"""Real-time Binance trade streaming with multiplexing.

This example demonstrates:
- Using Multiplex for multiple subscriptions over single WebSocket
- Parsing trades with Pydantic models
- Concurrent processing of multiple streams
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from jetsocket import Multiplex


class BinanceTrade(BaseModel):
    """Binance trade message."""

    event_type: str = Field(alias="e")
    event_time: int = Field(alias="E")
    symbol: str = Field(alias="s")
    trade_id: int = Field(alias="t")
    price: str = Field(alias="p")
    quantity: str = Field(alias="q")
    trade_time: int = Field(alias="T")
    is_buyer_maker: bool = Field(alias="m")

    @property
    def side(self) -> str:
        """Get trade side (BUY/SELL)."""
        return "SELL" if self.is_buyer_maker else "BUY"


async def process_trades(sub, name: str) -> None:
    """Process trades from a subscription."""
    async for msg in sub:
        data = msg.get("data", msg)
        trade = BinanceTrade.model_validate(data)
        print(f"{name}: {trade.side} {trade.price} x {trade.quantity}")


async def main() -> None:
    """Stream BTC and ETH trades from Binance."""
    async with Multiplex(
        "wss://stream.binance.com:9443/ws",
        channel_key="stream",
        subscribe_msg=lambda ch: {
            "method": "SUBSCRIBE",
            "params": [ch],
            "id": 1,
        },
        unsubscribe_msg=lambda ch: {
            "method": "UNSUBSCRIBE",
            "params": [ch],
            "id": 2,
        },
        reconnect=True,
        heartbeat=20.0,
    ) as mux:
        # Subscribe to multiple symbols
        btc = await mux.subscribe("btcusdt@trade")
        eth = await mux.subscribe("ethusdt@trade")

        print("Subscribed to BTC/USDT and ETH/USDT trades")
        print("Press Ctrl+C to stop\n")

        # Process both subscriptions concurrently
        await asyncio.gather(
            process_trades(btc, "BTC"),
            process_trades(eth, "ETH"),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
