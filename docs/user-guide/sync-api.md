# Sync API

WSFabric provides a synchronous API that wraps the async implementation with a background thread.

## SyncWebSocket

The sync client provides blocking operations for non-async codebases:

```python
from wsfabric import SyncWebSocket

ws = SyncWebSocket("wss://example.com/ws")
ws.connect()

ws.send({"subscribe": "updates"})
message = ws.recv(timeout=5.0)
print(message)

ws.close()
```

### Context Manager

```python
with SyncWebSocket("wss://example.com/ws") as ws:
    ws.send({"subscribe": "updates"})
    for message in ws:
        print(message)
```

### Configuration

All WebSocket options are supported:

```python
from wsfabric import (
    SyncWebSocket,
    BackoffConfig,
    HeartbeatConfig,
)

ws = SyncWebSocket(
    "wss://example.com/ws",
    reconnect=True,
    backoff=BackoffConfig(base=1.0, cap=30.0),
    heartbeat=HeartbeatConfig(interval=20.0),
)
```

### Receiving Messages

```python
# With timeout
try:
    message = ws.recv(timeout=5.0)
except TimeoutError:
    print("No message received")

# Iteration (blocks until message or close)
for message in ws:
    print(message)
```

### Event Handlers

Event handlers are called from the background thread:

```python
@ws.on("connected")
def on_connected(event):
    print("Connected!")

@ws.on("message")
def on_message(event):
    print(f"Received: {event.data}")
```

!!! warning "Thread Safety"
    Event handlers run in a background thread. Ensure your handlers are thread-safe.

### Statistics

```python
stats = ws.stats()
print(f"State: {stats.state}")
print(f"Messages: {stats.messages_received}")
```

## Full Example

```python
from wsfabric import SyncWebSocket, BackoffConfig

def main():
    ws = SyncWebSocket(
        "wss://stream.example.com/ws",
        reconnect=True,
        backoff=BackoffConfig(base=1.0, cap=30.0),
    )

    @ws.on("connected")
    def on_connected(event):
        print(f"Connected to {event.uri}")
        ws.send({"subscribe": "trades"})

    @ws.on("reconnected")
    def on_reconnected(event):
        print(f"Reconnected after {event.downtime_seconds:.2f}s")
        ws.send({"subscribe": "trades"})

    try:
        with ws:
            for message in ws:
                print(f"Trade: {message}")
    except KeyboardInterrupt:
        print("Interrupted")

if __name__ == "__main__":
    main()
```
