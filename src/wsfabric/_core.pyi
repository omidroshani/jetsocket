"""Type stubs for the Rust _core module.

This file provides type hints for the Rust extension module.
"""

from __future__ import annotations

from wsfabric.types import Frame

class FrameParser:
    """WebSocket frame parser implemented in Rust."""

    def __init__(
        self,
        max_frame_size: int = 16 * 1024 * 1024,
        max_message_size: int = 64 * 1024 * 1024,
    ) -> None: ...
    def feed(self, data: bytes) -> tuple[list[Frame], int]: ...
    def encode(self, opcode: int, payload: bytes, mask: bool, fin: bool) -> bytes: ...
    def encode_close(self, code: int, reason: str, mask: bool) -> bytes: ...

class HandshakeResult:
    """Result of parsing a WebSocket handshake response."""

    @property
    def subprotocol(self) -> str | None: ...
    @property
    def extensions(self) -> list[str]: ...

class Handshake:
    """WebSocket handshake handler implemented in Rust."""

    def __init__(
        self,
        host: str,
        resource: str,
        *,
        origin: str | None = None,
        subprotocols: list[str] | None = None,
        extensions: list[str] | None = None,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None: ...
    def build_request(self) -> bytes: ...
    def parse_response(self, data: bytes) -> HandshakeResult: ...

def apply_mask(data: bytes, mask: bytes) -> bytes:
    """Apply WebSocket masking to data."""

def generate_key() -> str:
    """Generate a random Sec-WebSocket-Key."""

def compute_accept(key: str) -> str:
    """Compute the Sec-WebSocket-Accept value."""
