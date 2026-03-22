# Async API

The async API is JetSocket's primary interface, built on native asyncio.

## WebSocket

The main entry point for async WebSocket connections:

```python
from jetsocket import WebSocket

ws = WebSocket("wss://example.com/ws")
```

### Configuration

```python
from jetsocket import (
    WebSocket,
    BackoffConfig,
    HeartbeatConfig,
    BufferConfig,
)

ws = WebSocket(
    "wss://example.com/ws",
    reconnect=True,
    backoff=BackoffConfig(base=1.0, cap=60.0),
    heartbeat=HeartbeatConfig(interval=30.0),
    buffer=BufferConfig(capacity=1000),
)
```

### Connection

```python
# Manual connection
await ws.connect()
await ws.run()  # Blocks until closed
await ws.close()

# Context manager (recommended)
async with ws:
    await ws.send({"subscribe": "updates"})
    async for message in ws:
        process(message)
```

### Sending Messages

```python
# Send JSON-serializable data
await ws.send({"type": "subscribe", "channel": "trades"})

# Send raw bytes
await ws.send_raw(b"binary data", binary=True)
```

### Receiving Messages

```python
# Async iteration (recommended)
async for message in ws:
    print(message)

# Manual receive
message = await ws.recv()
```

### Events

```python
@ws.on("connected")
async def on_connect(event):
    print(f"Connected to {event.uri}")

@ws.on("message")
async def on_message(event):
    print(f"Received: {event.data}")

@ws.on("error")
async def on_error(event):
    print(f"Error: {event.error}")
```

### Statistics

```python
stats = ws.stats()
print(f"Messages received: {stats.messages_received}")
print(f"Reconnect count: {stats.reconnect_count}")
print(f"Latency: {stats.latency_ms}ms")
```

## Full Example

```python
import asyncio
from jetsocket import WebSocket, BackoffConfig, HeartbeatConfig

async def main():
    ws = WebSocket(
        "wss://stream.example.com/ws",
        reconnect=True,
        backoff=BackoffConfig(base=1.0, cap=30.0, jitter=True),
        heartbeat=HeartbeatConfig(interval=20.0, timeout=10.0),
    )

    @ws.on("connected")
    async def on_connected(event):
        print(f"Connected to {event.uri}")
        await ws.send({"subscribe": "trades"})

    @ws.on("reconnected")
    async def on_reconnected(event):
        print(f"Reconnected after {event.downtime_seconds:.2f}s")
        # Re-subscribe after reconnection
        await ws.send({"subscribe": "trades"})

    @ws.on("message")
    async def on_message(event):
        trade = event.data
        print(f"Trade: {trade['symbol']} @ {trade['price']}")

    try:
        await ws.connect()
        await ws.run()
    except KeyboardInterrupt:
        pass
    finally:
        await ws.close()

if __name__ == "__main__":
    asyncio.run(main())
```
