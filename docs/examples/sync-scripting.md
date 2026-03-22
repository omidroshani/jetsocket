# Sync Scripting

This example demonstrates how to use the synchronous API for simple scripts and notebooks.

## Overview

- Use `SyncWebSocket` for blocking operations
- Simple one-shot requests
- Interactive scripting in notebooks
- No async/await required

## Prerequisites

```bash
pip install jetsocket
```

## Basic Example

```python
"""Simple sync WebSocket script."""

from jetsocket import SyncWebSocket


def main():
    """Fetch current BTC price."""
    with SyncWebSocket("wss://stream.binance.com:9443/ws/btcusdt@ticker") as ws:
        # Receive a single message
        ticker = ws.recv(timeout=5.0)
        price = float(ticker.get("c", 0))
        print(f"BTC/USDT: ${price:,.2f}")


if __name__ == "__main__":
    main()
```

## Full Code

```python
"""Sync WebSocket client for scripting."""

from __future__ import annotations

from jetsocket import SyncWebSocket, HeartbeatConfig


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
    """Calculate basic statistics."""
    return {
        "min": min(prices),
        "max": max(prices),
        "avg": sum(prices) / len(prices),
        "spread": max(prices) - min(prices),
    }


def main():
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
```

## Key Concepts

### Sync vs Async

Use `SyncWebSocket` when:
- Writing simple scripts
- Working in Jupyter notebooks
- Integrating with sync codebases
- Prototyping quickly

Use `WebSocket` (async) when:
- Building production services
- Handling multiple connections
- Maximum performance needed

### Context Manager

The `with` statement ensures proper cleanup:

```python
with SyncWebSocket(uri) as ws:
    message = ws.recv(timeout=5.0)
# Connection closed automatically
```

### Timeout Handling

Always use timeouts in sync code:

```python
try:
    message = ws.recv(timeout=5.0)
except TimeoutError:
    print("No message received")
```

## Jupyter Notebook Usage

```python
# In a notebook cell
from jetsocket import SyncWebSocket

ws = SyncWebSocket("wss://stream.binance.com:9443/ws/btcusdt@ticker")
ws.connect()

# Fetch a few messages
for _ in range(3):
    msg = ws.recv(timeout=5.0)
    print(f"Price: {msg.get('c')}")

ws.close()
```

## Variations

### Iterator Pattern

```python
with SyncWebSocket(uri) as ws:
    for msg in ws.iter_messages():
        print(msg)
        if should_stop(msg):
            break
```

### Send and Receive

```python
with SyncWebSocket("wss://api.example.com/ws") as ws:
    # Send request
    ws.send({"action": "get_price", "symbol": "BTCUSDT"})

    # Wait for response
    response = ws.recv(timeout=10.0)
    print(f"Response: {response}")
```

### With Reconnection

```python
ws = SyncWebSocket(
    "wss://stream.example.com/ws",
    reconnect=True,
    heartbeat=HeartbeatConfig(interval=30.0),
)

with ws:
    # Will automatically reconnect on disconnect
    for msg in ws.iter_messages():
        process(msg)
```
