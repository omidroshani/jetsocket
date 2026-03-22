"""Benchmark tests comparing Rust vs fallback performance.

Uses pytest-benchmark to measure and compare the performance
of the Rust extension module against the pure-Python fallback.

Run with: uv run pytest tests/unit/test_benchmarks.py --benchmark-only
"""

from __future__ import annotations

import os

import pytest

from wsfabric._core import (
    Deflater as FallbackDeflater,
)
from wsfabric._core import (
    FrameParser as FallbackFrameParser,
)
from wsfabric._core import (
    apply_mask as fallback_apply_mask,
)
from wsfabric._core import (
    validate_utf8 as fallback_validate_utf8,
)

try:
    from wsfabric._core import Deflater as RustDeflater
    from wsfabric._core import FrameParser as RustFrameParser
    from wsfabric._core import apply_mask as rust_apply_mask
    from wsfabric._core import validate_utf8 as rust_validate_utf8

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

SMALL = b"Hello, World! " * 4  # 56 bytes
MEDIUM = b"x" * 1024  # 1 KB
LARGE = os.urandom(65536)  # 64 KB
JSON_DATA = b'{"symbol":"BTCUSDT","price":"50000.00","qty":"0.001"}' * 20
MASK_KEY = (0x37, 0xFA, 0x21, 0x3D)


# --- Masking ---


@pytest.mark.benchmark(group="mask")
class TestMaskBenchmarks:
    """Benchmark masking performance."""

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_mask_small(self, benchmark: object) -> None:
        """Benchmark Rust masking on small payload."""
        benchmark(rust_apply_mask, SMALL, MASK_KEY)  # type: ignore[operator]

    def test_fallback_mask_small(self, benchmark: object) -> None:
        """Benchmark fallback masking on small payload."""
        benchmark(fallback_apply_mask, SMALL, MASK_KEY)  # type: ignore[operator]

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_mask_large(self, benchmark: object) -> None:
        """Benchmark Rust masking on large payload."""
        benchmark(rust_apply_mask, LARGE, MASK_KEY)  # type: ignore[operator]

    def test_fallback_mask_large(self, benchmark: object) -> None:
        """Benchmark fallback masking on large payload."""
        benchmark(fallback_apply_mask, LARGE, MASK_KEY)  # type: ignore[operator]


# --- Frame Encoding ---


@pytest.mark.benchmark(group="frame-encode")
class TestFrameEncodeBenchmarks:
    """Benchmark frame encoding performance."""

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_encode_small(self, benchmark: object) -> None:
        """Benchmark Rust frame encoding on small payload."""
        parser = RustFrameParser()
        benchmark(parser.encode, 0x01, SMALL, True, True)  # type: ignore[operator]

    def test_fallback_encode_small(self, benchmark: object) -> None:
        """Benchmark fallback frame encoding on small payload."""
        from wsfabric._core import Opcode

        parser = FallbackFrameParser()
        benchmark(parser.encode, Opcode.TEXT, SMALL, True, True)  # type: ignore[operator]

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_encode_large(self, benchmark: object) -> None:
        """Benchmark Rust frame encoding on large payload."""
        parser = RustFrameParser()
        benchmark(parser.encode, 0x02, LARGE, True, True)  # type: ignore[operator]

    def test_fallback_encode_large(self, benchmark: object) -> None:
        """Benchmark fallback frame encoding on large payload."""
        from wsfabric._core import Opcode

        parser = FallbackFrameParser()
        benchmark(parser.encode, Opcode.BINARY, LARGE, True, True)  # type: ignore[operator]


# --- Compression ---


@pytest.mark.benchmark(group="compress")
class TestCompressBenchmarks:
    """Benchmark compression performance."""

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_compress_json(self, benchmark: object) -> None:
        """Benchmark Rust compression on JSON data."""
        d = RustDeflater()
        benchmark(d.compress, JSON_DATA)  # type: ignore[operator]

    def test_fallback_compress_json(self, benchmark: object) -> None:
        """Benchmark fallback compression on JSON data."""
        d = FallbackDeflater()
        benchmark(d.compress, JSON_DATA)  # type: ignore[operator]

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_compress_large(self, benchmark: object) -> None:
        """Benchmark Rust compression on large payload."""
        d = RustDeflater()
        benchmark(d.compress, LARGE)  # type: ignore[operator]

    def test_fallback_compress_large(self, benchmark: object) -> None:
        """Benchmark fallback compression on large payload."""
        d = FallbackDeflater()
        benchmark(d.compress, LARGE)  # type: ignore[operator]


# --- Decompression ---


@pytest.mark.benchmark(group="decompress")
class TestDecompressBenchmarks:
    """Benchmark decompression performance."""

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_decompress_json(self, benchmark: object) -> None:
        """Benchmark Rust decompression of compressed JSON."""
        d = RustDeflater()
        compressed = d.compress(JSON_DATA)
        benchmark(d.decompress, compressed)  # type: ignore[operator]

    def test_fallback_decompress_json(self, benchmark: object) -> None:
        """Benchmark fallback decompression of compressed JSON."""
        d = FallbackDeflater()
        compressed = d.compress(JSON_DATA)
        benchmark(d.decompress, compressed)  # type: ignore[operator]


# --- UTF-8 Validation ---


@pytest.mark.benchmark(group="utf8")
class TestUtf8Benchmarks:
    """Benchmark UTF-8 validation performance."""

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_utf8_medium(self, benchmark: object) -> None:
        """Benchmark Rust UTF-8 validation on medium text."""
        data = ("Hello, World! " * 100).encode()
        benchmark(rust_validate_utf8, data)  # type: ignore[operator]

    def test_fallback_utf8_medium(self, benchmark: object) -> None:
        """Benchmark fallback UTF-8 validation on medium text."""
        data = ("Hello, World! " * 100).encode()
        benchmark(fallback_validate_utf8, data)  # type: ignore[operator]

    @pytest.mark.skipif(not HAS_RUST, reason="Rust extension not available")
    def test_rust_utf8_large(self, benchmark: object) -> None:
        """Benchmark Rust UTF-8 validation on large multi-byte text."""
        data = ("こんにちは世界 " * 1000).encode()
        benchmark(rust_validate_utf8, data)  # type: ignore[operator]

    def test_fallback_utf8_large(self, benchmark: object) -> None:
        """Benchmark fallback UTF-8 validation on large multi-byte text."""
        data = ("こんにちは世界 " * 1000).encode()
        benchmark(fallback_validate_utf8, data)  # type: ignore[operator]
