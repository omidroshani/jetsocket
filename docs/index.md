# WSFabric

**Production-grade, resilient WebSocket library for Python**

WSFabric provides a high-performance, memory-efficient WebSocket client with:

- **Rust-powered core** for frame parsing and compression
- **Automatic reconnection** with exponential backoff and jitter
- **Heartbeat management** (ping/pong)
- **Message buffering** with replay-on-reconnect
- **Both async and sync APIs** without thread explosion
- **Full type safety** with generics and Pydantic support

## Quick Example

=== "Async"

    ```python
    from wsfabric import WebSocketManager

    async with WebSocketManager("wss://stream.example.com/ws") as ws:
        await ws.send({"subscribe": "trades"})
        async for message in ws:
            print(f"Received: {message}")
    ```

=== "Sync"

    ```python
    from wsfabric import SyncWebSocketClient

    with SyncWebSocketClient("wss://stream.example.com/ws") as ws:
        ws.send({"subscribe": "trades"})
        for message in ws:
            print(f"Received: {message}")
    ```

## Installation

```bash
pip install wsfabric
```

## Why WSFabric?

| Feature | websockets | websocket-client | aiohttp | **WSFabric** |
|---------|------------|------------------|---------|--------------|
| Auto-Reconnect | :x: | :warning: basic | :x: | :white_check_mark: |
| Exponential Backoff | :x: | :x: | :x: | :white_check_mark: |
| Heartbeat Management | :x: | :x: | :x: | :white_check_mark: |
| Message Buffer | :x: | :x: | :x: | :white_check_mark: |
| Memory Efficient | :warning: 308MB VSZ | :x: threads | :x: | :white_check_mark: <10MB |
| Async + Sync | :warning: | sync only | async only | :white_check_mark: |
| Type Safe | partial | :x: | partial | :white_check_mark: |

## Features

### Automatic Reconnection

WSFabric handles disconnections gracefully with configurable exponential backoff:

```python
from wsfabric import WebSocketManager, BackoffConfig

ws = WebSocketManager(
    "wss://stream.example.com/ws",
    reconnect=True,
    backoff=BackoffConfig(
        base=1.0,      # Start with 1s delay
        cap=60.0,      # Max 60s between retries
        jitter=True,   # Randomize to avoid thundering herd
    ),
)
```

### Heartbeat Management

Never worry about idle disconnections again:

```python
from wsfabric import WebSocketManager, HeartbeatConfig

ws = WebSocketManager(
    "wss://stream.example.com/ws",
    heartbeat=HeartbeatConfig(
        interval=20.0,  # Send ping every 20s
        timeout=10.0,   # Wait 10s for pong
    ),
)
```

### Connection Pooling

Manage multiple connections efficiently:

```python
from wsfabric import ConnectionPool, ConnectionPoolConfig

config = ConnectionPoolConfig(max_connections=10)

async with ConnectionPool(config, base_uri="wss://stream.example.com") as pool:
    async with pool.acquire("/ws/btcusdt") as conn:
        await conn.send({"subscribe": "trades"})
        async for msg in conn:
            process(msg)
```

### Multiplexing

Multiple subscriptions over a single connection:

```python
from wsfabric import MultiplexConnection, MultiplexConfig

config = MultiplexConfig(
    channel_extractor=lambda msg: msg.get("stream"),
    subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
)

async with MultiplexConnection("wss://stream.example.com/ws", config) as mux:
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@trade")

    async for trade in btc:
        print(f"BTC: {trade}")
```

### Type Safety with Pydantic

Full type checking with Pydantic models:

```python
from pydantic import BaseModel
from wsfabric import TypedWebSocket

class TradeMessage(BaseModel):
    symbol: str
    price: float
    quantity: float

async with TypedWebSocket("wss://stream.example.com/ws", TradeMessage) as ws:
    async for trade in ws:  # trade is TradeMessage
        print(f"{trade.symbol}: ${trade.price:.2f}")
```

### Presets for Common Use Cases

Optimized configurations for different scenarios:

```python
from wsfabric import Presets

# For crypto trading
ws = Presets.trading("wss://stream.binance.com/ws")

# For LLM streaming
ws = Presets.llm_stream("wss://api.openai.com/v1/realtime")

# For dashboards
ws = Presets.dashboard("wss://dashboard.example.com/ws")
```

## What's Next?

- [Installation](getting-started/installation.md) - Get WSFabric installed
- [Quickstart](getting-started/quickstart.md) - Build your first WebSocket client
- [User Guide](user-guide/async-api.md) - Deep dive into all features
- [API Reference](reference/api/manager.md) - Full API documentation
