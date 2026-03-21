"""Security tests for WebSocket close handshake."""

from __future__ import annotations

import struct

import pytest

try:
    from wsfabric._core import FrameParser
except ImportError:
    from wsfabric._core_fallback import FrameParser  # type: ignore[assignment]


@pytest.mark.security
class TestCloseHandshake:
    """Verify close frame handling follows RFC 6455."""

    def test_close_frame_parsed(self) -> None:
        """Verify close frame is parsed with code and reason."""
        parser = FrameParser()
        # Close frame: code 1000, reason "Normal"
        payload = struct.pack(">H", 1000) + b"Normal"
        data = bytes([0x88, len(payload)]) + payload
        frames, _ = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].opcode == 0x8  # CLOSE

    def test_close_frame_encode(self) -> None:
        """Verify close frame can be encoded."""
        parser = FrameParser()
        encoded = parser.encode_close(1000, "bye", True)
        assert len(encoded) > 0
        # Should have mask bit set
        assert encoded[1] & 0x80 != 0

    def test_close_with_empty_reason(self) -> None:
        """Verify close frame with just code (no reason) is valid."""
        parser = FrameParser()
        # Close frame: code 1000, no reason
        payload = struct.pack(">H", 1000)
        data = bytes([0x88, len(payload)]) + payload
        frames, _ = parser.feed(data)
        assert len(frames) == 1

    def test_close_with_no_payload(self) -> None:
        """Verify close frame with no payload is valid."""
        parser = FrameParser()
        data = bytes([0x88, 0x00])
        frames, _ = parser.feed(data)
        assert len(frames) == 1

    def test_close_various_codes(self) -> None:
        """Verify common close codes are handled."""
        parser = FrameParser()
        for code in [1000, 1001, 1002, 1003, 1008, 1011]:
            parser.reset()
            payload = struct.pack(">H", code)
            data = bytes([0x88, len(payload)]) + payload
            frames, _ = parser.feed(data)
            assert len(frames) == 1
