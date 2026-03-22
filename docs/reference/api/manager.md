# WebSocket

The core async WebSocket client with automatic reconnection, heartbeat, and message buffering.

::: jetsocket.manager.WebSocket
    options:
      show_source: true
      members:
        - __init__
        - connect
        - close
        - send
        - recv
        - run
        - on
        - stats
        - is_connected
        - latency_ms
        - buffer

## Configuration

WebSocket accepts several configuration objects:

```python
from jetsocket import (
    WebSocket,
    BackoffConfig,
    HeartbeatConfig,
    BufferConfig,
    ReplayConfig,
)

ws = WebSocket(
    "wss://example.com/ws",
    reconnect=True,
    backoff=BackoffConfig(base=1.0, multiplier=2.0, cap=60.0),
    heartbeat=HeartbeatConfig(interval=30.0, timeout=10.0),
    buffer=BufferConfig(capacity=1000),
    replay=ReplayConfig(mode="sequence_id", sequence_extractor=lambda m: m.get("seq")),
)
```

## Events

WebSocket emits events that you can subscribe to:

| Event | Description |
|-------|-------------|
| `connected` | Connection established |
| `disconnected` | Connection closed |
| `message` | Message received |
| `error` | Error occurred |
| `reconnecting` | Starting reconnection attempt |
| `reconnected` | Successfully reconnected |
| `ping` | Ping sent |
| `pong` | Pong received |
| `buffer_overflow` | Message buffer full |

```python
@ws.on("connected")
async def on_connected(event):
    print(f"Connected to {event.uri}")

@ws.on("message")
async def on_message(event):
    print(f"Received: {event.data}")
```

## Example

```python
import asyncio
from jetsocket import WebSocket, HeartbeatConfig

async def main():
    async with WebSocket(
        "wss://stream.example.com/ws",
        reconnect=True,
        heartbeat=HeartbeatConfig(interval=20.0),
    ) as ws:
        await ws.send({"subscribe": "trades"})
        async for message in ws:
            print(f"Trade: {message}")

asyncio.run(main())
```
