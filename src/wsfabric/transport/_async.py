"""Async transport implementation using asyncio.

This module provides an asyncio-based WebSocket transport that uses
the native event loop for non-blocking I/O.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
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

# Try to import Rust core, fall back to pure Python
try:
    from wsfabric._core import FrameParser, Handshake
except ImportError:
    from wsfabric._core_fallback import (  # type: ignore[assignment]
        FrameParser,
        Handshake,
    )


class AsyncTransport(AbstractTransport):
    """Async WebSocket transport using asyncio.

    This transport uses asyncio streams for non-blocking I/O and integrates
    with the Rust frame parser for high-performance frame handling.

    Example:
        >>> transport = AsyncTransport()
        >>> await transport.connect("wss://example.com/ws")
        >>> await transport.send(b"Hello")
        >>> frame = await transport.recv()
        >>> await transport.close()
    """

    def __init__(self, config: BaseTransportConfig | None = None) -> None:
        """Initialize the async transport.

        Args:
            config: Transport configuration. Uses defaults if not provided.
        """
        super().__init__(config)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._parser: FrameParser | None = None
        self._uri: WebSocketURI | None = None
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._pending_frames: list[Frame] = []
        self._close_code: int | None = None
        self._close_reason: str = ""

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

    async def connect(self, uri: str | WebSocketURI) -> None:
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

        # Create SSL context if needed
        ssl_context: ssl.SSLContext | None = None
        if self._uri.is_secure:
            ssl_context = self._config.ssl_context or create_default_ssl_context()

        # Connect with timeout
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=self._uri.host,
                    port=self._uri.port,
                    ssl=ssl_context,
                ),
                timeout=self._config.connect_timeout,
            )
        except asyncio.TimeoutError:
            msg = f"Connection to {self._uri.host}:{self._uri.port} timed out"
            raise TimeoutError(
                msg, timeout=self._config.connect_timeout, operation="connect"
            ) from None
        except OSError as e:
            msg = f"Failed to connect to {self._uri.host}:{self._uri.port}: {e}"
            raise ConnectionError(msg) from e

        # Perform WebSocket handshake
        try:
            await self._perform_handshake()
        except Exception:
            await self._close_transport()
            raise

        # Initialize frame parser
        self._parser = FrameParser(
            self._config.max_frame_size,
            self._config.max_message_size,
        )
        self._connected = True

    async def _perform_handshake(self) -> None:
        """Perform the WebSocket opening handshake."""
        if self._uri is None or self._writer is None or self._reader is None:
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
        self._writer.write(request)
        await self._writer.drain()

        # Read response (read until we get the double CRLF)
        response_data = b""
        while b"\r\n\r\n" not in response_data:
            chunk = await asyncio.wait_for(
                self._reader.read(4096),
                timeout=self._config.connect_timeout,
            )
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

    async def send(self, data: bytes | str, *, binary: bool | None = None) -> None:
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

        # Encode and send frame (pass opcode as int for Rust compatibility)
        frame_data = self._parser.encode(int(opcode), data, True, True)
        await self._send_raw(frame_data)

    async def send_frame(self, frame: Frame) -> None:
        """Send a pre-built frame over the connection.

        Args:
            frame: The frame to send.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._parser is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        frame_data = self._parser.encode(
            int(frame.opcode), frame.payload, True, frame.fin
        )
        await self._send_raw(frame_data)

    async def _send_raw(self, data: bytes) -> None:
        """Send raw bytes over the connection.

        Args:
            data: The raw bytes to send.
        """
        if self._writer is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        async with self._write_lock:
            self._writer.write(data)
            if self._config.write_timeout:
                await asyncio.wait_for(
                    self._writer.drain(),
                    timeout=self._config.write_timeout,
                )
            else:
                await self._writer.drain()

    async def recv(self) -> Frame:
        """Receive the next WebSocket frame.

        Returns:
            The received frame.

        Raises:
            ConnectionError: If not connected or connection is lost.
            ProtocolError: If there's a protocol error.
            TimeoutError: If the read times out.
        """
        if not self._connected or self._parser is None or self._reader is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        async with self._read_lock:
            # Return pending frame if available
            if self._pending_frames:
                return self._pending_frames.pop(0)

            # Read until we have at least one complete frame
            while True:
                try:
                    if self._config.read_timeout:
                        chunk = await asyncio.wait_for(
                            self._reader.read(65536),
                            timeout=self._config.read_timeout,
                        )
                    else:
                        chunk = await self._reader.read(65536)
                except asyncio.TimeoutError:
                    msg = "Read operation timed out"
                    raise TimeoutError(
                        msg,
                        timeout=self._config.read_timeout or 0,
                        operation="recv",
                    ) from None

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
                            await self._handle_close_frame(frame)
                        elif frame.opcode == Opcode.PING:
                            await self._handle_ping_frame(frame)
                        elif frame.opcode == Opcode.PONG:
                            # Pong frames are typically handled by heartbeat manager
                            pass
                        else:
                            data_frames.append(frame)

                    if data_frames:
                        # Return first frame, queue the rest
                        self._pending_frames.extend(data_frames[1:])
                        return data_frames[0]

    async def _handle_close_frame(self, frame: Frame) -> None:
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
                with contextlib.suppress(Exception):
                    await self._send_raw(close_frame)

        self._connected = False
        await self._close_transport()

    async def _handle_ping_frame(self, frame: Frame) -> None:
        """Handle a received ping frame by sending a pong.

        Args:
            frame: The ping frame.
        """
        if self._parser is None:
            return

        # Send pong with same payload
        pong_frame = self._parser.encode(int(Opcode.PONG), frame.payload, True, True)
        with contextlib.suppress(Exception):
            await self._send_raw(pong_frame)

    async def ping(self, payload: bytes = b"") -> None:
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
        await self._send_raw(ping_data)

    async def close(self, code: int = CloseCode.NORMAL, reason: str = "") -> None:
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
            with contextlib.suppress(Exception):
                close_frame = self._parser.encode_close(code, reason, True)
                await self._send_raw(close_frame)

                # Wait for close frame response with timeout
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._wait_for_close(), timeout=5.0)

        self._connected = False
        await self._close_transport()

    async def _wait_for_close(self) -> None:
        """Wait for the server's close frame."""
        if self._reader is None or self._parser is None:
            return

        while self._connected:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)
                if not chunk:
                    break
                frames, _ = self._parser.feed(chunk)
                for frame in frames:
                    if frame.opcode == Opcode.CLOSE:
                        return
            except Exception:
                break

    async def _close_transport(self) -> None:
        """Close the underlying transport."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        self._parser = None

    async def __aenter__(self) -> AsyncTransport:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        """Async context manager exit."""
        await self.close()

    # Abstract method implementations for base class compatibility
    def _send_frame(self, frame: Frame) -> None:
        """Not used in async transport - use send_frame instead."""
        msg = "Use send_frame() for async transport"
        raise NotImplementedError(msg)

    def _recv_frame(self) -> Frame:
        """Not used in async transport - use recv instead."""
        msg = "Use recv() for async transport"
        raise NotImplementedError(msg)
