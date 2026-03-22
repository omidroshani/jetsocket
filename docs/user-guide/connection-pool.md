# Connection Pool

WSFabric provides connection pooling for managing multiple WebSocket connections efficiently.

## Basic Usage

```python
from wsfabric import ConnectionPool, ConnectionPoolConfig

config = ConnectionPoolConfig(
    max_connections=10,
    max_idle_time=300.0,      # Close idle connections after 5 min
    health_check_interval=30.0,
    acquire_timeout=10.0,
)

async with ConnectionPool(config, base_uri="wss://stream.example.com") as pool:
    async with pool.acquire("/ws/btcusdt") as conn:
        await conn.send({"subscribe": "trades"})
        async for msg in conn:
            process(msg)
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_connections` | 10 | Maximum concurrent connections |
| `max_idle_time` | 300.0 | Close idle connections after N seconds |
| `health_check_interval` | 30.0 | Interval between health checks |
| `acquire_timeout` | 10.0 | Timeout for acquiring a connection |

## Acquiring Connections

```python
# With path (appended to base_uri)
async with pool.acquire("/ws/btcusdt") as conn:
    ...

# With full URI
async with pool.acquire("wss://stream.example.com/ws/btcusdt") as conn:
    ...

# With timeout
async with pool.acquire("/ws/btcusdt", timeout=5.0) as conn:
    ...
```

## Connection Reuse

Connections are reused when released back to the pool:

```python
async with pool.acquire("/ws/btcusdt") as conn1:
    # Use connection
    pass

# Connection returned to pool

async with pool.acquire("/ws/btcusdt") as conn2:
    # May be the same physical connection as conn1
    pass
```

## Pool Statistics

```python
stats = pool.stats()
print(f"Total connections: {stats.total_connections}")
print(f"Active: {stats.active_connections}")
print(f"Idle: {stats.idle_connections}")
print(f"Messages sent: {stats.total_messages_sent}")
print(f"Messages received: {stats.total_messages_received}")
```

## Health Checks

The pool automatically performs health checks on idle connections:

- Connections that fail health checks are removed
- New connections are created on demand
- Health check interval is configurable

## Pool Exhaustion

If all connections are in use:

```python
try:
    async with pool.acquire("/ws/btcusdt", timeout=5.0) as conn:
        ...
except PoolExhaustedError as e:
    print(f"Pool exhausted: max={e.max_connections}, timeout={e.timeout}s")
```

## Custom WebSocket Configuration

Pass additional WebSocket options:

```python
pool = ConnectionPool(
    config,
    base_uri="wss://stream.example.com",
    manager_kwargs={
        "reconnect": True,
        "heartbeat": HeartbeatConfig(interval=20.0),
    },
)
```

## Full Example

```python
import asyncio
from wsfabric import ConnectionPool, ConnectionPoolConfig, HeartbeatConfig

async def process_stream(pool, symbol):
    async with pool.acquire(f"/ws/{symbol}") as conn:
        await conn.send({"subscribe": "trades"})
        async for msg in conn:
            print(f"{symbol}: {msg}")

async def main():
    config = ConnectionPoolConfig(max_connections=10)

    async with ConnectionPool(
        config,
        base_uri="wss://stream.example.com",
        manager_kwargs={
            "heartbeat": HeartbeatConfig(interval=20.0),
        },
    ) as pool:
        # Process multiple streams concurrently
        await asyncio.gather(
            process_stream(pool, "btcusdt"),
            process_stream(pool, "ethusdt"),
            process_stream(pool, "solusdt"),
        )

if __name__ == "__main__":
    asyncio.run(main())
```
