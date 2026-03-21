"""Integration tests for OKX WebSocket API."""

from __future__ import annotations

import asyncio
import json

import pytest

from wsfabric.transport import AsyncTransport, BaseTransportConfig

from .conftest import skip_no_network

OKX_WS = "wss://ws.okx.com:8443/ws/v5/public"


@skip_no_network
@pytest.mark.exchange
@pytest.mark.integration
class TestOKXWebSocket:
    """Test against OKX public WebSocket streams."""

    async def test_connect_subscribe_receive(self) -> None:
        """Connect, subscribe to tickers, receive a message."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(OKX_WS)
        try:
            sub = json.dumps(
                {
                    "op": "subscribe",
                    "args": [{"channel": "tickers", "instId": "BTC-USDT"}],
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
