# cython: language_level=3, boundscheck=False, wraparound=False
"""JetSocket Core — Cython-powered WebSocket primitives.

High-performance WebSocket frame parsing, masking, compression,
handshake utilities, and ring buffer.
"""

import base64
import hashlib
import os
import struct
import zlib
from enum import IntEnum
from libc.string cimport memcpy, memset
from libc.stdint cimport uint32_t, uint64_t

# WebSocket GUID for accept key calculation (RFC 6455)
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_DEFLATE_TRAILER = b"\x00\x00\xff\xff"


# ==========================================================================
# Opcode
# ==========================================================================

class Opcode(IntEnum):
    """WebSocket frame opcodes."""
    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA

    @property
    def is_control_frame(self):
        return self >= 0x8

    @property
    def is_data_frame(self):
        return self <= 0x2


# ==========================================================================
# Masking (C-speed XOR)
# ==========================================================================

cdef void _apply_mask_c(unsigned char *data, Py_ssize_t length,
                        unsigned char *mask) noexcept nogil:
    """Apply WebSocket mask in-place using word-at-a-time XOR."""
    cdef Py_ssize_t i = 0
    cdef uint32_t mask32
    cdef uint64_t mask64

    # Build 32-bit and 64-bit masks
    memcpy(&mask32, mask, 4)
    mask64 = (<uint64_t>mask32) | ((<uint64_t>mask32) << 32)

    # Process 8 bytes at a time
    while i + 8 <= length:
        (<uint64_t*>(data + i))[0] ^= mask64
        i += 8

    # Process 4 bytes at a time
    while i + 4 <= length:
        (<uint32_t*>(data + i))[0] ^= mask32
        i += 4

    # Remaining bytes
    while i < length:
        data[i] ^= mask[i % 4]
        i += 1


def apply_mask(data, mask):
    """Apply WebSocket masking to data.

    Args:
        data: The data to mask/unmask (bytes).
        mask: A 4-byte masking key (bytes or tuple).

    Returns:
        The masked/unmasked data as bytes.
    """
    cdef bytes mask_bytes
    if isinstance(mask, (tuple, list)):
        mask_bytes = bytes(mask)
    else:
        mask_bytes = bytes(mask)

    if not data:
        return b""

    cdef bytearray result = bytearray(data)
    cdef unsigned char *result_ptr = <unsigned char*>result
    cdef unsigned char *mask_ptr = <unsigned char*>mask_bytes
    cdef Py_ssize_t length = len(result)

    with nogil:
        _apply_mask_c(result_ptr, length, mask_ptr)

    return bytes(result)


# ==========================================================================
# Frame
# ==========================================================================

class Frame:
    """A parsed WebSocket frame."""

    __slots__ = ('opcode', 'payload', 'fin', 'rsv1', 'rsv2', 'rsv3')

    def __init__(self, opcode, payload, fin=True, rsv1=False, rsv2=False, rsv3=False):
        self.opcode = opcode
        self.payload = payload
        self.fin = fin
        self.rsv1 = rsv1
        self.rsv2 = rsv2
        self.rsv3 = rsv3

    @property
    def payload_len(self):
        return len(self.payload)

    def as_text(self):
        """Decode payload as UTF-8 text."""
        return self.payload.decode("utf-8")

    def __repr__(self):
        return f"Frame(opcode={self.opcode!r}, fin={self.fin}, payload_len={len(self.payload)})"


# ==========================================================================
# FrameParser
# ==========================================================================

class FrameParser:
    """WebSocket frame parser with configurable limits.

    Sans-I/O pattern: accepts raw bytes, returns parsed frames.
    """

    def __init__(self, max_frame_size=16*1024*1024, max_message_size=64*1024*1024):
        self.max_frame_size = max_frame_size
        self.max_message_size = max_message_size
        self._buffer = bytearray()
        self._message_buffer = bytearray()
        self._message_opcode = None

    def feed(self, data):
        """Feed raw bytes into the parser.

        Returns:
            Tuple of (frames_list, bytes_consumed).
        """
        self._buffer.extend(data)
        cdef list frames = []
        cdef Py_ssize_t total_consumed = 0

        while True:
            result = self._parse_frame()
            if result is None:
                break
            frame, consumed = result
            total_consumed += consumed
            frames.append(frame)
            del self._buffer[:consumed]

        return frames, total_consumed

    def encode(self, opcode, payload, mask=True, fin=True, rsv1=False):
        """Encode a frame for sending.

        Args:
            opcode: Frame opcode (int).
            payload: Payload bytes.
            mask: Whether to mask (client-to-server).
            fin: Whether this is the final fragment.
            rsv1: Whether to set RSV1 (compression).

        Returns:
            Encoded frame as bytes.
        """
        return self._encode_frame(opcode, payload, mask, fin, rsv1)

    def encode_close(self, code=1000, reason="", mask=True):
        """Build a close frame."""
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        return self._encode_frame(Opcode.CLOSE, payload, mask, True, False)

    def reset(self):
        """Reset parser state."""
        self._buffer.clear()
        self._message_buffer.clear()
        self._message_opcode = None

    def _parse_frame(self):
        """Parse a single frame from the buffer. Returns (Frame, consumed) or None."""
        cdef bytearray buf = self._buffer
        cdef Py_ssize_t buf_len = len(buf)

        if buf_len < 2:
            return None

        cdef unsigned char first_byte = buf[0]
        cdef unsigned char second_byte = buf[1]

        cdef bint fin = (first_byte & 0x80) != 0
        cdef bint rsv1 = (first_byte & 0x40) != 0
        cdef bint rsv2 = (first_byte & 0x20) != 0
        cdef bint rsv3 = (first_byte & 0x10) != 0
        cdef unsigned char opcode_value = first_byte & 0x0F

        try:
            opcode = Opcode(opcode_value)
        except ValueError:
            raise ValueError(f"Invalid opcode: {opcode_value}")

        if rsv2 or rsv3:
            raise ValueError("Reserved bits set without extension")

        cdef bint masked = (second_byte & 0x80) != 0
        cdef unsigned char payload_len_byte = second_byte & 0x7F
        cdef Py_ssize_t mask_size = 4 if masked else 0
        cdef Py_ssize_t header_size, payload_len

        if payload_len_byte <= 125:
            header_size = 2 + mask_size
            payload_len = payload_len_byte
        elif payload_len_byte == 126:
            if buf_len < 4:
                return None
            payload_len = struct.unpack(">H", buf[2:4])[0]
            header_size = 4 + mask_size
        else:  # 127
            if buf_len < 10:
                return None
            payload_len = struct.unpack(">Q", buf[2:10])[0]
            header_size = 10 + mask_size

        if payload_len > self.max_frame_size:
            raise ValueError(f"Frame too large: {payload_len} bytes (max: {self.max_frame_size})")

        if opcode >= 0x8:  # Control frame
            if payload_len > 125:
                raise ValueError(f"Control frame too large: {payload_len} bytes (max: 125)")
            if not fin:
                raise ValueError("Fragmented control frame")

        cdef Py_ssize_t total_size = header_size + payload_len
        if buf_len < total_size:
            return None

        # Extract payload
        cdef bytearray payload_ba
        cdef bytes payload_bytes
        cdef unsigned char mask_key[4]

        if masked:
            mask_key[0] = buf[header_size - 4]
            mask_key[1] = buf[header_size - 3]
            mask_key[2] = buf[header_size - 2]
            mask_key[3] = buf[header_size - 1]
            payload_ba = bytearray(buf[header_size:total_size])
            _apply_mask_c(<unsigned char*>payload_ba, payload_len, mask_key)
            payload_bytes = bytes(payload_ba)
        else:
            payload_bytes = bytes(buf[header_size:total_size])

        frame = Frame(
            opcode=opcode,
            payload=payload_bytes,
            fin=fin,
            rsv1=rsv1,
            rsv2=rsv2,
            rsv3=rsv3,
        )

        return frame, total_size

    def _encode_frame(self, opcode, payload, bint mask, bint fin, bint rsv1=False):
        """Encode a frame directly into a single bytearray (zero-copy)."""
        cdef Py_ssize_t payload_len = len(payload)
        cdef Py_ssize_t header_len, mask_size, total_size, pos
        cdef unsigned char first_byte, mask_bit
        cdef unsigned char mask_key[4]
        cdef const unsigned char *payload_ptr

        # Calculate sizes
        mask_size = 4 if mask else 0
        if payload_len <= 125:
            header_len = 2 + mask_size
        elif payload_len <= 65535:
            header_len = 4 + mask_size
        else:
            header_len = 10 + mask_size
        total_size = header_len + payload_len

        # Single allocation
        cdef bytearray frame = bytearray(total_size)
        cdef unsigned char *buf = <unsigned char*>frame
        pos = 0

        # First byte
        first_byte = (0x80 if fin else 0x00) | int(opcode)
        if rsv1:
            first_byte |= 0x40
        buf[pos] = first_byte
        pos += 1

        # Second byte + extended length
        mask_bit = 0x80 if mask else 0x00
        if payload_len <= 125:
            buf[pos] = mask_bit | <unsigned char>payload_len
            pos += 1
        elif payload_len <= 65535:
            buf[pos] = mask_bit | 126
            pos += 1
            buf[pos] = (payload_len >> 8) & 0xFF
            buf[pos + 1] = payload_len & 0xFF
            pos += 2
        else:
            buf[pos] = mask_bit | 127
            pos += 1
            # Write 8-byte big-endian length
            for i in range(7, -1, -1):
                buf[pos + 7 - i] = (payload_len >> (i * 8)) & 0xFF
            pos += 8

        # Mask key + payload
        if mask:
            _mask_key = os.urandom(4)
            mask_key[0] = _mask_key[0]
            mask_key[1] = _mask_key[1]
            mask_key[2] = _mask_key[2]
            mask_key[3] = _mask_key[3]
            buf[pos] = mask_key[0]
            buf[pos + 1] = mask_key[1]
            buf[pos + 2] = mask_key[2]
            buf[pos + 3] = mask_key[3]
            pos += 4
            # Copy payload
            payload_ptr = <const unsigned char*>payload
            memcpy(buf + pos, payload_ptr, payload_len)
            # Mask in-place
            _apply_mask_c(buf + pos, payload_len, mask_key)
        else:
            memcpy(buf + pos, <const unsigned char*>payload, payload_len)

        return bytes(frame)


# ==========================================================================
# Handshake
# ==========================================================================

def generate_key():
    """Generate a random Sec-WebSocket-Key."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def validate_accept(key, accept):
    """Validate the Sec-WebSocket-Accept header value."""
    sha1 = hashlib.sha1()
    sha1.update(key.encode("ascii"))
    sha1.update(_WS_GUID)
    expected = base64.b64encode(sha1.digest()).decode("ascii")
    return expected == accept


class HandshakeResult:
    """Result of a successful WebSocket handshake."""
    __slots__ = ('status', 'headers', 'subprotocol', 'extensions')

    def __init__(self, status, headers, subprotocol, extensions):
        self.status = status
        self.headers = headers
        self.subprotocol = subprotocol
        self.extensions = extensions


class Handshake:
    """WebSocket handshake helper."""

    def __init__(self, host, path, origin=None, subprotocols=None,
                 extensions=None, extra_headers=None):
        self._key = generate_key()
        self._host = host
        self._path = path
        self._origin = origin
        self._subprotocols = subprotocols or []
        self._extensions = extensions or []
        self._extra_headers = extra_headers or []

    @property
    def key(self):
        return self._key

    def build_request(self):
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

    def parse_response(self, response):
        """Parse and validate the handshake response."""
        header_end = response.find(b"\r\n\r\n")
        if header_end == -1:
            raise ValueError("Invalid HTTP response")

        try:
            header_section = response[:header_end].decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Invalid HTTP response")

        lines = header_section.split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2:
            raise ValueError("Invalid HTTP response")

        try:
            status = int(parts[1])
        except ValueError:
            raise ValueError("Invalid HTTP response")

        if status != 101:
            reason = parts[2] if len(parts) > 2 else ""
            raise ValueError(f"HTTP {status}: {reason}")

        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()

        upgrade = headers.get("upgrade", "")
        if upgrade.lower() != "websocket":
            raise ValueError("Invalid Upgrade header")

        connection = headers.get("connection", "")
        if "upgrade" not in connection.lower():
            raise ValueError("Invalid Connection header")

        accept = headers.get("sec-websocket-accept")
        if accept is None:
            raise ValueError("Missing Sec-WebSocket-Accept header")

        if not validate_accept(self._key, accept):
            raise ValueError("Invalid Sec-WebSocket-Accept")

        subprotocol = headers.get("sec-websocket-protocol")
        extensions_str = headers.get("sec-websocket-extensions", "")
        extensions = [e.strip() for e in extensions_str.split(";")] if extensions_str else []

        return HandshakeResult(
            status=status, headers=headers,
            subprotocol=subprotocol, extensions=extensions,
        )


# ==========================================================================
# UTF-8 Validation
# ==========================================================================

def validate_utf8(data):
    """Check if data is valid UTF-8."""
    try:
        data.decode("utf-8")
        return True
    except (UnicodeDecodeError, AttributeError):
        return False


# ==========================================================================
# Compression (permessage-deflate via zlib)
# ==========================================================================

def parse_deflate_params(extension_str):
    """Parse permessage-deflate extension parameters.

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

    return (client_no_context_takeover, server_no_context_takeover,
            client_max_window_bits, server_max_window_bits)


class Deflater:
    """permessage-deflate compressor/decompressor using zlib."""

    def __init__(self, client_no_context_takeover=False,
                 server_no_context_takeover=False,
                 client_max_window_bits=15, server_max_window_bits=15):
        if not (9 <= client_max_window_bits <= 15):
            raise ValueError("client_max_window_bits must be between 9 and 15")
        if not (9 <= server_max_window_bits <= 15):
            raise ValueError("server_max_window_bits must be between 9 and 15")

        self._client_no_context_takeover = client_no_context_takeover
        self._server_no_context_takeover = server_no_context_takeover
        self._client_max_window_bits = client_max_window_bits
        self._server_max_window_bits = server_max_window_bits
        self._compressor = zlib.compressobj(
            zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -client_max_window_bits)
        self._decompressor = zlib.decompressobj(-server_max_window_bits)

    @property
    def client_no_context_takeover(self):
        return self._client_no_context_takeover

    @property
    def server_no_context_takeover(self):
        return self._server_no_context_takeover

    @property
    def client_max_window_bits(self):
        return self._client_max_window_bits

    @property
    def server_max_window_bits(self):
        return self._server_max_window_bits

    def compress(self, data):
        """Compress a message payload."""
        compressed = self._compressor.compress(data)
        compressed += self._compressor.flush(zlib.Z_SYNC_FLUSH)
        if compressed.endswith(_DEFLATE_TRAILER):
            compressed = compressed[:-4]
        if self._client_no_context_takeover:
            self._compressor = zlib.compressobj(
                zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED,
                -self._client_max_window_bits)
        return compressed

    def decompress(self, data):
        """Decompress a received message payload."""
        decompressed = self._decompressor.decompress(data + _DEFLATE_TRAILER)
        if self._server_no_context_takeover:
            self._decompressor = zlib.decompressobj(-self._server_max_window_bits)
        return decompressed

    def reset_compressor(self):
        self._compressor = zlib.compressobj(
            zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED,
            -self._client_max_window_bits)

    def reset_decompressor(self):
        self._decompressor = zlib.decompressobj(-self._server_max_window_bits)

    def __repr__(self):
        return (f"Deflater(client_no_context_takeover={self._client_no_context_takeover}, "
                f"server_no_context_takeover={self._server_no_context_takeover}, "
                f"client_max_window_bits={self._client_max_window_bits}, "
                f"server_max_window_bits={self._server_max_window_bits})")


# ==========================================================================
# RingBuffer
# ==========================================================================

class OverflowPolicy:
    """Overflow policy enumeration for RingBuffer."""
    DropOldest = 0
    DropNewest = 1
    Error = 2


class RingBuffer:
    """High-performance ring buffer with configurable overflow policy."""

    _BufferOverflowError = None

    @classmethod
    def _get_overflow_error(cls):
        if cls._BufferOverflowError is None:
            from jetsocket.exceptions import BufferOverflowError
            cls._BufferOverflowError = BufferOverflowError
        return cls._BufferOverflowError

    def __init__(self, capacity, policy="drop_oldest"):
        if capacity <= 0:
            raise ValueError("Buffer capacity must be greater than 0")
        self._buffer = [None] * capacity
        self._head = 0
        self._tail = 0
        self._len = 0
        self._capacity = capacity
        self._policy = policy
        self._total_dropped = 0

    def push(self, item, sequence_id=None):
        """Push an item. Returns True if added, False if dropped."""
        if self._len == self._capacity:
            if self._policy == "drop_oldest":
                self._head = (self._head + 1) % self._capacity
                self._len -= 1
                self._total_dropped += 1
            elif self._policy == "drop_newest":
                self._total_dropped += 1
                return False
            else:
                exc_cls = self._get_overflow_error()
                raise exc_cls("Buffer is full",
                              capacity=self._capacity,
                              current_size=self._len)

        self._buffer[self._tail] = (item, sequence_id)
        self._tail = (self._tail + 1) % self._capacity
        self._len += 1
        return True

    def pop(self):
        if self._len == 0:
            return None
        item_tuple = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) % self._capacity
        self._len -= 1
        return item_tuple[0] if item_tuple else None

    def peek(self):
        if self._len == 0:
            return None
        item_tuple = self._buffer[self._head]
        return item_tuple[0] if item_tuple else None

    def drain(self):
        items = []
        while self._len > 0:
            item = self.pop()
            if item is not None:
                items.append(item)
        return items

    def drain_with_sequences(self):
        items = []
        while self._len > 0:
            item_tuple = self._buffer[self._head]
            self._buffer[self._head] = None
            self._head = (self._head + 1) % self._capacity
            self._len -= 1
            if item_tuple is not None:
                items.append(item_tuple)
        return items

    def clear(self):
        for i in range(self._capacity):
            self._buffer[i] = None
        self._head = 0
        self._tail = 0
        self._len = 0

    def reset_dropped_counter(self):
        self._total_dropped = 0

    @property
    def len(self):
        return self._len

    @property
    def capacity(self):
        return self._capacity

    @property
    def is_empty(self):
        return self._len == 0

    @property
    def is_full(self):
        return self._len == self._capacity

    @property
    def fill_ratio(self):
        return self._len / self._capacity if self._capacity > 0 else 0.0

    @property
    def total_dropped(self):
        return self._total_dropped

    @property
    def policy(self):
        return self._policy

    def __len__(self):
        return self._len

    def __bool__(self):
        return self._len > 0

    def __repr__(self):
        return (f"RingBuffer(capacity={self._capacity}, len={self._len}, "
                f"fill_ratio={self.fill_ratio:.2f}, policy={self._policy})")
