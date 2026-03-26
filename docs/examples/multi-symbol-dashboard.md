# Multi-Symbol Dashboard

Build a real-time terminal dashboard displaying multiple crypto trading pairs.

## Run It

```bash
uv run python examples/multi_symbol_dashboard.py
```

## Overview

- Stream 5 symbols over a single multiplexed connection
- Live terminal rendering with ANSI color codes
- Green/red coloring for positive/negative 24h change

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
        """Initialize dashboard with symbols to track."""
        self.symbols = symbols
        self.data: dict[str, SymbolData] = {s: SymbolData(symbol=s) for s in symbols}

    def update(self, symbol: str, **kwargs: Any) -> None:
        """Update symbol data and re-render."""
        if symbol in self.data:
            for key, value in kwargs.items():
                if hasattr(self.data[symbol], key):
                    setattr(self.data[symbol], key, value)
            self.render()

    def render(self) -> None:
        """Render the dashboard to terminal."""
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
            print(
                f"{symbol:<10} ${data.price:>11,.2f} {color}{change_str:>12}{reset}"
            )

        print("-" * 50)
        print("Press Ctrl+C to exit")


async def stream_symbol(mux: Multiplex[Any], symbol: str, dashboard: Dashboard) -> None:
    """Stream updates for a single symbol."""
    sub = await mux.subscribe(f"{symbol.lower()}@ticker")

    async for msg in sub:
        dashboard.update(
            symbol,
            price=float(msg.get("c", 0)),
            change_24h=float(msg.get("P", 0)),
        )


async def main() -> None:
    """Run the dashboard."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    dashboard = Dashboard(symbols)

    async with Multiplex(
        "wss://stream.binance.com:9443/ws",
        channel_extractor=lambda msg: (
            f"{msg['s'].lower()}@ticker" if "s" in msg else None
        ),
        subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        reconnect=True,
        heartbeat=30.0,
        buffer=100,
    ) as mux:
        tasks = [stream_symbol(mux, s, dashboard) for s in symbols]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDashboard stopped")
```

## Key Concepts

### Channel Extraction

Binance ticker messages contain a `"s"` (symbol) field. We map it to the subscription channel:

```python
channel_extractor=lambda msg: (
    f"{msg['s'].lower()}@ticker" if "s" in msg else None
)
```

### Concurrent Streaming

Use `asyncio.gather` to stream multiple symbols simultaneously:

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
    price=float(msg.get("c", 0)),
    volume_24h=float(msg.get("v", 0)),
    change_24h=float(msg.get("P", 0)),
)
```

### More Symbols

```python
symbols = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
]
```
