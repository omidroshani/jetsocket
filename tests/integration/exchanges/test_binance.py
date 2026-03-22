"""Integration tests for Binance WebSocket API."""

from __future__ import annotations

import asyncio
import json

import pytest

from jetsocket.transport import AsyncTransport, BaseTransportConfig

from .conftest import skip_no_network

BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"


@skip_no_network
@pytest.mark.exchange
@pytest.mark.integration
class TestBinanceWebSocket:
    """Test against Binance public WebSocket streams."""

    async def test_connect_and_receive_trade(self) -> None:
        """Connect to Binance trade stream and receive a message."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(BINANCE_WS)
        try:
            frame = await asyncio.wait_for(transport.recv(), timeout=15.0)
            data = json.loads(frame.payload)
            assert "e" in data  # event type
            assert data["e"] == "trade"
            assert "s" in data  # symbol
            assert "p" in data  # price
        finally:
            await transport.close()

    async def test_message_structure(self) -> None:
        """Verify Binance trade message has expected fields."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(BINANCE_WS)
        try:
            frame = await asyncio.wait_for(transport.recv(), timeout=15.0)
            data = json.loads(frame.payload)

            expected_keys = {"e", "E", "s", "t", "p", "q", "T", "m", "M"}
            assert expected_keys.issubset(data.keys()), (
                f"Missing keys: {expected_keys - data.keys()}"
            )
        finally:
            await transport.close()

    async def test_graceful_disconnect(self) -> None:
        """Connect, receive, then close gracefully."""
        config = BaseTransportConfig(connect_timeout=10.0, read_timeout=15.0)
        transport = AsyncTransport(config)

        await transport.connect(BINANCE_WS)
        await asyncio.wait_for(transport.recv(), timeout=15.0)
        await transport.close()

        assert not transport.is_connected
