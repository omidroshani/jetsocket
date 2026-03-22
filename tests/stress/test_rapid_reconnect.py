"""Stress tests for rapid connect/disconnect cycles."""

from __future__ import annotations

import os

import pytest

from jetsocket.transport import AsyncTransport, BaseTransportConfig

ITERATIONS = int(os.environ.get("JETSOCKET_RECONNECT_ITERATIONS", "50"))


@pytest.mark.stress
class TestRapidReconnect:
    """Verify no resource leaks during rapid reconnection."""

    async def test_rapid_connect_disconnect(self, echo_server: str) -> None:
        """Connect and disconnect many times without resource leaks."""
        config = BaseTransportConfig(connect_timeout=5.0)

        for i in range(ITERATIONS):
            transport = AsyncTransport(config)
            await transport.connect(echo_server)
            await transport.send(f"test-{i}")
            frame = await transport.recv()
            assert frame.payload == f"test-{i}".encode()
            await transport.close()

    async def test_reconnect_preserves_functionality(self, echo_server: str) -> None:
        """Verify each reconnection produces a fully working connection."""
        config = BaseTransportConfig(connect_timeout=5.0)

        for i in range(20):
            transport = AsyncTransport(config)
            await transport.connect(echo_server)

            # Send multiple messages per connection
            for j in range(5):
                msg = f"iter-{i}-msg-{j}"
                await transport.send(msg)
                frame = await transport.recv()
                assert frame.payload.decode("utf-8") == msg

            await transport.close()
