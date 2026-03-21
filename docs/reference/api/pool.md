# ConnectionPool

Connection pool for managing multiple WebSocket connections efficiently.

::: wsfabric.ConnectionPool
    options:
      show_source: true
      members:
        - __init__
        - acquire
        - release
        - close
        - stats

::: wsfabric.ConnectionPoolConfig
    options:
      show_source: true

## Usage

```python
from wsfabric import ConnectionPool, ConnectionPoolConfig

config = ConnectionPoolConfig(
    max_connections=10,
    max_idle_time=300.0,
    health_check_interval=30.0,
    acquire_timeout=10.0,
)

async with ConnectionPool(config, base_uri="wss://stream.example.com") as pool:
    async with pool.acquire("/ws/btcusdt") as conn:
        await conn.send({"subscribe": "trades"})
        async for msg in conn:
            print(msg)
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_connections` | 10 | Maximum concurrent connections |
| `max_idle_time` | 300.0 | Close idle connections after N seconds |
| `health_check_interval` | 30.0 | Interval between health checks |
| `acquire_timeout` | 10.0 | Timeout for acquiring a connection |

## Pool Statistics

```python
stats = pool.stats()
print(f"Total: {stats.total_connections}")
print(f"Active: {stats.active_connections}")
print(f"Idle: {stats.idle_connections}")
```

## Pool Exhaustion

When all connections are in use:

```python
from wsfabric import PoolExhaustedError

try:
    async with pool.acquire("/ws", timeout=5.0) as conn:
        ...
except PoolExhaustedError as e:
    print(f"Pool exhausted: {e}")
```
