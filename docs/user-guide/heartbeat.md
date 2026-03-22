# Heartbeat Management

WSFabric handles WebSocket ping/pong automatically to prevent idle disconnections.

## Basic Configuration

```python
from wsfabric import WebSocket, HeartbeatConfig

ws = WebSocket(
    "wss://example.com/ws",
    heartbeat=HeartbeatConfig(
        interval=30.0,  # Send ping every 30 seconds
        timeout=10.0,   # Wait 10 seconds for pong
    ),
)
```

## How It Works

1. WSFabric sends a WebSocket ping frame every `interval` seconds
2. If no pong is received within `timeout` seconds, the connection is considered dead
3. The connection is closed and reconnection is triggered (if enabled)

## Disabling Heartbeat

```python
ws = WebSocket(
    "wss://example.com/ws",
    heartbeat=None,  # No heartbeat
)
```

## Latency Monitoring

Heartbeat also measures round-trip latency:

```python
# Current latency
latency = ws.latency_ms
print(f"Current latency: {latency}ms")

# From stats
stats = ws.stats()
print(f"Latency: {stats.latency_ms}ms")
print(f"Average latency: {stats.latency_avg_ms}ms")
```

## Heartbeat Events

```python
@ws.on("ping")
async def on_ping(event):
    print(f"Ping sent: {event.payload}")

@ws.on("pong")
async def on_pong(event):
    print(f"Pong received: latency={event.latency_ms}ms")
```

## Application-Level Heartbeat

Some services use application-level ping/pong messages instead of WebSocket frames. WSFabric supports custom pong detection:

```python
heartbeat = HeartbeatConfig(
    interval=20.0,
    timeout=10.0,
    # Custom payload (sent as application message)
    payload=b'{"op": "ping"}',
    use_ws_ping=False,  # Don't use WebSocket ping
    use_application_ping=True,  # Send as regular message
    # Detect pong in application messages
    pong_matcher=lambda msg: msg.get("op") == "pong",
)
```

## Exchange-Specific Examples

### Binance

```python
# Binance uses WebSocket pong frames automatically
heartbeat = HeartbeatConfig(
    interval=20.0,
    timeout=10.0,
)
```

### Bybit

```python
# Bybit uses application-level ping/pong
heartbeat = HeartbeatConfig(
    interval=20.0,
    timeout=10.0,
    payload=b'{"op": "ping"}',
    use_ws_ping=False,
    use_application_ping=True,
    pong_matcher=lambda msg: msg.get("op") == "pong",
)
```

## Recommended Settings

| Use Case | Interval | Timeout |
|----------|----------|---------|
| Trading | 20s | 10s |
| LLM Streaming | 30s | 15s |
| Dashboard | 30s | 20s |
