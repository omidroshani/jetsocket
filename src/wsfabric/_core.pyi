"""Type stubs for the Cython _core extension module."""

from __future__ import annotations

from enum import IntEnum

class Opcode(IntEnum):
    """WebSocket frame opcodes."""

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA

    @property
    def is_control_frame(self) -> bool: ...
    @property
    def is_data_frame(self) -> bool: ...

class Frame:
    """A parsed WebSocket frame."""

    @property
    def opcode(self) -> Opcode: ...
    @property
    def fin(self) -> bool: ...
    @property
    def rsv1(self) -> bool: ...
    @property
    def rsv2(self) -> bool: ...
    @property
    def rsv3(self) -> bool: ...
    @property
    def payload(self) -> bytes: ...
    @property
    def payload_len(self) -> int: ...
    def as_text(self) -> str: ...

class FrameParser:
    """WebSocket frame parser implemented in Cython."""

    def __init__(
        self,
        max_frame_size: int = 16 * 1024 * 1024,
        max_message_size: int = 64 * 1024 * 1024,
    ) -> None: ...
    def feed(self, data: bytes) -> tuple[list[Frame], int]: ...
    def encode(
        self,
        opcode: int,
        payload: bytes,
        mask: bool = True,
        fin: bool = True,
        rsv1: bool = False,
    ) -> bytes: ...
    def encode_close(
        self, code: int = 1000, reason: str = "", mask: bool = True
    ) -> bytes: ...
    def reset(self) -> None: ...

class HandshakeResult:
    """Result of parsing a WebSocket handshake response."""

    @property
    def status(self) -> int: ...
    @property
    def headers(self) -> dict[str, str]: ...
    @property
    def subprotocol(self) -> str | None: ...
    @property
    def extensions(self) -> list[str]: ...

class Handshake:
    """WebSocket handshake handler."""

    def __init__(
        self,
        host: str,
        path: str,
        origin: str | None = None,
        subprotocols: list[str] | None = None,
        extensions: list[str] | None = None,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None: ...
    @property
    def key(self) -> str: ...
    def build_request(self) -> bytes: ...
    def parse_response(self, data: bytes) -> HandshakeResult: ...

class Deflater:
    """permessage-deflate compressor/decompressor."""

    def __init__(
        self,
        client_no_context_takeover: bool = False,
        server_no_context_takeover: bool = False,
        client_max_window_bits: int = 15,
        server_max_window_bits: int = 15,
    ) -> None: ...
    def compress(self, data: bytes) -> bytes: ...
    def decompress(self, data: bytes) -> bytes: ...
    def reset_compressor(self) -> None: ...
    def reset_decompressor(self) -> None: ...
    @property
    def client_no_context_takeover(self) -> bool: ...
    @property
    def server_no_context_takeover(self) -> bool: ...
    @property
    def client_max_window_bits(self) -> int: ...
    @property
    def server_max_window_bits(self) -> int: ...

class OverflowPolicy:
    """Overflow policy for RingBuffer."""

    DropOldest: int
    DropNewest: int
    Error: int

class RingBuffer:
    """Ring buffer with configurable overflow policy."""

    def __init__(self, capacity: int, policy: str = "drop_oldest") -> None: ...
    def push(self, item: object, sequence_id: object | None = None) -> bool: ...
    def pop(self) -> object | None: ...
    def peek(self) -> object | None: ...
    def drain(self) -> list[object]: ...
    def drain_with_sequences(self) -> list[tuple[object, object | None]]: ...
    def clear(self) -> None: ...
    def reset_dropped_counter(self) -> None: ...
    @property
    def len(self) -> int: ...
    @property
    def is_empty(self) -> bool: ...
    @property
    def capacity(self) -> int: ...
    @property
    def is_full(self) -> bool: ...
    @property
    def fill_ratio(self) -> float: ...
    @property
    def total_dropped(self) -> int: ...
    @property
    def policy(self) -> OverflowPolicy: ...
    def __len__(self) -> int: ...
    def __bool__(self) -> bool: ...

def apply_mask(data: bytes, mask: bytes | tuple[int, int, int, int]) -> bytes:
    """Apply WebSocket masking to data."""

def generate_key() -> str:
    """Generate a random Sec-WebSocket-Key."""

def validate_accept(key: str, accept: str) -> bool:
    """Validate the Sec-WebSocket-Accept header value."""

def validate_utf8(data: bytes) -> bool:
    """UTF-8 validation."""

def parse_deflate_params(
    extension_str: str,
) -> tuple[bool, bool, int, int]:
    """Parse permessage-deflate extension parameters."""
