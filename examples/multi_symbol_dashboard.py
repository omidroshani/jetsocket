"""Multi-symbol real-time dashboard.

This example demonstrates:
- Using multiplexing for multiple symbol streams
- Dashboard preset configuration
- Real-time terminal rendering with ANSI codes
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from wsfabric import MultiplexConfig, MultiplexConnection


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
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="")
        print("=" * 50)
        print("  CRYPTO DASHBOARD")
        print("=" * 50)
        print(f"{'Symbol':<10} {'Price':>12} {'24h Change':>12}")
        print("-" * 50)

        for symbol, data in self.data.items():
            change_str = f"{data.change_24h:+.2f}%"
            # Green for positive, red for negative
            color = "\033[32m" if data.change_24h >= 0 else "\033[31m"
            reset = "\033[0m"
            print(
                f"{symbol:<10} ${data.price:>11,.2f} {color}{change_str:>12}{reset}"
            )

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

    config = MultiplexConfig(
        channel_extractor=lambda msg: msg.get("stream"),
        subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
    )

    # Use dashboard-optimized settings
    async with MultiplexConnection(
        "wss://stream.binance.com:9443/ws",
        config,
        manager_kwargs={
            "reconnect": True,
            "heartbeat": {"interval": 30.0},
            "buffer": {"capacity": 100, "overflow_policy": "drop_oldest"},
        },
    ) as mux:
        # Stream all symbols concurrently
        tasks = [stream_symbol(mux, s, dashboard) for s in symbols]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDashboard stopped")
