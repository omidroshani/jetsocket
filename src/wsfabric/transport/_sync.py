"""Synchronous transport implementation using socket.

This module provides a blocking WebSocket transport that uses
standard socket I/O with selectors for timeout handling.
"""

from __future__ import annotations

import builtins
import contextlib
import selectors
import socket
import ssl
import threading
from typing import TYPE_CHECKING

from wsfabric.exceptions import (
    ConnectionError,
    HandshakeError,
    ProtocolError,
    TimeoutError,
)
from wsfabric.transport.base import (
    AbstractTransport,
    BaseTransportConfig,
    create_default_ssl_context,
)
from wsfabric.transport.uri import WebSocketURI, parse_uri
from wsfabric.types import CloseCode, Frame, Opcode

if TYPE_CHECKING:
    pass

from wsfabric._core import Deflater, FrameParser, Handshake, parse_deflate_params


class SyncTransport(AbstractTransport):
    """Synchronous WebSocket transport using blocking sockets.

    This transport uses standard blocking socket I/O with optional
    timeouts via selectors.

    Example:
        >>> transport = SyncTransport()
        >>> transport.connect("wss://example.com/ws")
        >>> transport.send(b"Hello")
        >>> frame = transport.recv()
        >>> transport.close()
    """

    def __init__(self, config: BaseTransportConfig | None = None) -> None:
        """Initialize the sync transport.

        Args:
            config: Transport configuration. Uses defaults if not provided.
        """
        super().__init__(config)
        self._socket: socket.socket | None = None
        self._parser: FrameParser | None = None
        self._uri: WebSocketURI | None = None
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending_frames: list[Frame] = []
        self._close_code: int | None = None
        self._close_reason: str = ""
        self._selector: selectors.DefaultSelector | None = None
        # Compression
        self._deflater: Deflater | None = None

    @property
    def uri(self) -> WebSocketURI | None:
        """Return the connected URI, if any."""
        return self._uri

    @property
    def close_code(self) -> int | None:
        """Return the close code if the connection was closed."""
        return self._close_code

    @property
    def close_reason(self) -> str:
        """Return the close reason if the connection was closed."""
        return self._close_reason

    def connect(self, uri: str | WebSocketURI) -> None:
        """Connect to a WebSocket server.

        Args:
            uri: The WebSocket URI to connect to.

        Raises:
            ConnectionError: If the connection cannot be established.
            HandshakeError: If the WebSocket handshake fails.
            TimeoutError: If the connection times out.
        """
        if self._connected:
            msg = "Transport is already connected"
            raise ConnectionError(msg)

        # Parse URI if string
        if isinstance(uri, str):
            self._uri = parse_uri(uri)
        else:
            self._uri = uri

        # Create socket
        try:
            self._socket = socket.create_connection(
                (self._uri.host, self._uri.port),
                timeout=self._config.connect_timeout,
            )
        except builtins.TimeoutError:
            msg = f"Connection to {self._uri.host}:{self._uri.port} timed out"
            raise TimeoutError(
                msg, timeout=self._config.connect_timeout, operation="connect"
            ) from None
        except OSError as e:
            msg = f"Failed to connect to {self._uri.host}:{self._uri.port}: {e}"
            raise ConnectionError(msg) from e

        # Wrap with SSL if secure
        if self._uri.is_secure:
            ssl_context = self._config.ssl_context or create_default_ssl_context()
            try:
                self._socket = ssl_context.wrap_socket(
                    self._socket,
                    server_hostname=self._uri.host,
                )
            except ssl.SSLError as e:
                self._close_socket()
                msg = f"SSL handshake failed: {e}"
                raise ConnectionError(msg) from e

        # Set socket to non-blocking for timeout handling
        self._socket.setblocking(False)
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._socket, selectors.EVENT_READ)

        # Perform WebSocket handshake
        try:
            self._perform_handshake()
        except Exception:
            self._close_socket()
            raise

        # Initialize frame parser
        self._parser = FrameParser(
            self._config.max_frame_size,
            self._config.max_message_size,
        )
        self._connected = True

    def _perform_handshake(self) -> None:
        """Perform the WebSocket opening handshake."""
        if self._uri is None or self._socket is None:
            msg = "Transport not initialized"
            raise ConnectionError(msg)

        # Build extensions list
        extensions: list[str] = []
        if self._config.compression:
            extensions.append("permessage-deflate")

        # Build extra headers as tuples
        extra_headers = list(self._config.extra_headers.items())

        # Create handshake
        handshake = Handshake(
            self._uri.host_header,
            self._uri.resource_name,
            origin=self._config.origin or self._uri.origin,
            subprotocols=self._config.subprotocols or None,
            extensions=extensions or None,
            extra_headers=extra_headers or None,
        )

        # Send request
        request = handshake.build_request()
        self._send_all(request)

        # Read response (read until we get the double CRLF)
        response_data = b""
        while b"\r\n\r\n" not in response_data:
            chunk = self._recv_with_timeout(4096, self._config.connect_timeout)
            if not chunk:
                msg = "Connection closed during handshake"
                raise HandshakeError(msg)
            response_data += chunk

        # Parse and validate response
        try:
            result = handshake.parse_response(response_data)
        except ValueError as e:
            raise HandshakeError(str(e)) from e

        self._subprotocol = result.subprotocol
        self._extensions = result.extensions

        # Initialize compression if server accepted permessage-deflate
        if self._config.compression:
            ext_header = ""
            if hasattr(result, "headers") and isinstance(result.headers, dict):
                ext_header = result.headers.get("sec-websocket-extensions", "")
            if "permessage-deflate" in ext_header.lower():
                cnct, snct, cmwb, smwb = parse_deflate_params(ext_header)
                self._deflater = Deflater(
                    client_no_context_takeover=cnct,
                    server_no_context_takeover=snct,
                    client_max_window_bits=cmwb,
                    server_max_window_bits=smwb,
                )

    def _send_all(self, data: bytes) -> None:
        """Send all data, handling partial sends.

        Args:
            data: The data to send.
        """
        if self._socket is None:
            msg = "Socket is not connected"
            raise ConnectionError(msg)

        total_sent = 0
        while total_sent < len(data):
            # Wait for socket to be writable
            if self._selector:
                self._selector.modify(self._socket, selectors.EVENT_WRITE)
                events = self._selector.select(timeout=self._config.write_timeout)
                self._selector.modify(self._socket, selectors.EVENT_READ)
                if not events:
                    msg = "Write operation timed out"
                    raise TimeoutError(
                        msg,
                        timeout=self._config.write_timeout or 0,
                        operation="send",
                    )

            try:
                sent = self._socket.send(data[total_sent:])
                if sent == 0:
                    msg = "Connection closed"
                    raise ConnectionError(msg)
                total_sent += sent
            except BlockingIOError:
                continue
            except OSError as e:
                msg = f"Send failed: {e}"
                raise ConnectionError(msg) from e

    def _recv_with_timeout(self, size: int, timeout: float | None) -> bytes:
        """Receive data with optional timeout.

        Args:
            size: Maximum bytes to receive.
            timeout: Timeout in seconds (None for blocking).

        Returns:
            The received bytes.
        """
        if self._socket is None or self._selector is None:
            msg = "Socket is not connected"
            raise ConnectionError(msg)

        events = self._selector.select(timeout=timeout)
        if not events:
            msg = "Read operation timed out"
            raise TimeoutError(msg, timeout=timeout or 0, operation="recv")

        try:
            return self._socket.recv(size)
        except BlockingIOError:
            return b""
        except OSError as e:
            msg = f"Receive failed: {e}"
            raise ConnectionError(msg) from e

    def send(self, data: bytes | str, *, binary: bool | None = None) -> None:
        """Send data over the WebSocket connection.

        Args:
            data: The data to send. Can be bytes or string.
            binary: If True, send as binary frame. If False, send as text.
                   If None, infer from data type.

        Raises:
            ConnectionError: If not connected.
            ProtocolError: If there's an error sending the frame.
        """
        if not self._connected or self._parser is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        # Determine opcode
        if binary is None:
            binary = isinstance(data, bytes)

        opcode = Opcode.BINARY if binary else Opcode.TEXT

        # Convert string to bytes
        if isinstance(data, str):
            data = data.encode("utf-8")

        # Compress if deflater is active and payload exceeds threshold
        rsv1 = False
        if (
            self._deflater is not None
            and len(data) >= self._config.compression_threshold
        ):
            data = self._deflater.compress(data)
            rsv1 = True

        # Encode and send frame (pass opcode as int for Rust compatibility)
        frame_data = self._parser.encode(int(opcode), data, True, True, rsv1=rsv1)
        with self._write_lock:
            self._send_all(frame_data)

    def send_frame(self, frame: Frame) -> None:
        """Send a pre-built frame over the connection.

        Args:
            frame: The frame to send.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._parser is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        payload = frame.payload
        rsv1 = frame.rsv1
        if (
            self._deflater is not None
            and not frame.opcode.is_control_frame
            and len(payload) >= self._config.compression_threshold
        ):
            payload = self._deflater.compress(payload)
            rsv1 = True

        frame_data = self._parser.encode(
            int(frame.opcode), payload, True, frame.fin, rsv1=rsv1
        )
        with self._write_lock:
            self._send_all(frame_data)

    def recv(self, timeout: float | None = None) -> Frame:
        """Receive the next WebSocket frame.

        Args:
            timeout: Optional timeout in seconds. Uses config default if None.

        Returns:
            The received frame.

        Raises:
            ConnectionError: If not connected or connection is lost.
            ProtocolError: If there's a protocol error.
            TimeoutError: If the read times out.
        """
        if not self._connected or self._parser is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        effective_timeout = (
            timeout if timeout is not None else self._config.read_timeout
        )

        with self._read_lock:
            # Return pending frame if available
            if self._pending_frames:
                return self._pending_frames.pop(0)

            # Read until we have at least one complete frame
            while True:
                chunk = self._recv_with_timeout(65536, effective_timeout)

                if not chunk:
                    self._connected = False
                    msg = "Connection closed by remote"
                    raise ConnectionError(msg)

                # Feed data to parser
                try:
                    frames, _ = self._parser.feed(chunk)
                except ValueError as e:
                    raise ProtocolError(str(e)) from e

                if frames:
                    # Handle control frames automatically
                    data_frames: list[Frame] = []
                    for frame in frames:
                        if frame.opcode == Opcode.CLOSE:
                            self._handle_close_frame(frame)
                        elif frame.opcode == Opcode.PING:
                            self._handle_ping_frame(frame)
                        elif frame.opcode == Opcode.PONG:
                            # Pong frames are typically handled by heartbeat manager
                            pass
                        else:
                            # Decompress if RSV1 is set (permessage-deflate)
                            if frame.rsv1 and self._deflater is not None:
                                decompressed = self._deflater.decompress(frame.payload)
                                frame = Frame(  # noqa: PLW2901
                                    opcode=Opcode(int(frame.opcode)),
                                    payload=decompressed,
                                    fin=frame.fin,
                                )
                            data_frames.append(frame)

                    if data_frames:
                        # Return first frame, queue the rest
                        self._pending_frames.extend(data_frames[1:])
                        return data_frames[0]

    def _handle_close_frame(self, frame: Frame) -> None:
        """Handle a received close frame.

        Args:
            frame: The close frame.
        """
        self._close_code = frame.close_code or CloseCode.NO_STATUS
        self._close_reason = frame.close_reason

        if not self._closing:
            # Echo the close frame
            self._closing = True
            if self._parser is not None:
                close_frame = self._parser.encode_close(
                    self._close_code, self._close_reason, True
                )
                try:
                    with self._write_lock:
                        self._send_all(close_frame)
                except Exception:
                    pass  # Best effort

        self._connected = False
        self._close_socket()

    def _handle_ping_frame(self, frame: Frame) -> None:
        """Handle a received ping frame by sending a pong.

        Args:
            frame: The ping frame.
        """
        if self._parser is None:
            return

        # Send pong with same payload
        pong_frame = self._parser.encode(int(Opcode.PONG), frame.payload, True, True)
        try:
            with self._write_lock:
                self._send_all(pong_frame)
        except Exception:
            pass  # Best effort

    def ping(self, payload: bytes = b"") -> None:
        """Send a ping frame.

        Args:
            payload: Optional payload for the ping (max 125 bytes).

        Raises:
            ValueError: If payload is too large.
            ConnectionError: If not connected.
        """
        if len(payload) > 125:
            msg = "Ping payload must be 125 bytes or less"
            raise ValueError(msg)

        if not self._connected or self._parser is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        ping_data = self._parser.encode(int(Opcode.PING), payload, True, True)
        with self._write_lock:
            self._send_all(ping_data)

    def close(self, code: int = CloseCode.NORMAL, reason: str = "") -> None:
        """Close the WebSocket connection gracefully.

        Args:
            code: The close code (default: 1000 normal closure).
            reason: Optional close reason string.
        """
        if not self._connected or self._closing:
            return

        self._closing = True
        self._close_code = code
        self._close_reason = reason

        if self._parser is not None:
            try:
                close_frame = self._parser.encode_close(code, reason, True)
                with self._write_lock:
                    self._send_all(close_frame)

                # Wait for close frame response with timeout
                self._wait_for_close(timeout=5.0)
            except Exception:
                pass  # Close anyway

        self._connected = False
        self._close_socket()

    def _wait_for_close(self, timeout: float = 5.0) -> None:
        """Wait for the server's close frame."""
        if self._parser is None:
            return

        try:
            while self._connected:
                chunk = self._recv_with_timeout(4096, timeout)
                if not chunk:
                    break
                frames, _ = self._parser.feed(chunk)
                for frame in frames:
                    if frame.opcode == Opcode.CLOSE:
                        return
        except Exception:
            pass

    def _close_socket(self) -> None:
        """Close the underlying socket."""
        if self._selector is not None:
            with contextlib.suppress(Exception):
                self._selector.close()
            self._selector = None

        if self._socket is not None:
            with contextlib.suppress(Exception):
                self._socket.close()
            self._socket = None

        self._parser = None
        self._deflater = None

    def __enter__(self) -> SyncTransport:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    # Abstract method implementations for base class compatibility
    def _send_frame(self, frame: Frame) -> None:
        """Send a frame - delegates to send_frame."""
        self.send_frame(frame)

    def _recv_frame(self) -> Frame:
        """Receive a frame - delegates to recv."""
        return self.recv()
