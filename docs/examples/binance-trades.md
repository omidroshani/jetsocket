# Binance Trade Streaming

Stream real-time trade data from Binance using multiplexing and Pydantic models.

## Run It

```bash
uv run --extra pydantic python examples/binance_trades.py
```

## Overview

- Connect to Binance WebSocket API
- Subscribe to multiple trading pairs over a single connection
- Parse trades with Pydantic models
- Handle reconnections gracefully

## Full Code

```python
"""Real-time Binance trade streaming with multiplexing."""

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
        trade = BinanceTrade.model_validate(msg)
        print(f"{name}: {trade.side} {trade.price} x {trade.quantity}")


async def main() -> None:
    """Stream BTC and ETH trades from Binance."""
    async with Multiplex(
        "wss://stream.binance.com:9443/ws",
        channel_extractor=lambda msg: (
            f"{msg['s'].lower()}@trade" if "s" in msg else None
        ),
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

### Channel Extraction

Binance's `/ws` endpoint sends raw trade messages without a wrapper. We extract the channel from the symbol field:

```python
channel_extractor=lambda msg: (
    f"{msg['s'].lower()}@trade" if "s" in msg else None
)
```

A raw trade message from Binance looks like:

```json
{
  "e": "trade",
  "s": "BTCUSDT",
  "p": "69500.10",
  "q": "0.001",
  ...
}
```

The extractor maps `"BTCUSDT"` to `"btcusdt@trade"`, which matches the subscription channel name.

!!! tip "Alternative: Combined stream endpoint"
    If you prefer a `"stream"` key for routing, use `/stream?streams=` instead of `/ws`:
    ```python
    Multiplex(
        "wss://stream.binance.com:9443/stream",
        channel_key="stream",  # Messages arrive as {"stream": "btcusdt@trade", "data": {...}}
    )
    ```

### Multiplexing

Instead of opening separate connections for each symbol, `Multiplex` handles multiple subscriptions over a single WebSocket:

```python
btc = await mux.subscribe("btcusdt@trade")
eth = await mux.subscribe("ethusdt@trade")
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
