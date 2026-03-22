# Multi-Symbol Dashboard

This example demonstrates how to build a real-time dashboard that displays multiple trading pairs.

## Overview

- Use connection pooling for multiple endpoints
- Stream multiple symbols with multiplexing
- Display real-time price updates
- Handle reconnections seamlessly

## Prerequisites

```bash
pip install jetsocket
```

## Full Code

```python
"""Multi-symbol real-time dashboard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from jetsocket import Multiplex


@dataclass
class SymbolData:
    """Current state of a trading symbol."""

    symbol: str
    price: float = 0.0
    volume_24h: float = 0.0
    change_24h: float = 0.0


class Dashboard:
    """Real-time trading dashboard."""

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.data: dict[str, SymbolData] = {
            s: SymbolData(symbol=s) for s in symbols
        }

    def update(self, symbol: str, **kwargs: Any) -> None:
        """Update symbol data."""
        if symbol in self.data:
            for key, value in kwargs.items():
                if hasattr(self.data[symbol], key):
                    setattr(self.data[symbol], key, value)
            self.render()

    def render(self) -> None:
        """Render the dashboard."""
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="")
        print("=" * 50)
        print("  CRYPTO DASHBOARD")
        print("=" * 50)
        print(f"{'Symbol':<10} {'Price':>12} {'24h Change':>12}")
        print("-" * 50)

        for symbol, data in self.data.items():
            change_str = f"{data.change_24h:+.2f}%"
            color = "\033[32m" if data.change_24h >= 0 else "\033[31m"
            reset = "\033[0m"
            print(f"{symbol:<10} ${data.price:>11,.2f} {color}{change_str:>12}{reset}")

        print("-" * 50)
        print("Press Ctrl+C to exit")


async def stream_symbol(mux, symbol: str, dashboard: Dashboard) -> None:
    """Stream updates for a single symbol."""
    sub = await mux.subscribe(f"{symbol.lower()}@ticker")

    async for msg in sub:
        data = msg.get("data", msg)
        dashboard.update(
            symbol,
            price=float(data.get("c", 0)),
            change_24h=float(data.get("P", 0)),
        )


async def main() -> None:
    """Run the dashboard."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    dashboard = Dashboard(symbols)

    # Use dashboard-optimized settings
    async with Multiplex(
        "wss://stream.binance.com:9443/ws",
        channel_key="stream",
        subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        reconnect=True,
        heartbeat=30.0,
        buffer_capacity=100,
    ) as mux:
        # Stream all symbols concurrently
        tasks = [stream_symbol(mux, s, dashboard) for s in symbols]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDashboard stopped")
```

## Key Concepts

### Dashboard Preset

The dashboard-optimized settings keep a small buffer and drop stale data:

```python
async with Multiplex(
    "wss://...",
    channel_key="stream",
    heartbeat=30.0,
    buffer_capacity=100,
) as mux:
    ...
```

- Small buffer (latest data is most important)
- Drop oldest on overflow (stale data is useless)
- Relaxed reconnect (patient retry)

### Concurrent Streaming

Use `asyncio.gather` to stream multiple symbols:

```python
tasks = [stream_symbol(mux, s, dashboard) for s in symbols]
await asyncio.gather(*tasks)
```

### Terminal Rendering

Use ANSI escape codes for live updates:

```python
print("\033[2J\033[H", end="")  # Clear screen
print("\033[32m", end="")       # Green text
print("\033[0m", end="")        # Reset
```

## Variations

### Add Volume

```python
dashboard.update(
    symbol,
    price=float(data.get("c", 0)),
    volume_24h=float(data.get("v", 0)),
    change_24h=float(data.get("P", 0)),
)
```

### Multiple Exchanges

```python
# Stream from multiple exchanges
async with Multiplex(
    "wss://stream.binance.com/ws",
    channel_key="stream",
) as binance:
    async with Multiplex(
        "wss://stream.bybit.com/ws",
        channel_extractor=lambda msg: msg.get("topic"),
    ) as bybit:
        btc_binance = await binance.subscribe("btcusdt@ticker")
        btc_bybit = await bybit.subscribe("ticker.BTCUSDT")
```

### Web Dashboard

For a web-based dashboard, you could integrate with a framework:

```python
from fastapi import FastAPI, WebSocket as FastAPIWebSocket

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: FastAPIWebSocket):
    await websocket.accept()

    async with Multiplex(...) as mux:
        sub = await mux.subscribe("btcusdt@ticker")
        async for msg in sub:
            await websocket.send_json(msg)
```
