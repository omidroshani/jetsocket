"""Integration tests for Bybit WebSocket API."""

from __future__ import annotations

import asyncio
import json

import pytest

from wsfabric.transport import AsyncTransport, BaseTransportConfig

from .conftest import skip_no_network

BYBIT_WS = "wss://stream.bybit.com/v5/public/spot"


@skip_no_network
@pytest.mark.exchange
@pytest.mark.integration
class TestBybitWebSocket:
    """Test against Bybit public WebSocket streams."""

    async def test_connect_subscribe_receive(self) -> None:
        """Connect, subscribe to tickers, receive a message."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(BYBIT_WS)
        try:
            # Subscribe
            sub = json.dumps(
                {"op": "subscribe", "args": ["tickers.BTCUSDT"]}
            )
            await transport.send(sub)

            # Read subscription confirmation + first data message
            messages = []
            for _ in range(3):
                frame = await asyncio.wait_for(transport.recv(), timeout=15.0)
                messages.append(json.loads(frame.payload))

            # Should have received at least one message
            assert len(messages) > 0
        finally:
            await transport.close()
