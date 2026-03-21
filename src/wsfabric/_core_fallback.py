"""Pure-Python fallback for the Rust core module.

This module provides the same API as the Rust _core module but implemented
in pure Python. It is used when the Rust extension cannot be loaded (e.g.,
on platforms without prebuilt wheels or when Rust compilation fails).

Performance is approximately 10x slower than the Rust implementation, but
functionally equivalent.
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# WebSocket GUID for accept key calculation
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Opcode(IntEnum):
    """WebSocket frame opcodes."""

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA

    @property
    def is_control_frame(self) -> bool:
        """Check if this is a control frame opcode."""
        return self >= 0x8

    @property
    def is_data_frame(self) -> bool:
        """Check if this is a data frame opcode."""
        return self <= 0x2


@dataclass
class Frame:
    """A parsed WebSocket frame."""

    opcode: Opcode
    payload: bytes
    fin: bool = True
    rsv1: bool = False
    rsv2: bool = False
    rsv3: bool = False

    @property
    def payload_len(self) -> int:
        """Get payload length."""
        return len(self.payload)

    def as_text(self) -> str:
        """Decode payload as UTF-8 text."""
        return self.payload.decode("utf-8")

    def __repr__(self) -> str:
        return f"Frame(opcode={self.opcode.name}, fin={self.fin}, payload_len={len(self.payload)})"


def apply_mask(data: bytes, mask: tuple[int, int, int, int] | bytes) -> bytes:
    """Apply WebSocket masking to data.

    Args:
        data: The data to mask/unmask.
        mask: A 4-byte masking key.

    Returns:
        The masked/unmasked data.
    """
    if isinstance(mask, bytes):
        mask = (mask[0], mask[1], mask[2], mask[3])

    if not data:
        return b""

    # Process in chunks for better performance
    result = bytearray(len(data))
    for i, byte in enumerate(data):
        result[i] = byte ^ mask[i % 4]

    return bytes(result)


def generate_key() -> str:
    """Generate a random Sec-WebSocket-Key."""
    random_bytes = os.urandom(16)
    return base64.b64encode(random_bytes).decode("ascii")


def validate_accept(key: str, accept: str) -> bool:
    """Validate the Sec-WebSocket-Accept header value.

    Args:
        key: The Sec-WebSocket-Key that was sent in the request.
        accept: The Sec-WebSocket-Accept received in the response.

    Returns:
        True if the accept value is valid.
    """
    expected = _compute_accept(key)
    return expected == accept


def _compute_accept(key: str) -> str:
    """Compute the expected Sec-WebSocket-Accept value."""
    sha1 = hashlib.sha1()
    sha1.update(key.encode("ascii"))
    sha1.update(_WS_GUID)
    return base64.b64encode(sha1.digest()).decode("ascii")


class FrameParser:
    """WebSocket frame parser with configurable limits.

    This parser follows the sans-I/O pattern: it accepts raw bytes and returns
    parsed frames without performing any I/O operations.
    """

    def __init__(
        self,
        max_frame_size: int = 16 * 1024 * 1024,
        max_message_size: int = 64 * 1024 * 1024,
    ) -> None:
        """Create a new frame parser.

        Args:
            max_frame_size: Maximum size of a single frame.
            max_message_size: Maximum size of an assembled message.
        """
        self.max_frame_size = max_frame_size
        self.max_message_size = max_message_size
        self._buffer = bytearray()
        self._message_buffer = bytearray()
        self._message_opcode: Opcode | None = None

    def feed(self, data: bytes) -> tuple[list[Frame], int]:
        """Feed raw bytes into the parser.

        Args:
            data: Raw bytes received from the socket.

        Returns:
            A tuple of (frames, bytes_consumed) where frames is a list of
            complete frames that could be parsed from the input.

        Raises:
            ValueError: If a protocol error is detected.
        """
        self._buffer.extend(data)
        frames: list[Frame] = []
        total_consumed = 0

        while True:
            result = self._parse_frame()
            if result is None:
                break
            frame, consumed = result
            total_consumed += consumed
            frames.append(frame)
            # Remove consumed bytes immediately to avoid re-parsing
            del self._buffer[:consumed]

        return frames, total_consumed

    def encode(
        self,
        opcode: Opcode,
        payload: bytes,
        mask: bool = True,
        fin: bool = True,
        rsv1: bool = False,
    ) -> bytes:
        """Encode a frame for sending.

        Args:
            opcode: The frame opcode.
            payload: The payload bytes.
            mask: Whether to mask the frame (required for client-to-server).
            fin: Whether this is the final fragment.
            rsv1: Whether to set the RSV1 bit (for compression).

        Returns:
            The encoded frame as bytes.
        """
        return self._encode_frame(opcode, payload, mask, fin, rsv1=rsv1)

    def encode_close(
        self,
        code: int = 1000,
        reason: str = "",
        mask: bool = True,
    ) -> bytes:
        """Build a close frame with code and reason.

        Args:
            code: The close code.
            reason: The close reason.
            mask: Whether to mask the frame.

        Returns:
            The encoded close frame.
        """
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        return self._encode_frame(Opcode.CLOSE, payload, mask, True)

    def reset(self) -> None:
        """Reset parser state (for reconnection)."""
        self._buffer.clear()
        self._message_buffer.clear()
        self._message_opcode = None

    def _parse_frame(self) -> tuple[Frame, int] | None:
        """Parse a single frame from the buffer."""
        if len(self._buffer) < 2:
            return None

        first_byte = self._buffer[0]
        second_byte = self._buffer[1]

        # Parse first byte
        fin = bool(first_byte & 0x80)
        rsv1 = bool(first_byte & 0x40)
        rsv2 = bool(first_byte & 0x20)
        rsv3 = bool(first_byte & 0x10)
        opcode_value = first_byte & 0x0F

        try:
            opcode = Opcode(opcode_value)
        except ValueError:
            msg = f"Invalid opcode: {opcode_value}"
            raise ValueError(msg) from None

        # Check reserved bits
        if rsv2 or rsv3:
            msg = "Reserved bits set without extension"
            raise ValueError(msg)

        # Parse second byte
        masked = bool(second_byte & 0x80)
        payload_len_byte = second_byte & 0x7F

        # Calculate header size and payload length
        header_size, payload_len = self._parse_length(payload_len_byte, masked)
        if header_size is None:
            return None  # Need more data

        # Check frame size limit
        if payload_len > self.max_frame_size:
            msg = f"Frame too large: {payload_len} bytes (max: {self.max_frame_size})"
            raise ValueError(msg)

        # Control frame validation
        if opcode.is_control_frame:
            if payload_len > 125:
                msg = f"Control frame too large: {payload_len} bytes (max: 125)"
                raise ValueError(msg)
            if not fin:
                msg = "Fragmented control frame"
                raise ValueError(msg)

        # Check if we have enough data
        total_size = header_size + payload_len
        if len(self._buffer) < total_size:
            return None

        # Extract mask key if present
        mask_key: bytes | None = None
        if masked:
            mask_offset = header_size - 4
            mask_key = bytes(self._buffer[mask_offset : mask_offset + 4])

        # Extract and unmask payload
        payload = bytes(self._buffer[header_size:total_size])
        if mask_key is not None:
            payload = apply_mask(payload, mask_key)

        frame = Frame(
            opcode=opcode,
            payload=payload,
            fin=fin,
            rsv1=rsv1,
            rsv2=rsv2,
            rsv3=rsv3,
        )

        return frame, total_size

    def _parse_length(
        self,
        initial_len: int,
        masked: bool,
    ) -> tuple[int | None, int]:
        """Parse the payload length from the header."""
        mask_size = 4 if masked else 0

        if initial_len <= 125:
            return 2 + mask_size, initial_len
        elif initial_len == 126:
            if len(self._buffer) < 4:
                return None, 0
            length = struct.unpack(">H", self._buffer[2:4])[0]
            return 4 + mask_size, length
        else:  # 127
            if len(self._buffer) < 10:
                return None, 0
            length = struct.unpack(">Q", self._buffer[2:10])[0]
            return 10 + mask_size, length

    def _encode_frame(
        self,
        opcode: Opcode,
        payload: bytes,
        mask: bool,
        fin: bool,
        rsv1: bool = False,
    ) -> bytes:
        """Encode a frame for sending."""
        payload_len = len(payload)
        frame_parts: list[bytes] = []

        # First byte: FIN + RSV1 + opcode
        first_byte = (0x80 if fin else 0x00) | int(opcode)
        if rsv1:
            first_byte |= 0x40
        frame_parts.append(bytes([first_byte]))

        # Second byte and extended length
        mask_bit = 0x80 if mask else 0x00
        if payload_len <= 125:
            frame_parts.append(bytes([mask_bit | payload_len]))
        elif payload_len <= 65535:
            frame_parts.append(bytes([mask_bit | 126]))
            frame_parts.append(struct.pack(">H", payload_len))
        else:
            frame_parts.append(bytes([mask_bit | 127]))
            frame_parts.append(struct.pack(">Q", payload_len))

        # Mask key and payload
        if mask:
            mask_key = os.urandom(4)
            frame_parts.append(mask_key)
            frame_parts.append(apply_mask(payload, mask_key))
        else:
            frame_parts.append(payload)

        return b"".join(frame_parts)


class Handshake:
    """WebSocket handshake helper."""

    def __init__(
        self,
        host: str,
        path: str,
        origin: str | None = None,
        subprotocols: list[str] | None = None,
        extensions: list[str] | None = None,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        """Create a new handshake builder.

        Args:
            host: The Host header value.
            path: The request path.
            origin: Optional Origin header.
            subprotocols: Optional list of subprotocols to request.
            extensions: Optional list of extensions to request.
            extra_headers: Optional additional headers.
        """
        self._key = generate_key()
        self._host = host
        self._path = path
        self._origin = origin
        self._subprotocols = subprotocols or []
        self._extensions = extensions or []
        self._extra_headers = extra_headers or []

    @property
    def key(self) -> str:
        """Get the generated Sec-WebSocket-Key."""
        return self._key

    def build_request(self) -> bytes:
        """Build the HTTP/1.1 upgrade request."""
        lines = [
            f"GET {self._path} HTTP/1.1",
            f"Host: {self._host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {self._key}",
            "Sec-WebSocket-Version: 13",
        ]

        if self._origin:
            lines.append(f"Origin: {self._origin}")

        if self._subprotocols:
            lines.append(f"Sec-WebSocket-Protocol: {', '.join(self._subprotocols)}")

        if self._extensions:
            lines.append(f"Sec-WebSocket-Extensions: {'; '.join(self._extensions)}")

        for name, value in self._extra_headers:
            lines.append(f"{name}: {value}")

        lines.append("")
        lines.append("")

        return "\r\n".join(lines).encode("utf-8")

    def parse_response(self, response: bytes) -> HandshakeResult:
        """Parse the HTTP response and validate the handshake.

        Args:
            response: The raw HTTP response bytes.

        Returns:
            HandshakeResult with status, headers, etc.

        Raises:
            ValueError: If the handshake is invalid.
        """
        try:
            response_str = response.decode("utf-8")
        except UnicodeDecodeError:
            msg = "Invalid HTTP response"
            raise ValueError(msg) from None

        # Split headers from body
        try:
            header_end = response_str.index("\r\n\r\n")
        except ValueError:
            msg = "Invalid HTTP response"
            raise ValueError(msg) from None

        header_section = response_str[:header_end]
        lines = header_section.split("\r\n")

        # Parse status line
        status_line = lines[0]
        parts = status_line.split(" ", 2)
        if len(parts) < 2:
            msg = "Invalid HTTP response"
            raise ValueError(msg)

        try:
            status = int(parts[1])
        except ValueError:
            msg = "Invalid HTTP response"
            raise ValueError(msg) from None

        if status != 101:
            reason = parts[2] if len(parts) > 2 else ""
            msg = f"HTTP {status}: {reason}"
            raise ValueError(msg)

        # Parse headers
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()

        # Validate required headers
        upgrade = headers.get("upgrade", "")
        if upgrade.lower() != "websocket":
            msg = "Invalid Upgrade header"
            raise ValueError(msg)

        connection = headers.get("connection", "")
        if "upgrade" not in connection.lower():
            msg = "Invalid Connection header"
            raise ValueError(msg)

        # Validate Sec-WebSocket-Accept
        accept = headers.get("sec-websocket-accept")
        if accept is None:
            msg = "Missing Sec-WebSocket-Accept header"
            raise ValueError(msg)

        if not validate_accept(self._key, accept):
            msg = "Invalid Sec-WebSocket-Accept"
            raise ValueError(msg)

        # Extract optional fields
        subprotocol = headers.get("sec-websocket-protocol")
        extensions_str = headers.get("sec-websocket-extensions", "")
        extensions = (
            [e.strip() for e in extensions_str.split(";")] if extensions_str else []
        )

        return HandshakeResult(
            status=status,
            headers=headers,
            subprotocol=subprotocol,
            extensions=extensions,
        )


@dataclass
class HandshakeResult:
    """Result of a successful WebSocket handshake."""

    status: int
    headers: dict[str, str]
    subprotocol: str | None
    extensions: list[str]


def validate_utf8(data: bytes) -> bool:
    """Check if data is valid UTF-8.

    Args:
        data: The bytes to validate.

    Returns:
        True if data is valid UTF-8, False otherwise.
    """
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def parse_deflate_params(
    extension_str: str,
) -> tuple[bool, bool, int, int]:
    """Parse permessage-deflate extension parameters.

    Args:
        extension_str: The Sec-WebSocket-Extensions header value.

    Returns:
        Tuple of (client_no_context_takeover, server_no_context_takeover,
                  client_max_window_bits, server_max_window_bits).
    """
    client_no_context_takeover = False
    server_no_context_takeover = False
    client_max_window_bits = 15
    server_max_window_bits = 15

    for raw_part in extension_str.split(";"):
        token = raw_part.strip()
        if token.lower() == "permessage-deflate" or not token:
            continue

        if "=" in token:
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "client_max_window_bits":
                client_max_window_bits = int(value)
            elif key == "server_max_window_bits":
                server_max_window_bits = int(value)
        elif token == "client_no_context_takeover":
            client_no_context_takeover = True
        elif token == "server_no_context_takeover":
            server_no_context_takeover = True

    return (
        client_no_context_takeover,
        server_no_context_takeover,
        client_max_window_bits,
        server_max_window_bits,
    )


_DEFLATE_TRAILER = b"\x00\x00\xff\xff"


class Deflater:
    """Pure-Python permessage-deflate compressor/decompressor.

    Uses Python's zlib module with raw deflate (wbits=-15).
    """

    def __init__(
        self,
        client_no_context_takeover: bool = False,
        server_no_context_takeover: bool = False,
        client_max_window_bits: int = 15,
        server_max_window_bits: int = 15,
    ) -> None:
        """Create a new Deflater.

        Args:
            client_no_context_takeover: Reset compressor after each message.
            server_no_context_takeover: Reset decompressor after each message.
            client_max_window_bits: LZ77 window size for compression (9-15).
            server_max_window_bits: LZ77 window size for decompression (9-15).
        """
        if not (9 <= client_max_window_bits <= 15):
            msg = "client_max_window_bits must be between 9 and 15"
            raise ValueError(msg)
        if not (9 <= server_max_window_bits <= 15):
            msg = "server_max_window_bits must be between 9 and 15"
            raise ValueError(msg)

        self._client_no_context_takeover = client_no_context_takeover
        self._server_no_context_takeover = server_no_context_takeover
        self._client_max_window_bits = client_max_window_bits
        self._server_max_window_bits = server_max_window_bits

        self._compressor = zlib.compressobj(
            zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -client_max_window_bits
        )
        self._decompressor = zlib.decompressobj(-server_max_window_bits)

    @property
    def client_no_context_takeover(self) -> bool:
        """Get client_no_context_takeover setting."""
        return self._client_no_context_takeover

    @property
    def server_no_context_takeover(self) -> bool:
        """Get server_no_context_takeover setting."""
        return self._server_no_context_takeover

    @property
    def client_max_window_bits(self) -> int:
        """Get client_max_window_bits setting."""
        return self._client_max_window_bits

    @property
    def server_max_window_bits(self) -> int:
        """Get server_max_window_bits setting."""
        return self._server_max_window_bits

    def compress(self, data: bytes) -> bytes:
        """Compress a message payload for sending.

        Args:
            data: The payload bytes to compress.

        Returns:
            Compressed bytes with trailing sync marker stripped.
        """
        compressed = self._compressor.compress(data)
        compressed += self._compressor.flush(zlib.Z_SYNC_FLUSH)

        # Strip trailing 0x00 0x00 0xFF 0xFF per RFC 7692
        if compressed.endswith(_DEFLATE_TRAILER):
            compressed = compressed[: -len(_DEFLATE_TRAILER)]

        if self._client_no_context_takeover:
            self._compressor = zlib.compressobj(
                zlib.Z_DEFAULT_COMPRESSION,
                zlib.DEFLATED,
                -self._client_max_window_bits,
            )

        return compressed

    def decompress(self, data: bytes) -> bytes:
        """Decompress a received message payload.

        Args:
            data: The compressed payload bytes.

        Returns:
            Decompressed bytes.
        """
        # Append trailing bytes per RFC 7692
        decompressed = self._decompressor.decompress(data + _DEFLATE_TRAILER)

        if self._server_no_context_takeover:
            self._decompressor = zlib.decompressobj(-self._server_max_window_bits)

        return decompressed

    def reset_compressor(self) -> None:
        """Reset the compressor state."""
        self._compressor = zlib.compressobj(
            zlib.Z_DEFAULT_COMPRESSION,
            zlib.DEFLATED,
            -self._client_max_window_bits,
        )

    def reset_decompressor(self) -> None:
        """Reset the decompressor state."""
        self._decompressor = zlib.decompressobj(-self._server_max_window_bits)

    def __repr__(self) -> str:
        return (
            f"Deflater(client_no_context_takeover={self._client_no_context_takeover}, "
            f"server_no_context_takeover={self._server_no_context_takeover}, "
            f"client_max_window_bits={self._client_max_window_bits}, "
            f"server_max_window_bits={self._server_max_window_bits})"
        )


# Overflow policy enum for RingBuffer
class OverflowPolicy:
    """Overflow policy enumeration for RingBuffer."""

    DropOldest = 0
    DropNewest = 1
    Error = 2


class RingBuffer:
    """Pure-Python fallback for RingBuffer.

    This provides the same API as the Rust RingBuffer for when the
    Rust extension is not available.
    """

    # Class-level cache for BufferOverflowError to avoid repeated imports
    _BufferOverflowError: type | None = None

    @classmethod
    def _get_overflow_error(cls) -> type:
        """Lazily import BufferOverflowError to avoid circular imports."""
        if cls._BufferOverflowError is None:
            from wsfabric.exceptions import BufferOverflowError  # noqa: PLC0415

            cls._BufferOverflowError = BufferOverflowError
        return cls._BufferOverflowError

    def __init__(self, capacity: int, policy: str = "drop_oldest") -> None:
        """Create a new ring buffer.

        Args:
            capacity: Maximum number of items.
            policy: Overflow policy ('drop_oldest', 'drop_newest', 'error').
        """
        if capacity <= 0:
            msg = "Buffer capacity must be greater than 0"
            raise ValueError(msg)

        self._buffer: list[tuple[object, object | None] | None] = [None] * capacity
        self._head = 0
        self._tail = 0
        self._len = 0
        self._capacity = capacity
        self._policy = policy
        self._total_dropped = 0

    def push(self, item: object, sequence_id: object | None = None) -> bool:
        """Push an item onto the buffer.

        Args:
            item: The item to push.
            sequence_id: Optional sequence identifier.

        Returns:
            True if item was added, False if dropped.
        """
        if self._len == self._capacity:
            if self._policy == "drop_oldest":
                self._head = (self._head + 1) % self._capacity
                self._len -= 1
                self._total_dropped += 1
            elif self._policy == "drop_newest":
                self._total_dropped += 1
                return False
            else:  # error
                exc_cls = self._get_overflow_error()
                raise exc_cls(
                    "Buffer is full",
                    capacity=self._capacity,
                    current_size=self._len,
                )

        self._buffer[self._tail] = (item, sequence_id)
        self._tail = (self._tail + 1) % self._capacity
        self._len += 1
        return True

    def pop(self) -> object | None:
        """Pop the oldest item from the buffer."""
        if self._len == 0:
            return None

        item_tuple = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) % self._capacity
        self._len -= 1

        return item_tuple[0] if item_tuple else None

    def peek(self) -> object | None:
        """Peek at the oldest item without removing it."""
        if self._len == 0:
            return None
        item_tuple = self._buffer[self._head]
        return item_tuple[0] if item_tuple else None

    def drain(self) -> list[object]:
        """Drain all items from the buffer."""
        items: list[object] = []
        while self._len > 0:
            item = self.pop()
            if item is not None:
                items.append(item)
        return items

    def drain_with_sequences(self) -> list[tuple[object, object | None]]:
        """Drain all items with their sequence IDs."""
        items: list[tuple[object, object | None]] = []
        while self._len > 0:
            item_tuple = self._buffer[self._head]
            self._buffer[self._head] = None
            self._head = (self._head + 1) % self._capacity
            self._len -= 1
            if item_tuple is not None:
                items.append(item_tuple)
        return items

    def clear(self) -> None:
        """Clear all items from the buffer."""
        for i in range(self._capacity):
            self._buffer[i] = None
        self._head = 0
        self._tail = 0
        self._len = 0

    def reset_dropped_counter(self) -> None:
        """Reset the dropped counter."""
        self._total_dropped = 0

    @property
    def len(self) -> int:
        """Get the number of items in the buffer."""
        return self._len

    @property
    def capacity(self) -> int:
        """Get the buffer capacity."""
        return self._capacity

    @property
    def is_empty(self) -> bool:
        """Check if the buffer is empty."""
        return self._len == 0

    @property
    def is_full(self) -> bool:
        """Check if the buffer is full."""
        return self._len == self._capacity

    @property
    def fill_ratio(self) -> float:
        """Get the fill ratio (0.0 to 1.0)."""
        return self._len / self._capacity if self._capacity > 0 else 0.0

    @property
    def total_dropped(self) -> int:
        """Get the total number of dropped messages."""
        return self._total_dropped

    @property
    def policy(self) -> str:
        """Get the overflow policy."""
        return self._policy

    def __len__(self) -> int:
        """Get the number of items in the buffer."""
        return self._len

    def __bool__(self) -> bool:
        """Return True if buffer is not empty."""
        return self._len > 0

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"RingBuffer(capacity={self._capacity}, len={self._len}, "
            f"fill_ratio={self.fill_ratio:.2f}, policy={self._policy})"
        )
