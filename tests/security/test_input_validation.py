"""Security tests for input validation."""

from __future__ import annotations

import struct

import pytest

from jetsocket._core import FrameParser


@pytest.mark.security
class TestInputValidation:
    """Verify protocol input validation prevents abuse."""

    def test_max_frame_size_enforced(self) -> None:
        """Verify FrameParser rejects frames exceeding max_frame_size."""
        parser = FrameParser(max_frame_size=1024)
        # Build header claiming 2048-byte payload (extended 16-bit length)
        header = bytes([0x81, 0x7E]) + struct.pack(">H", 2048)
        payload = b"\x00" * 2048
        with pytest.raises(ValueError, match=r"[Tt]oo [Ll]arge|[Ff]rame"):
            parser.feed(header + payload)

    def test_control_frame_max_125_bytes(self) -> None:
        """Verify control frames reject payloads > 125 bytes."""
        parser = FrameParser()
        # Ping frame (0x89) with 126-byte extended length
        header = bytes([0x89, 0x7E]) + struct.pack(">H", 130)
        payload = b"\x00" * 130
        with pytest.raises(ValueError, match=r"[Cc]ontrol|[Tt]oo [Ll]arge"):
            parser.feed(header + payload)

    def test_fragmented_control_frame_rejected(self) -> None:
        """Verify fragmented control frames are rejected per RFC 6455."""
        parser = FrameParser()
        # Ping frame with FIN=0 (0x09 instead of 0x89)
        data = bytes([0x09, 0x05]) + b"Hello"
        with pytest.raises(ValueError, match=r"[Ff]ragment|[Cc]ontrol"):
            parser.feed(data)

    def test_reserved_bits_rsv2_rejected(self) -> None:
        """Verify RSV2 bit causes protocol error."""
        parser = FrameParser()
        # Text frame with RSV2 set (0xA1 = 1010_0001)
        data = bytes([0xA1, 0x05]) + b"Hello"
        with pytest.raises(ValueError, match=r"[Rr]eserved|RSV"):
            parser.feed(data)

    def test_reserved_bits_rsv3_rejected(self) -> None:
        """Verify RSV3 bit causes protocol error."""
        parser = FrameParser()
        # Text frame with RSV3 set (0x91 = 1001_0001)
        data = bytes([0x91, 0x05]) + b"Hello"
        with pytest.raises(ValueError, match=r"[Rr]eserved|RSV"):
            parser.feed(data)

    def test_rsv1_allowed_for_compression(self) -> None:
        """Verify RSV1 bit is allowed (used for permessage-deflate)."""
        parser = FrameParser()
        # Text frame with RSV1 set (0xC1 = 1100_0001)
        data = bytes([0xC1, 0x05]) + b"Hello"
        # Should NOT raise — RSV1 is allowed for compression
        frames, _ = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].rsv1 is True

    def test_invalid_opcode_3_rejected(self) -> None:
        """Verify reserved opcodes 3-7 are rejected."""
        parser = FrameParser()
        # Opcode 3 (reserved)
        data = bytes([0x83, 0x05]) + b"Hello"
        with pytest.raises(ValueError, match=r"[Oo]pcode|[Ii]nvalid"):
            parser.feed(data)

    def test_invalid_opcode_0xB_rejected(self) -> None:
        """Verify reserved opcodes B-F are rejected."""
        parser = FrameParser()
        # Opcode 0xB (reserved control)
        data = bytes([0x8B, 0x05]) + b"Hello"
        with pytest.raises(ValueError, match=r"[Oo]pcode|[Ii]nvalid"):
            parser.feed(data)

    def test_close_frame_with_1_byte_payload_valid(self) -> None:
        """Verify close frame with 1-byte payload is handled."""
        parser = FrameParser()
        # Close frame with 1-byte payload (invalid per RFC but shouldn't crash)
        data = bytes([0x88, 0x01, 0x00])
        # Should either parse or raise ValueError, but NOT crash
        import contextlib

        with contextlib.suppress(ValueError):
            parser.feed(data)

    def test_zero_length_frame(self) -> None:
        """Verify zero-length frames are handled."""
        parser = FrameParser()
        # Text frame with 0-byte payload
        data = bytes([0x81, 0x00])
        frames, consumed = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].payload == b""
        assert consumed == 2
