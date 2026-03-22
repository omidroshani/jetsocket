"""Tests for compression (permessage-deflate)."""

from __future__ import annotations

import pytest


class TestDeflater:
    """Tests for the Deflater class."""

    def _get_deflater(self, **kwargs: object) -> object:
        """Get a Deflater from either Rust or fallback."""
        try:
            from jetsocket._core import Deflater
        except ImportError:
            from jetsocket._core import Deflater
        return Deflater(**kwargs)

    def test_compress_decompress_roundtrip(self) -> None:
        """Test basic compress/decompress roundtrip."""
        d = self._get_deflater()
        original = b"Hello, World! This is a test of the compression engine."

        compressed = d.compress(original)
        assert len(compressed) > 0
        assert compressed != original

        decompressed = d.decompress(compressed)
        assert decompressed == original

    def test_compress_empty(self) -> None:
        """Test compressing empty data."""
        d = self._get_deflater()
        compressed = d.compress(b"")
        decompressed = d.decompress(compressed)
        assert decompressed == b""

    def test_compress_large_payload(self) -> None:
        """Test compressing a large payload."""
        d = self._get_deflater()
        original = bytes(range(256)) * 400  # 100KB repetitive data

        compressed = d.compress(original)
        assert len(compressed) < len(original)

        decompressed = d.decompress(compressed)
        assert decompressed == original

    def test_compress_incompressible_data(self) -> None:
        """Test compressing random-like data."""
        import os

        d = self._get_deflater()
        original = os.urandom(1000)

        compressed = d.compress(original)
        decompressed = d.decompress(compressed)
        assert decompressed == original

    def test_multiple_messages(self) -> None:
        """Test compressing multiple messages sequentially."""
        d = self._get_deflater()

        messages = [
            b'{"symbol":"BTCUSDT","price":"50000.00"}',
            b'{"symbol":"ETHUSDT","price":"3000.00"}',
            b'{"symbol":"BTCUSDT","price":"50001.00"}',
        ]

        for msg in messages:
            compressed = d.compress(msg)
            decompressed = d.decompress(compressed)
            assert decompressed == msg

    def test_no_context_takeover(self) -> None:
        """Test with context takeover disabled."""
        d = self._get_deflater(
            client_no_context_takeover=True,
            server_no_context_takeover=True,
        )

        msg = b"repeated message content for testing"
        compressed1 = d.compress(msg)
        decompressed1 = d.decompress(compressed1)
        assert decompressed1 == msg

        compressed2 = d.compress(msg)
        decompressed2 = d.decompress(compressed2)
        assert decompressed2 == msg

    def test_properties(self) -> None:
        """Test Deflater properties."""
        d = self._get_deflater(
            client_no_context_takeover=True,
            server_no_context_takeover=False,
            client_max_window_bits=12,
            server_max_window_bits=14,
        )

        assert d.client_no_context_takeover is True
        assert d.server_no_context_takeover is False
        assert d.client_max_window_bits == 12
        assert d.server_max_window_bits == 14

    def test_invalid_window_bits(self) -> None:
        """Test that invalid window bits raise."""
        with pytest.raises((ValueError, Exception)):
            self._get_deflater(client_max_window_bits=8)

        with pytest.raises((ValueError, Exception)):
            self._get_deflater(server_max_window_bits=16)

    def test_reset_compressor(self) -> None:
        """Test resetting the compressor."""
        d = self._get_deflater()
        msg = b"test message"

        # Compress a message to establish context
        d.compress(msg)

        # Reset and compress again
        d.reset_compressor()
        compressed = d.compress(msg)
        decompressed = d.decompress(compressed)
        assert decompressed == msg

    def test_reset_decompressor(self) -> None:
        """Test resetting the decompressor."""
        d = self._get_deflater()
        msg = b"test message"

        compressed = d.compress(msg)
        d.decompress(compressed)

        # Reset decompressor and decompress a fresh message
        d.reset_decompressor()
        d.reset_compressor()
        compressed2 = d.compress(msg)
        decompressed2 = d.decompress(compressed2)
        assert decompressed2 == msg

    def test_repr(self) -> None:
        """Test string representation."""
        d = self._get_deflater()
        r = repr(d)
        assert "Deflater" in r
        assert "client_no_context_takeover" in r


class TestParseDeflateParams:
    """Tests for parse_deflate_params."""

    def _parse(self, s: str) -> tuple[bool, bool, int, int]:
        try:
            from jetsocket._core import parse_deflate_params
        except ImportError:
            from jetsocket._core import parse_deflate_params
        return parse_deflate_params(s)

    def test_basic(self) -> None:
        """Test parsing basic extension string."""
        cnct, snct, cmwb, smwb = self._parse("permessage-deflate")
        assert cnct is False
        assert snct is False
        assert cmwb == 15
        assert smwb == 15

    def test_server_no_context_takeover(self) -> None:
        """Test parsing server_no_context_takeover."""
        cnct, snct, _cmwb, _smwb = self._parse(
            "permessage-deflate; server_no_context_takeover"
        )
        assert snct is True
        assert cnct is False

    def test_window_bits(self) -> None:
        """Test parsing window bits."""
        _cnct, _snct, cmwb, smwb = self._parse(
            "permessage-deflate; client_max_window_bits=12; server_max_window_bits=10"
        )
        assert cmwb == 12
        assert smwb == 10

    def test_full_params(self) -> None:
        """Test parsing all parameters."""
        cnct, snct, cmwb, smwb = self._parse(
            "permessage-deflate; client_no_context_takeover; "
            "server_no_context_takeover; client_max_window_bits=9"
        )
        assert cnct is True
        assert snct is True
        assert cmwb == 9
        assert smwb == 15


class TestValidateUtf8:
    """Tests for validate_utf8."""

    def _validate(self, data: bytes) -> bool:
        try:
            from jetsocket._core import validate_utf8
        except ImportError:
            from jetsocket._core import validate_utf8
        return validate_utf8(data)

    def test_valid_ascii(self) -> None:
        """Test valid ASCII."""
        assert self._validate(b"Hello, World!") is True

    def test_valid_multibyte(self) -> None:
        """Test valid multi-byte UTF-8."""
        assert self._validate("こんにちは".encode()) is True

    def test_valid_emoji(self) -> None:
        """Test valid emoji."""
        assert self._validate("🎉🚀".encode()) is True

    def test_empty(self) -> None:
        """Test empty data."""
        assert self._validate(b"") is True

    def test_invalid_bytes(self) -> None:
        """Test invalid UTF-8 bytes."""
        assert self._validate(bytes([0xFF, 0xFE])) is False

    def test_truncated_sequence(self) -> None:
        """Test truncated multi-byte sequence."""
        assert self._validate(bytes([0xC0])) is False

    def test_large_valid(self) -> None:
        """Test large valid UTF-8 payload."""
        data = ("Hello " * 10000).encode("utf-8")
        assert self._validate(data) is True
