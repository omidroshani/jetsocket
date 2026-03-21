"""Memory leak detection tests."""

from __future__ import annotations

import gc
import tracemalloc

import pytest

from wsfabric.transport import AsyncTransport, BaseTransportConfig

try:
    from wsfabric._core import Deflater, RingBuffer
except ImportError:
    from wsfabric._core_fallback import Deflater, RingBuffer  # type: ignore[assignment]


def _get_memory() -> int:
    """Force GC and return current traced memory in bytes."""
    gc.collect()
    gc.collect()
    current, _ = tracemalloc.get_traced_memory()
    return current


@pytest.mark.stress
class TestMemoryLeaks:
    """Verify no memory leaks during sustained operation."""

    async def test_recv_loop_no_leak(self, echo_server: str) -> None:
        """Memory doesn't grow unboundedly during recv loop."""
        config = BaseTransportConfig(connect_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        tracemalloc.start()
        try:
            # Warm up
            for i in range(200):
                await transport.send(f"warmup-{i}")
                await transport.recv()

            baseline = _get_memory()

            # Main loop
            for i in range(2000):
                await transport.send(f"test-{i}")
                await transport.recv()

            final = _get_memory()
            growth = final - baseline

            # Allow up to 5MB growth (generous for CI stability)
            assert growth < 5 * 1024 * 1024, (
                f"Memory grew {growth / 1024 / 1024:.1f}MB during recv loop"
            )
        finally:
            tracemalloc.stop()
            await transport.close()

    async def test_connect_disconnect_no_leak(self, echo_server: str) -> None:
        """Memory doesn't grow during repeated connect/disconnect."""
        config = BaseTransportConfig(connect_timeout=5.0)

        tracemalloc.start()
        try:
            # Warm up
            for _ in range(10):
                t = AsyncTransport(config)
                await t.connect(echo_server)
                await t.close()

            baseline = _get_memory()

            for _ in range(100):
                t = AsyncTransport(config)
                await t.connect(echo_server)
                await t.send("test")
                await t.recv()
                await t.close()

            final = _get_memory()
            growth = final - baseline

            assert growth < 2 * 1024 * 1024, (
                f"Memory grew {growth / 1024 / 1024:.1f}MB during connect/disconnect"
            )
        finally:
            tracemalloc.stop()

    def test_buffer_fill_drain_no_leak(self) -> None:
        """RingBuffer fill/drain cycles don't leak memory."""
        tracemalloc.start()
        try:
            buf = RingBuffer(1000, "drop_oldest")

            # Warm up
            for _ in range(10):
                for j in range(1000):
                    buf.push(f"item-{j}")
                buf.drain()

            baseline = _get_memory()

            for _ in range(500):
                for j in range(1000):
                    buf.push(f"item-{j}")
                buf.drain()

            final = _get_memory()
            growth = final - baseline

            assert growth < 1 * 1024 * 1024, (
                f"Memory grew {growth / 1024 / 1024:.1f}MB during buffer cycles"
            )
        finally:
            tracemalloc.stop()

    def test_compression_no_leak(self) -> None:
        """Deflater compress/decompress cycles don't leak memory."""
        d = Deflater()
        data = b'{"symbol":"BTCUSDT","price":"50000.00"}' * 10

        tracemalloc.start()
        try:
            # Warm up
            for _ in range(100):
                c = d.compress(data)
                d.decompress(c)

            baseline = _get_memory()

            for _ in range(5000):
                c = d.compress(data)
                d.decompress(c)

            final = _get_memory()
            growth = final - baseline

            assert growth < 1 * 1024 * 1024, (
                f"Memory grew {growth / 1024 / 1024:.1f}MB during compression"
            )
        finally:
            tracemalloc.stop()
