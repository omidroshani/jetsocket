# Events

WSFabric uses an event-driven architecture for connection lifecycle and message handling.

## Event Types

### Connection Events

| Event | Description | Fields |
|-------|-------------|--------|
| `connected` | Connection established | `uri`, `timestamp` |
| `disconnected` | Connection closed | `uri`, `code`, `reason`, `timestamp` |
| `reconnecting` | Starting reconnection | `attempt`, `delay`, `timestamp` |
| `reconnected` | Successfully reconnected | `uri`, `attempts`, `timestamp` |

### Message Events

| Event | Description | Fields |
|-------|-------------|--------|
| `message` | Message received | `data`, `timestamp` |
| `error` | Error occurred | `error`, `message`, `timestamp` |

### Heartbeat Events

| Event | Description | Fields |
|-------|-------------|--------|
| `ping` | Ping sent | `payload`, `timestamp` |
| `pong` | Pong received | `latency_ms`, `timestamp` |

### Buffer Events

| Event | Description | Fields |
|-------|-------------|--------|
| `buffer_overflow` | Buffer full | `dropped_count`, `policy` |
| `replay_started` | Replay begun | `mode`, `message_count` |
| `replay_completed` | Replay finished | `replayed_count`, `duration_ms` |

## Subscribing to Events

Use the `@ws.on()` decorator:

```python
from wsfabric import WebSocket

ws = WebSocket("wss://example.com/ws")

@ws.on("connected")
async def on_connected(event):
    print(f"Connected at {event.timestamp}")

@ws.on("message")
async def on_message(event):
    print(f"Received: {event.data}")

@ws.on("disconnected")
async def on_disconnected(event):
    print(f"Disconnected: {event.reason} (code {event.code})")

@ws.on("reconnecting")
async def on_reconnecting(event):
    print(f"Reconnecting... attempt {event.attempt}, waiting {event.delay}s")

@ws.on("error")
async def on_error(event):
    print(f"Error: {event.message}")
```

## Event Objects

All events include a `timestamp` field (Unix timestamp in seconds).

### ConnectedEvent

```python
@dataclass
class ConnectedEvent:
    uri: str
    timestamp: float
```

### DisconnectedEvent

```python
@dataclass
class DisconnectedEvent:
    uri: str
    code: int
    reason: str
    timestamp: float
```

### MessageEvent

```python
@dataclass
class MessageEvent:
    data: Any  # Parsed message (dict, list, etc.)
    timestamp: float
```

### ReconnectingEvent

```python
@dataclass
class ReconnectingEvent:
    attempt: int
    delay: float
    timestamp: float
```

## Multiple Handlers

You can register multiple handlers for the same event:

```python
@ws.on("message")
async def log_message(event):
    logger.info(f"Message: {event.data}")

@ws.on("message")
async def process_message(event):
    await process(event.data)
```

Both handlers will be called for each message.
