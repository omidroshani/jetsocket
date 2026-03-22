# SyncWebSocket

Synchronous WebSocket client that wraps the async WebSocket.

::: wsfabric.sync_client.SyncWebSocket
    options:
      show_source: true
      members:
        - __init__
        - connect
        - close
        - send
        - recv
        - iter_messages
        - stats
        - is_connected
        - latency_ms

## Usage

SyncWebSocket provides a blocking API for scripts and notebooks:

```python
from wsfabric import SyncWebSocket

with SyncWebSocket("wss://example.com/ws") as ws:
    ws.send({"subscribe": "trades"})

    # Receive single message
    message = ws.recv(timeout=5.0)
    print(message)

    # Iterate over messages
    for msg in ws.iter_messages():
        print(f"Received: {msg}")
```

## Configuration

Accepts the same configuration as WebSocket:

```python
from wsfabric import SyncWebSocket, HeartbeatConfig

ws = SyncWebSocket(
    "wss://example.com/ws",
    reconnect=True,
    heartbeat=HeartbeatConfig(interval=20.0, timeout=10.0),
)
```

## Thread Safety

SyncWebSocket runs an event loop in a background thread. The client is safe to use from any thread, but individual connections should not be shared across threads.

## Example

```python
from wsfabric import SyncWebSocket

def process_trades():
    with SyncWebSocket("wss://stream.example.com/ws") as ws:
        ws.send({"action": "subscribe", "channel": "trades"})

        for trade in ws.iter_messages():
            print(f"Trade: {trade['price']} x {trade['quantity']}")

            # Stop after 10 trades
            if trade.get("count", 0) >= 10:
                break

if __name__ == "__main__":
    process_trades()
```
