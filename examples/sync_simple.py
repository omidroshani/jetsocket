"""Simple sync WebSocket client for scripting.

This example demonstrates:
- Using SyncWebSocket for blocking operations
- Simple one-shot requests
- No async/await required
"""

from __future__ import annotations

from wsfabric import HeartbeatConfig, SyncWebSocket


def fetch_prices(symbols: list[str], count: int = 5) -> dict[str, list[float]]:
    """Fetch recent prices for multiple symbols.

    Args:
        symbols: List of trading pairs (e.g., ["btcusdt", "ethusdt"]).
        count: Number of prices to collect per symbol.

    Returns:
        Dictionary mapping symbols to price lists.
    """
    prices: dict[str, list[float]] = {s: [] for s in symbols}

    # Connect to combined stream
    stream = "/".join(f"{s}@trade" for s in symbols)
    uri = f"wss://stream.binance.com:9443/stream?streams={stream}"

    with SyncWebSocket(
        uri,
        heartbeat=HeartbeatConfig(interval=20.0),
    ) as ws:
        # Collect prices
        while any(len(p) < count for p in prices.values()):
            msg = ws.recv(timeout=10.0)

            if data := msg.get("data"):
                symbol = data.get("s", "").lower()
                if symbol in prices and len(prices[symbol]) < count:
                    prices[symbol].append(float(data.get("p", 0)))

    return prices


def calculate_stats(prices: list[float]) -> dict[str, float]:
    """Calculate basic statistics for a list of prices."""
    return {
        "min": min(prices),
        "max": max(prices),
        "avg": sum(prices) / len(prices),
        "spread": max(prices) - min(prices),
    }


def main() -> None:
    """Run the price analysis."""
    symbols = ["btcusdt", "ethusdt", "solusdt"]

    print("Fetching prices...")
    prices = fetch_prices(symbols, count=10)

    print("\nPrice Analysis")
    print("=" * 50)

    for symbol, price_list in prices.items():
        stats = calculate_stats(price_list)
        print(f"\n{symbol.upper()}")
        print(f"  Min: ${stats['min']:,.2f}")
        print(f"  Max: ${stats['max']:,.2f}")
        print(f"  Avg: ${stats['avg']:,.2f}")
        print(f"  Spread: ${stats['spread']:.2f}")


if __name__ == "__main__":
    main()
