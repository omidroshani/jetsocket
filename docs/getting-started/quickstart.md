# Quickstart

This guide will get you up and running with WSFabric in under 5 minutes.

## Basic Connection

### Async Usage

```python
import asyncio
from wsfabric import WebSocket

async def main():
    ws = WebSocket("wss://echo.websocket.org")

    @ws.on("message")
    async def on_message(event):
        print(f"Received: {event.data}")

    @ws.on("connected")
    async def on_connected(event):
        print("Connected!")
        await ws.send({"hello": "world"})

    await ws.run()

asyncio.run(main())
```

### Sync Usage

```python
from wsfabric import SyncWebSocket

with SyncWebSocket("wss://echo.websocket.org") as ws:
    ws.send({"hello": "world"})

    # Receive with timeout
    try:
        message = ws.recv(timeout=5.0)
        print(f"Received: {message}")
    except TimeoutError:
        print("No response within 5 seconds")
```

## Context Manager Pattern

Both async and sync clients support context managers for automatic cleanup:

=== "Async"

    ```python
    async with WebSocket("wss://example.com/ws") as ws:
        await ws.send({"subscribe": "updates"})
        async for message in ws:
            print(message)
    ```

=== "Sync"

    ```python
    with SyncWebSocket("wss://example.com/ws") as ws:
        ws.send({"subscribe": "updates"})
        for message in ws:
            print(message)
    ```

## Event Handling

WSFabric provides a rich event system for monitoring connection lifecycle:

```python
from wsfabric import WebSocket

ws = WebSocket("wss://example.com/ws")

@ws.on("connected")
async def on_connect(event):
    print(f"Connected to {event.uri}")

@ws.on("disconnected")
async def on_disconnect(event):
    print(f"Disconnected: {event.reason}")

@ws.on("reconnecting")
async def on_reconnecting(event):
    print(f"Reconnecting (attempt {event.attempt})...")

@ws.on("message")
async def on_message(event):
    print(f"Message: {event.data}")
```

## Using Presets

WSFabric provides optimized presets for common use cases:

```python
from wsfabric.presets import trading, llm_stream, dashboard

# For crypto trading - fast reconnect, large buffer
ws = trading("wss://stream.binance.com/ws")

# For LLM streaming - large messages, quick retry
ws = llm_stream("wss://api.openai.com/v1/realtime")

# For dashboards - relaxed reconnect, small buffer
ws = dashboard("wss://dashboard.example.com/ws")
```

## Typed Messages with Pydantic

For type-safe message handling:

```python
from pydantic import BaseModel
from wsfabric import WebSocket

class TradeMessage(BaseModel):
    symbol: str
    price: float
    quantity: float

async with WebSocket("wss://stream.example.com/ws", message_type=TradeMessage) as ws:
    async for trade in ws:  # trade is TradeMessage
        print(f"{trade.symbol}: ${trade.price:.2f}")
```

## What's Next?

- [Basic Concepts](basic-concepts.md) - Understand the core architecture
- [Reconnection](../user-guide/reconnection.md) - Configure reconnection behavior
- [Connection Pool](../user-guide/connection-pool.md) - Manage multiple connections
- [Multiplexing](../user-guide/multiplexing.md) - Multiple streams per connection
