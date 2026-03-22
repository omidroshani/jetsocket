"""Throughput stress tests."""

from __future__ import annotations

import asyncio

import pytest

from jetsocket.transport import AsyncTransport, BaseTransportConfig


@pytest.mark.stress
class TestThroughput:
    """Verify high message throughput."""

    async def test_10k_messages(self, echo_server: str) -> None:
        """Send and receive 10K messages."""
        config = BaseTransportConfig(connect_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        try:
            total = 10_000
            for i in range(total):
                await transport.send(f"msg-{i}")
                frame = await transport.recv()
                assert frame.payload == f"msg-{i}".encode()
        finally:
            await transport.close()

    async def test_large_messages(self, echo_server: str) -> None:
        """Send and receive large messages (100KB each)."""
        config = BaseTransportConfig(connect_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        try:
            payload = b"x" * (100 * 1024)  # 100KB
            for _ in range(10):
                await transport.send(payload, binary=True)
                frame = await transport.recv()
                assert len(frame.payload) == len(payload)
        finally:
            await transport.close()

    async def test_concurrent_connections(self, echo_server: str) -> None:
        """Run 20 concurrent connections."""
        config = BaseTransportConfig(connect_timeout=5.0)

        async def worker(idx: int) -> None:
            transport = AsyncTransport(config)
            await transport.connect(echo_server)
            try:
                for j in range(50):
                    msg = f"conn-{idx}-msg-{j}"
                    await transport.send(msg)
                    frame = await transport.recv()
                    assert frame.payload.decode("utf-8") == msg
            finally:
                await transport.close()

        await asyncio.gather(*(worker(i) for i in range(20)))
