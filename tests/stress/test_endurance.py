"""Endurance tests for sustained WebSocket operation."""

from __future__ import annotations

import os
import time

import pytest

from jetsocket.transport import AsyncTransport, BaseTransportConfig

DURATION = int(os.environ.get("JETSOCKET_STRESS_DURATION", "5"))


@pytest.mark.stress
class TestEndurance:
    """Verify sustained operation without errors."""

    async def test_continuous_send_recv(self, echo_server: str) -> None:
        """Run continuous send/receive for DURATION seconds."""
        config = BaseTransportConfig(connect_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        try:
            count = 0
            start = time.monotonic()
            while time.monotonic() - start < DURATION:
                msg = f"message-{count}"
                await transport.send(msg)
                frame = await transport.recv()
                assert frame.payload.decode("utf-8") == msg
                count += 1

            assert count > 0, "Should have sent at least one message"
        finally:
            await transport.close()

    async def test_high_frequency_small_messages(self, echo_server: str) -> None:
        """Send many small messages rapidly."""
        config = BaseTransportConfig(connect_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        try:
            for i in range(1000):
                await transport.send(f"m{i}")
                frame = await transport.recv()
                assert frame.payload == f"m{i}".encode()
        finally:
            await transport.close()
