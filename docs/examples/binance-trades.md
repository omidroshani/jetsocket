# Binance Trade Streaming

This example demonstrates how to stream real-time trade data from Binance using multiplexing and typed messages.

## Overview

- Connect to Binance WebSocket API
- Subscribe to multiple trading pairs
- Parse trades with Pydantic models
- Handle reconnections gracefully

## Prerequisites

```bash
pip install wsfabric pydantic
```

## Full Code

```python
"""Real-time Binance trade streaming with multiplexing."""

from __future__ import annotations

import asyncio
from pydantic import BaseModel, Field

from wsfabric import Multiplex


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
```

## Key Concepts

### Multiplexing

Instead of opening separate connections for each symbol, we use `Multiplex` to handle multiple subscriptions over a single WebSocket:

```python
btc = await mux.subscribe("btcusdt@trade")
eth = await mux.subscribe("ethusdt@trade")
```

### Channel Extraction

Binance wraps messages with a `stream` field that we use for routing:

```json
{
  "stream": "btcusdt@trade",
  "data": {
    "e": "trade",
    "s": "BTCUSDT",
    "p": "50000.00",
    ...
  }
}
```

### Pydantic Models

Field aliases handle Binance's single-letter field names:

```python
class BinanceTrade(BaseModel):
    symbol: str = Field(alias="s")
    price: str = Field(alias="p")
```

## Variations

### Subscribe to More Symbols

```python
symbols = ["btcusdt", "ethusdt", "solusdt", "bnbusdt"]
subs = []
for symbol in symbols:
    sub = await mux.subscribe(f"{symbol}@trade")
    subs.append(sub)
```

### Add Order Book Depth

```python
btc_trades = await mux.subscribe("btcusdt@trade")
btc_depth = await mux.subscribe("btcusdt@depth20@100ms")
```

### Using the Trading Preset

```python
from wsfabric.presets import trading

ws = trading("wss://stream.binance.com:9443/ws")
```
