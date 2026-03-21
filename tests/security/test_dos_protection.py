"""Security tests for denial-of-service protection."""

from __future__ import annotations

import pytest

try:
    from wsfabric._core import Deflater, FrameParser, RingBuffer
except ImportError:
    from wsfabric._core_fallback import (  # type: ignore[assignment]
        Deflater,
        FrameParser,
        RingBuffer,
    )


@pytest.mark.security
class TestDOSProtection:
    """Verify resource limits prevent denial-of-service."""

    def test_buffer_enforces_capacity(self) -> None:
        """Verify RingBuffer enforces capacity limits."""
        buf = RingBuffer(10, "drop_oldest")
        for i in range(100):
            buf.push(i)
        assert len(buf) == 10

    def test_buffer_error_policy_raises(self) -> None:
        """Verify RingBuffer error policy raises on overflow."""
        buf = RingBuffer(5, "error")
        for i in range(5):
            buf.push(i)
        with pytest.raises(Exception):
            buf.push(999)

    def test_parser_handles_many_incomplete_frames(self) -> None:
        """Verify parser doesn't crash with many incomplete frame headers."""
        parser = FrameParser(max_frame_size=1024)
        # Feed 1000 incomplete 2-byte headers
        for _ in range(1000):
            frames, _ = parser.feed(bytes([0x81]))
        # Parser should still work after reset
        parser.reset()
        data = bytes([0x81, 0x05]) + b"Hello"
        frames, _ = parser.feed(data)
        assert len(frames) == 1

    def test_decompression_bomb_bounded(self) -> None:
        """Verify decompression of highly-compressed data doesn't OOM.

        Creates data that compresses very well (all zeros) and verifies
        the decompressor handles it without crashing.
        """
        d = Deflater()
        # 1MB of zeros compresses to ~1KB
        big_data = b"\x00" * (1024 * 1024)
        compressed = d.compress(big_data)
        assert len(compressed) < len(big_data)

        # Decompression should succeed and produce correct output
        decompressed = d.decompress(compressed)
        assert len(decompressed) == len(big_data)
        assert decompressed == big_data

    def test_parser_max_frame_size_prevents_allocation(self) -> None:
        """Verify max_frame_size prevents huge memory allocation.

        The parser should reject the frame at the header level before
        trying to allocate payload memory.
        """
        parser = FrameParser(max_frame_size=1024)
        # Header claiming 1GB payload (64-bit extended length)
        header = bytes([0x82, 0x7F]) + (1_000_000_000).to_bytes(8, "big")
        # Feed just the header — should raise before allocating 1GB
        with pytest.raises(ValueError, match=r"[Tt]oo [Ll]arge|[Ff]rame"):
            parser.feed(header)

    def test_rapid_frame_parsing_no_crash(self) -> None:
        """Verify rapid parsing of many small frames doesn't crash."""
        parser = FrameParser()
        frame = bytes([0x81, 0x01, 0x41])  # Text frame "A"
        # Parse 10000 frames
        for _ in range(10000):
            frames, _ = parser.feed(frame)
            assert len(frames) == 1
