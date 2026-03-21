"""Integration tests for Kraken WebSocket API."""

from __future__ import annotations

import asyncio
import json

import pytest

from wsfabric.transport import AsyncTransport, BaseTransportConfig

from .conftest import skip_no_network

KRAKEN_WS = "wss://ws.kraken.com/v2"


@skip_no_network
@pytest.mark.exchange
@pytest.mark.integration
class TestKrakenWebSocket:
    """Test against Kraken public WebSocket streams."""

    async def test_connect_subscribe_receive(self) -> None:
        """Connect, subscribe to ticker, receive a message."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(KRAKEN_WS)
        try:
            sub = json.dumps(
                {
                    "method": "subscribe",
                    "params": {
                        "channel": "ticker",
                        "symbol": ["BTC/USD"],
                    },
                }
            )
            await transport.send(sub)

            messages = []
            for _ in range(3):
                frame = await asyncio.wait_for(transport.recv(), timeout=15.0)
                messages.append(json.loads(frame.payload))

            assert len(messages) > 0
        finally:
            await transport.close()
