# WSFabric

Production-grade, resilient WebSocket library for Python with Rust-powered performance.

Every existing Python WebSocket library gives you a raw pipe. WSFabric gives you a production-grade client manager with automatic reconnection, heartbeat management, message buffering, and connection pooling — all backed by a Rust core for maximum performance.

## Why WSFabric?

| Feature | `websockets` | `websocket-client` | `aiohttp` | **WSFabric** |
|---|---|---|---|---|
| Auto-Reconnect | - | Basic | - | Exponential backoff + jitter |
| Heartbeat | Manual | Manual | Manual | Built-in, configurable |
| Message Buffer | - | - | - | Ring buffer + replay |
| Connection Pool | - | - | - | Built-in |
| Multiplexing | - | - | - | Built-in |
| Async + Sync | Threading | Sync only | Async only | Both native |
| Type Safety | - | - | - | Generics + Pydantic |
| Performance Core | C extension | Pure Python | C extension | Rust (PyO3) |

## Features

- **Rust-powered core** — SIMD-accelerated frame parsing, masking, UTF-8 validation, and permessage-deflate compression via PyO3
- **Automatic reconnection** — Exponential backoff with jitter, configurable max attempts, connection age limits
- **Heartbeat management** — WebSocket-level and application-level ping/pong with timeout detection
- **Message buffering** — Ring buffer with overflow policies and replay-on-reconnect
- **Connection pooling** — Manage multiple connections with health checking and automatic rotation
- **Multiplexing** — Multiple logical subscriptions over a single WebSocket connection
- **Both async and sync** — Native asyncio API and synchronous wrapper
- **Full type safety** — Generic message types, Pydantic model validation via `TypedWebSocket`
- **Presets** — Pre-configured profiles for trading, LLM streaming, and dashboards
- **Zero runtime dependencies** — Only Python stdlib required; Rust core compiled as extension

## Installation

```bash
pip install wsfabric
```

With optional extras:

```bash
pip install wsfabric[pydantic]   # Pydantic message validation
pip install wsfabric[orjson]     # Faster JSON serialization
pip install wsfabric[all]        # All extras
```

## Quick Start

### Async

```python
import asyncio
from wsfabric import WebSocketManager

async def main():
    async with WebSocketManager("wss://stream.example.com/ws", reconnect=True) as ws:
        await ws.send({"subscribe": "trades"})
        async for message in ws:
            print(f"Received: {message}")

asyncio.run(main())
```

### Sync

```python
from wsfabric import SyncWebSocketClient

with SyncWebSocketClient("wss://stream.example.com/ws") as ws:
    ws.send({"subscribe": "trades"})
    for message in ws.iter_messages():
        print(f"Received: {message}")
```

### With Presets

```python
from wsfabric import Presets

# Optimized for exchange WebSocket connections
ws = Presets.trading("wss://stream.binance.com/ws")

# Optimized for LLM streaming
ws = Presets.llm_stream("wss://api.example.com/v1/stream")
```

### Typed Messages

```python
from pydantic import BaseModel
from wsfabric import TypedWebSocket

class Trade(BaseModel):
    symbol: str
    price: float
    quantity: float

async with TypedWebSocket("wss://stream.example.com/ws", Trade) as ws:
    async for trade in ws:  # trade: Trade (fully typed)
        print(f"{trade.symbol}: ${trade.price:.2f}")
```

### Multiplexing

```python
from wsfabric import MultiplexConnection, MultiplexConfig

config = MultiplexConfig(
    channel_extractor=lambda msg: msg.get("stream"),
    subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
)

async with MultiplexConnection("wss://stream.binance.com/ws", config) as mux:
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@trade")

    async for trade in btc:
        print(f"BTC: {trade}")
```

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              User-Facing Python API                    │
│    (async/sync, decorators, type-safe generics)       │
├──────────────────────────────────────────────────────┤
│                 Manager Layer (Python)                  │
│  ┌────────────┐ ┌───────────┐ ┌─────────────────┐   │
│  │ Connection  │ │ Heartbeat │ │ Message Buffer  │   │
│  │ Manager     │ │ Manager   │ │ (Ring Buffer)   │   │
│  │ + Pool      │ │           │ │ + Replay        │   │
│  └────────────┘ └───────────┘ └─────────────────┘   │
├──────────────────────────────────────────────────────┤
│               Transport Layer (Python)                 │
│  ┌──────────────────┐  ┌──────────────────────┐      │
│  │ AsyncIO Transport │  │ Sync Transport       │      │
│  └──────────────────┘  └──────────────────────┘      │
├──────────────────────────────────────────────────────┤
│            Protocol Core (Rust via PyO3)               │
│  ┌──────────┐ ┌────────────┐ ┌──────────────────┐   │
│  │ Frame     │ │ SIMD       │ │ permessage-      │   │
│  │ Parser    │ │ Masking    │ │ deflate (flate2) │   │
│  │ + Encoder │ │ + UTF-8    │ │ Compression      │   │
│  └──────────┘ └────────────┘ └──────────────────┘   │
└──────────────────────────────────────────────────────┘
```

## Configuration

```python
from wsfabric import WebSocketManager, BackoffConfig, HeartbeatConfig, BufferConfig

ws = WebSocketManager(
    "wss://stream.example.com/ws",
    reconnect=True,
    backoff=BackoffConfig(base=0.5, cap=30.0, jitter=True, max_attempts=0),
    heartbeat=HeartbeatConfig(interval=20.0, timeout=10.0),
    buffer=BufferConfig(capacity=10_000, overflow_policy="drop_oldest"),
    max_connection_age=85800,  # 23h 50m (before exchange 24h limit)
)
```

## Development

```bash
# Clone and setup
git clone https://github.com/omid/wsfabric && cd wsfabric
uv sync && uv run maturin develop

# Tests
uv run pytest

# Type check + lint
uv run mypy src/ && uv run ruff check .
```

## License

MIT
