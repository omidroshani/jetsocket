# Configuration

WSFabric uses dataclasses for type-safe configuration.

## BackoffConfig

Controls reconnection backoff behavior.

::: wsfabric.backoff.BackoffConfig
    options:
      show_source: true

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base` | float | 1.0 | Initial delay in seconds |
| `multiplier` | float | 2.0 | Delay multiplier per attempt |
| `cap` | float | 60.0 | Maximum delay in seconds |
| `jitter` | bool | True | Add random jitter to prevent thundering herd |
| `max_attempts` | int | 0 | Maximum attempts (0 = infinite) |
| `reset_after` | float | 60.0 | Reset backoff after N seconds of successful connection |

### Example

```python
from wsfabric import BackoffConfig

# Aggressive reconnect for trading
backoff = BackoffConfig(
    base=0.5,
    multiplier=2.0,
    cap=30.0,
    jitter=True,
    max_attempts=0,  # Never give up
)

# Quick fail for user-facing apps
backoff = BackoffConfig(
    base=1.0,
    multiplier=2.0,
    cap=10.0,
    max_attempts=5,  # Give up after 5 attempts
)
```

## HeartbeatConfig

Controls ping/pong heartbeat behavior.

::: wsfabric.heartbeat.HeartbeatConfig
    options:
      show_source: true

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `interval` | float | 30.0 | Send ping every N seconds |
| `timeout` | float | 10.0 | Wait N seconds for pong |
| `payload` | bytes | None | Custom ping payload |
| `use_ws_ping` | bool | True | Use WebSocket ping frames |
| `use_application_ping` | bool | False | Send as application message |
| `pong_matcher` | Callable | None | Function to detect pong in messages |

### Example

```python
from wsfabric import HeartbeatConfig

# Standard WebSocket ping
heartbeat = HeartbeatConfig(interval=20.0, timeout=10.0)

# Application-level ping (e.g., Bybit)
heartbeat = HeartbeatConfig(
    interval=20.0,
    timeout=10.0,
    payload=b'{"op": "ping"}',
    use_ws_ping=False,
    use_application_ping=True,
    pong_matcher=lambda msg: msg.get("op") == "pong",
)
```

## BufferConfig

Controls message buffering behavior.

::: wsfabric.buffer.BufferConfig
    options:
      show_source: true

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `capacity` | int | 1000 | Maximum messages to buffer |
| `overflow_policy` | str | "drop_oldest" | Policy when full: "drop_oldest", "drop_newest", "error" |
| `enable_dedup` | bool | False | Enable deduplication |
| `dedup_window` | int | 100 | Track last N sequence IDs |

### Example

```python
from wsfabric import BufferConfig

# Trading: large buffer with dedup
buffer = BufferConfig(
    capacity=10000,
    overflow_policy="drop_oldest",
    enable_dedup=True,
    dedup_window=1000,
)

# Dashboard: small buffer, drop stale
buffer = BufferConfig(
    capacity=100,
    overflow_policy="drop_oldest",
)
```

## ReplayConfig

Controls replay-on-reconnect behavior.

::: wsfabric.buffer.ReplayConfig
    options:
      show_source: true

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | str | "none" | Replay mode: "none", "sequence_id", "full_buffer" |
| `sequence_extractor` | Callable | None | Function to extract sequence ID from message |
| `on_replay` | Callable | None | Callback when replay is needed |

### Example

```python
from wsfabric import ReplayConfig

async def request_replay(last_seq):
    await ws.send({"action": "replay", "from": last_seq})

replay = ReplayConfig(
    mode="sequence_id",
    sequence_extractor=lambda msg: msg.get("seq"),
    on_replay=request_replay,
)
```

## ConnectionPoolConfig

Controls connection pool behavior.

::: wsfabric.pool.ConnectionPoolConfig
    options:
      show_source: true

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_connections` | int | 10 | Maximum concurrent connections |
| `max_idle_time` | float | 300.0 | Close idle connections after N seconds |
| `health_check_interval` | float | 30.0 | Interval between health checks |
| `acquire_timeout` | float | 10.0 | Timeout for acquiring connection |

### Example

```python
from wsfabric import ConnectionPoolConfig

config = ConnectionPoolConfig(
    max_connections=20,
    max_idle_time=600.0,
    health_check_interval=60.0,
)
```
