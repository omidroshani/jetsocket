"""Async transport implementation using asyncio Protocol.

This module provides a high-performance asyncio-based WebSocket transport
using the raw Protocol interface instead of StreamReader/StreamWriter for
minimal overhead on the send/recv hot path.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import ssl
from typing import TYPE_CHECKING, Any

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

# Type alias for resolved addresses
ResolvedAddress = tuple[socket.AddressFamily, str]

# Try to import Rust core, fall back to pure Python
try:
    from wsfabric._core import Deflater, FrameParser, Handshake, parse_deflate_params
except ImportError:
    from wsfabric._core_fallback import (  # type: ignore[assignment]
        Deflater,
        FrameParser,
        Handshake,
        parse_deflate_params,
    )

# Sentinel for connection lost
_CONNECTION_LOST = object()


class _WSProtocol(asyncio.Protocol):
    """Low-level WebSocket protocol handler.

    Feeds incoming data to the frame parser and delivers parsed frames
    to a queue. Handles backpressure via pause/resume callbacks.
    """

    def __init__(self, frame_queue: asyncio.Queue[Any]) -> None:
        self.transport: asyncio.Transport | None = None
        self.frame_queue = frame_queue
        self.parser: FrameParser | None = None
        self.deflater: Deflater | None = None
        self.compression_threshold: int = 128

        # Backpressure
        self._can_write = asyncio.Event()
        self._can_write.set()

        # Handshake mode: accumulate bytes until handshake completes
        self._handshake_buffer = bytearray()
        self._handshake_future: asyncio.Future[bytes] | None = None
        self._handshake_done = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called when connection is established."""
        self.transport = transport  # type: ignore[assignment]

    def data_received(self, data: bytes) -> None:
        """Called when data is received from the network."""
        # During handshake, accumulate raw bytes
        if not self._handshake_done:
            self._handshake_buffer.extend(data)
            if b"\r\n\r\n" in self._handshake_buffer:
                if self._handshake_future is not None and not self._handshake_future.done():
                    self._handshake_future.set_result(bytes(self._handshake_buffer))
            return

        # After handshake, parse WebSocket frames
        if self.parser is None:
            return

        try:
            frames, _ = self.parser.feed(data)
        except ValueError:
            # Protocol error — close
            if self.transport is not None:
                self.transport.close()
            return

        for frame in frames:
            opcode = int(frame.opcode)

            if opcode == 0x9:  # PING — auto-respond with PONG
                if self.parser is not None and self.transport is not None:
                    pong = self.parser.encode(0xA, frame.payload, True, True)
                    self.transport.write(pong)

            elif opcode == 0x8:  # CLOSE
                self.frame_queue.put_nowait(frame)

            elif opcode == 0xA:  # PONG
                self.frame_queue.put_nowait(frame)

            else:  # DATA frames (TEXT, BINARY)
                # Decompress if RSV1 set
                if frame.rsv1 and self.deflater is not None:
                    decompressed = self.deflater.decompress(frame.payload)
                    frame = Frame(
                        opcode=Opcode(int(frame.opcode)),
                        payload=decompressed,
                        fin=frame.fin,
                    )
                self.frame_queue.put_nowait(frame)

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when connection is lost."""
        self.frame_queue.put_nowait(_CONNECTION_LOST)
        if self._handshake_future is not None and not self._handshake_future.done():
            if exc:
                self._handshake_future.set_exception(exc)
            else:
                self._handshake_future.set_exception(
                    ConnectionError("Connection closed during handshake")
                )

    def pause_writing(self) -> None:
        """Called when the transport's write buffer is full."""
        self._can_write.clear()

    def resume_writing(self) -> None:
        """Called when the transport's write buffer drains below threshold."""
        self._can_write.set()


class AsyncTransport(AbstractTransport):
    """Async WebSocket transport using asyncio Protocol.

    Uses the raw asyncio Protocol interface for maximum performance:
    - No StreamReader/StreamWriter overhead
    - No drain() coroutine on sends (fire-and-forget with backpressure)
    - No asyncio.Lock on the hot path
    - Frame parsing happens in the data_received callback

    Example:
        >>> transport = AsyncTransport()
        >>> await transport.connect("wss://example.com/ws")
        >>> await transport.send(b"Hello")
        >>> frame = await transport.recv()
        >>> await transport.close()
    """

    def __init__(self, config: BaseTransportConfig | None = None) -> None:
        """Initialize the async transport."""
        super().__init__(config)
        self._protocol: _WSProtocol | None = None
        self._asyncio_transport: asyncio.Transport | None = None
        self._parser: FrameParser | None = None
        self._uri: WebSocketURI | None = None
        self._frame_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._close_code: int | None = None
        self._close_reason: str = ""
        self._cached_ssl_session: ssl.SSLSession | None = None
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

    async def _resolve_dns(self, host: str, port: int) -> list[ResolvedAddress]:
        """Resolve DNS fresh on each call (no caching)."""
        loop = asyncio.get_event_loop()

        try:
            infos = await loop.run_in_executor(
                None,
                lambda: socket.getaddrinfo(
                    host, port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                ),
            )
        except socket.gaierror as e:
            msg = f"DNS resolution failed for {host}: {e}"
            raise ConnectionError(msg) from e

        seen: set[tuple[socket.AddressFamily, str]] = set()
        addresses: list[ResolvedAddress] = []

        for family, type_, proto, canonname, sockaddr in infos:
            ip = str(sockaddr[0])
            key = (family, ip)
            if key not in seen:
                seen.add(key)
                addresses.append((family, ip))

        if not addresses:
            msg = f"No addresses found for {host}"
            raise ConnectionError(msg)

        return addresses

    async def connect(self, uri: str | WebSocketURI) -> None:
        """Connect to a WebSocket server."""
        if self._connected:
            msg = "Transport is already connected"
            raise ConnectionError(msg)

        if isinstance(uri, str):
            self._uri = parse_uri(uri)
        else:
            self._uri = uri

        ssl_context: ssl.SSLContext | None = None
        if self._uri.is_secure:
            ssl_context = self._config.ssl_context or create_default_ssl_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Resolve DNS fresh
        try:
            addresses = await asyncio.wait_for(
                self._resolve_dns(self._uri.host, self._uri.port),
                timeout=self._config.connect_timeout / 2,
            )
        except asyncio.TimeoutError:
            msg = f"DNS resolution for {self._uri.host} timed out"
            raise TimeoutError(
                msg, timeout=self._config.connect_timeout, operation="dns"
            ) from None

        # Try each resolved address
        last_error: Exception | None = None
        for family, ip in addresses:
            try:
                await self._connect_to_address(ip, family, ssl_context)
                break
            except OSError as e:
                last_error = e
                continue
        else:
            msg = f"Failed to connect to {self._uri.host}:{self._uri.port}"
            if last_error:
                msg = f"{msg}: {last_error}"
            raise ConnectionError(msg)

        # Perform WebSocket handshake
        try:
            await self._perform_handshake()
        except Exception:
            await self._close_transport()
            raise

        # Cache SSL session
        if ssl_context is not None and self._asyncio_transport is not None:
            self._cache_ssl_session()

        # Initialize frame parser
        self._parser = FrameParser(
            self._config.max_frame_size,
            self._config.max_message_size,
        )

        # Configure protocol for frame parsing mode
        self._protocol.parser = self._parser  # type: ignore[union-attr]
        self._protocol.deflater = self._deflater  # type: ignore[union-attr]
        self._protocol.compression_threshold = self._config.compression_threshold  # type: ignore[union-attr]
        self._protocol._handshake_done = True  # type: ignore[union-attr]

        # Drain any leftover data from handshake buffer
        if self._protocol is not None:
            leftover = self._protocol._handshake_buffer
            # Find data after the \r\n\r\n
            idx = leftover.find(b"\r\n\r\n")
            if idx >= 0:
                remaining = bytes(leftover[idx + 4 :])
                if remaining:
                    self._protocol.data_received(remaining)

        self._connected = True

    async def _connect_to_address(
        self,
        ip: str,
        family: socket.AddressFamily,
        ssl_context: ssl.SSLContext | None,
    ) -> None:
        """Connect to a specific IP address using Protocol."""
        if self._uri is None:
            msg = "URI not set"
            raise ConnectionError(msg)

        loop = asyncio.get_event_loop()
        self._frame_queue = asyncio.Queue()

        ssl_kwargs: dict[str, Any] = {}
        if ssl_context is not None:
            ssl_kwargs["ssl"] = ssl_context
            ssl_kwargs["server_hostname"] = self._uri.host

        try:
            transport, protocol = await asyncio.wait_for(
                loop.create_connection(
                    lambda: _WSProtocol(self._frame_queue),
                    host=ip,
                    port=self._uri.port,
                    family=family,
                    **ssl_kwargs,
                ),
                timeout=self._config.connect_timeout,
            )
        except asyncio.TimeoutError:
            msg = f"Connection to {ip}:{self._uri.port} timed out"
            raise TimeoutError(
                msg, timeout=self._config.connect_timeout, operation="connect"
            ) from None

        self._asyncio_transport = transport
        self._protocol = protocol

    def _cache_ssl_session(self) -> None:
        """Cache the current SSL session for reuse on reconnect."""
        if self._asyncio_transport is None:
            return

        ssl_object = self._asyncio_transport.get_extra_info("ssl_object")
        if ssl_object is not None:
            try:
                session = ssl_object.session
                if session is not None:
                    self._cached_ssl_session = session
            except AttributeError:
                pass

    @property
    def cached_ssl_session(self) -> ssl.SSLSession | None:
        """Return the cached SSL session, if any."""
        return self._cached_ssl_session

    def clear_ssl_session_cache(self) -> None:
        """Clear the cached SSL session."""
        self._cached_ssl_session = None

    async def _perform_handshake(self) -> None:
        """Perform the WebSocket opening handshake."""
        if self._uri is None or self._protocol is None or self._asyncio_transport is None:
            msg = "Transport not initialized"
            raise ConnectionError(msg)

        # Build extensions list
        extensions: list[str] = []
        if self._config.compression:
            extensions.append("permessage-deflate")

        extra_headers = list(self._config.extra_headers.items())

        handshake = Handshake(
            self._uri.host_header,
            self._uri.resource_name,
            origin=self._config.origin or self._uri.origin,
            subprotocols=self._config.subprotocols or None,
            extensions=extensions or None,
            extra_headers=extra_headers or None,
        )

        # Send handshake request (fire-and-forget, no drain)
        request = handshake.build_request()
        self._asyncio_transport.write(request)

        # Set up future for handshake response
        loop = asyncio.get_event_loop()
        self._protocol._handshake_future = loop.create_future()

        # Wait for handshake response
        try:
            response_data = await asyncio.wait_for(
                self._protocol._handshake_future,
                timeout=self._config.connect_timeout,
            )
        except asyncio.TimeoutError:
            msg = "Handshake timed out"
            raise HandshakeError(msg) from None

        try:
            result = handshake.parse_response(response_data)
        except ValueError as e:
            raise HandshakeError(str(e)) from e

        self._subprotocol = result.subprotocol
        self._extensions = result.extensions

        # Initialize compression
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

    async def send(self, data: bytes | str, *, binary: bool | None = None) -> None:
        """Send data over the WebSocket connection.

        No locks, no drain(). Writes directly to the transport.
        Backpressure is handled via pause_writing/resume_writing callbacks.
        """
        if not self._connected or self._parser is None or self._asyncio_transport is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        if binary is None:
            binary = isinstance(data, bytes)

        opcode = Opcode.BINARY if binary else Opcode.TEXT

        if isinstance(data, str):
            data = data.encode("utf-8")

        # Compress if applicable
        rsv1 = False
        if (
            self._deflater is not None
            and len(data) >= self._config.compression_threshold
        ):
            data = self._deflater.compress(data)
            rsv1 = True

        frame_data = self._parser.encode(int(opcode), data, True, True, rsv1=rsv1)

        # Wait for backpressure to clear (only blocks if transport is paused)
        if self._protocol is not None and not self._protocol._can_write.is_set():
            await self._protocol._can_write.wait()

        self._asyncio_transport.write(frame_data)

    async def send_frame(self, frame: Frame) -> None:
        """Send a pre-built frame."""
        if not self._connected or self._parser is None or self._asyncio_transport is None:
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

        if self._protocol is not None and not self._protocol._can_write.is_set():
            await self._protocol._can_write.wait()

        self._asyncio_transport.write(frame_data)

    async def recv(self) -> Frame:
        """Receive the next WebSocket frame.

        No locks. Frames arrive via the Protocol's data_received callback
        and are queued. This just awaits the queue.
        """
        if not self._connected:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        while True:
            try:
                if self._config.read_timeout:
                    item = await asyncio.wait_for(
                        self._frame_queue.get(),
                        timeout=self._config.read_timeout,
                    )
                else:
                    item = await self._frame_queue.get()
            except asyncio.TimeoutError:
                msg = "Read operation timed out"
                raise TimeoutError(
                    msg,
                    timeout=self._config.read_timeout or 0,
                    operation="recv",
                ) from None

            if item is _CONNECTION_LOST:
                self._connected = False
                msg = "Connection closed by remote"
                raise ConnectionError(msg)

            frame = item

            # Handle close frame
            if int(frame.opcode) == 0x8:
                self._close_code = frame.close_code or CloseCode.NO_STATUS
                self._close_reason = frame.close_reason

                if not self._closing:
                    self._closing = True
                    if self._parser is not None and self._asyncio_transport is not None:
                        close_echo = self._parser.encode_close(
                            self._close_code, self._close_reason, True
                        )
                        with contextlib.suppress(Exception):
                            self._asyncio_transport.write(close_echo)

                self._connected = False
                await self._close_transport()
                msg = "Connection closed by remote"
                raise ConnectionError(msg)

            # Skip PONG frames (handled by heartbeat manager externally)
            if int(frame.opcode) == 0xA:
                continue

            return frame

    async def ping(self, payload: bytes = b"") -> None:
        """Send a ping frame."""
        if len(payload) > 125:
            msg = "Ping payload must be 125 bytes or less"
            raise ValueError(msg)

        if not self._connected or self._parser is None or self._asyncio_transport is None:
            msg = "Transport is not connected"
            raise ConnectionError(msg)

        ping_data = self._parser.encode(int(Opcode.PING), payload, True, True)
        self._asyncio_transport.write(ping_data)

    async def close(self, code: int = CloseCode.NORMAL, reason: str = "") -> None:
        """Close the WebSocket connection gracefully."""
        if not self._connected or self._closing:
            return

        self._closing = True
        self._close_code = code
        self._close_reason = reason

        if self._parser is not None and self._asyncio_transport is not None:
            with contextlib.suppress(Exception):
                close_frame = self._parser.encode_close(code, reason, True)
                self._asyncio_transport.write(close_frame)

                # Wait briefly for close response
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._wait_for_close(), timeout=5.0)

        self._connected = False
        await self._close_transport()

    async def _wait_for_close(self) -> None:
        """Wait for the server's close frame."""
        while self._connected:
            try:
                item = await asyncio.wait_for(
                    self._frame_queue.get(), timeout=1.0
                )
                if item is _CONNECTION_LOST:
                    return
                if int(item.opcode) == 0x8:
                    return
            except (asyncio.TimeoutError, Exception):
                return

    async def _close_transport(self) -> None:
        """Close the underlying transport."""
        if self._asyncio_transport is not None:
            with contextlib.suppress(Exception):
                self._asyncio_transport.close()
            self._asyncio_transport = None
        self._protocol = None
        self._parser = None
        self._deflater = None

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
