# Reconnection

WSFabric provides automatic reconnection with configurable exponential backoff.

## Basic Configuration

```python
from wsfabric import WebSocketManager, BackoffConfig

ws = WebSocketManager(
    "wss://example.com/ws",
    reconnect=True,  # Enable auto-reconnect (default)
    backoff=BackoffConfig(
        base=1.0,        # Initial delay: 1 second
        multiplier=2.0,  # Double each attempt
        cap=60.0,        # Maximum delay: 60 seconds
        jitter=True,     # Add randomization
        max_attempts=0,  # 0 = infinite retries
    ),
)
```

## Backoff Strategy

The delay between reconnection attempts follows this formula:

```
delay = min(base * (multiplier ^ attempt), cap)
if jitter:
    delay = random(0, delay)  # Full jitter
```

### Example Sequence (no jitter)

| Attempt | Delay |
|---------|-------|
| 1 | 1.0s |
| 2 | 2.0s |
| 3 | 4.0s |
| 4 | 8.0s |
| 5 | 16.0s |
| 6+ | 60.0s (capped) |

## Why Jitter?

Jitter prevents the "thundering herd" problem when many clients reconnect simultaneously (e.g., after a server restart or maintenance window).

```python
# Recommended: Full jitter
backoff = BackoffConfig(base=1.0, cap=60.0, jitter=True)
```

## Maximum Attempts

```python
# Retry up to 10 times, then fail
backoff = BackoffConfig(max_attempts=10)

# Retry forever (default)
backoff = BackoffConfig(max_attempts=0)
```

## Reset After Success

The attempt counter resets after staying connected:

```python
backoff = BackoffConfig(
    reset_after=60.0,  # Reset after 60s connected
)
```

## Connection Age Limit

Some services (like Binance) force disconnect after 24 hours. WSFabric can proactively reconnect:

```python
ws = WebSocketManager(
    "wss://stream.binance.com/ws",
    max_connection_age=85800.0,  # 23h 50m
)
```

## Disabling Reconnection

```python
ws = WebSocketManager(
    "wss://example.com/ws",
    reconnect=False,
)
```

## Handling Reconnection Events

```python
@ws.on("disconnected")
async def on_disconnected(event):
    print(f"Disconnected: {event.code} - {event.reason}")

@ws.on("reconnecting")
async def on_reconnecting(event):
    print(f"Reconnecting (attempt {event.attempt}, delay {event.delay:.1f}s)")

@ws.on("reconnected")
async def on_reconnected(event):
    print(f"Reconnected after {event.downtime_seconds:.2f}s downtime")
    # Re-subscribe to channels
    await ws.send({"subscribe": "trades"})
```

## Fatal vs Retriable Errors

WSFabric automatically distinguishes between errors that should trigger reconnection and errors that should not:

### Retriable (will reconnect)

- Network errors
- Timeout errors
- Server closing connection (most close codes)

### Fatal (will NOT reconnect)

- HTTP 401/403 (authentication failed)
- HTTP 404 (not found)
- Close code 1008 (policy violation)

```python
@ws.on("error")
async def on_error(event):
    if event.fatal:
        print("Fatal error - reconnection disabled")
    else:
        print("Retriable error - will reconnect")
```
