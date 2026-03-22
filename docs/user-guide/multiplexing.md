# Multiplexing

Multiplexing allows multiple logical subscriptions over a single WebSocket connection.

## Why Multiplexing?

Many services (like Binance) allow hundreds of subscriptions per connection, but most code opens one connection per subscription. This wastes resources:

| Approach | 50 Symbols |
|----------|------------|
| 1 connection per symbol | 50 connections |
| Multiplexed | 1 connection |

## Basic Usage

```python
from wsfabric import Multiplex

async with Multiplex(
    "wss://stream.example.com/ws",
    channel_key="stream",
    subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
    unsubscribe_msg=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]},
) as mux:
    # Subscribe to multiple channels
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@trade")

    # Each subscription has its own queue
    async for trade in btc:
        print(f"BTC: {trade}")
```

## Configuration

### Channel Routing

Use `channel_key` for simple key-based routing, or `channel_extractor` for custom logic:

```python
# Simple key-based routing (extracts msg[key] for routing)
# For Binance-style messages: {"stream": "btcusdt@trade", "data": {...}}
async with Multiplex("wss://...", channel_key="stream") as mux:
    ...

# Custom extractor for complex routing
# For Bybit-style messages: {"topic": "trade.BTCUSDT", ...}
async with Multiplex(
    "wss://...",
    channel_extractor=lambda msg: msg.get("topic"),
) as mux:
    ...
```

### Subscribe/Unsubscribe Messages

Optional. Generate protocol-specific messages:

```python
# Binance
async with Multiplex(
    "wss://...",
    channel_key="stream",
    subscribe_msg=lambda ch: {
        "method": "SUBSCRIBE",
        "params": [ch],
        "id": int(time.time() * 1000),
    },
    unsubscribe_msg=lambda ch: {
        "method": "UNSUBSCRIBE",
        "params": [ch],
        "id": int(time.time() * 1000),
    },
) as mux:
    ...

# Bybit
async with Multiplex(
    "wss://...",
    channel_extractor=lambda msg: msg.get("topic"),
    subscribe_msg=lambda ch: {"op": "subscribe", "args": [ch]},
    unsubscribe_msg=lambda ch: {"op": "unsubscribe", "args": [ch]},
) as mux:
    ...
```

### Queue Size

Control per-subscription buffer size:

```python
async with Multiplex(
    "wss://...",
    channel_key="stream",
    queue_size=1000,  # Max messages per subscription (0 = unbounded)
) as mux:
    ...
```

## Subscription Management

### Subscribe

```python
sub = await mux.subscribe("btcusdt@trade")
```

### Unsubscribe

```python
await mux.unsubscribe("btcusdt@trade")
# or
await sub.close()
```

### List Subscriptions

```python
channels = mux.list_subscriptions()
print(f"Active subscriptions: {channels}")
```

### Get Subscription

```python
sub = mux.get_subscription("btcusdt@trade")
if sub and sub.is_active:
    print("Still subscribed")
```

## Receiving Messages

Each subscription has its own message queue:

```python
# Async iteration
async for msg in sub:
    print(msg)

# With timeout
msg = await sub.recv(timeout=5.0)
```

## Statistics

```python
# Multiplex stats
mux_stats = mux.stats()
print(f"Total subscriptions: {mux_stats.total_subscriptions}")
print(f"Active: {mux_stats.active_subscriptions}")
print(f"Routed messages: {mux_stats.total_messages_routed}")
print(f"Unroutable: {mux_stats.unroutable_messages}")

# Per-subscription stats
sub_stats = sub.stats()
print(f"Channel: {sub_stats.channel}")
print(f"Messages received: {sub_stats.messages_received}")
print(f"Queue size: {sub_stats.queue_size}")
```

## Exchange Examples

### Binance

```python
async with Multiplex(
    "wss://stream.binance.com:9443/ws",
    channel_key="stream",
    subscribe_msg=lambda ch: {
        "method": "SUBSCRIBE",
        "params": [ch],
        "id": 1,
    },
    unsubscribe_msg=lambda ch: {
        "method": "UNSUBSCRIBE",
        "params": [ch],
        "id": 2,
    },
) as mux:
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@aggTrade")
    kline = await mux.subscribe("btcusdt@kline_1m")
```

### Bybit

```python
async with Multiplex(
    "wss://stream.bybit.com/v5/public/spot",
    channel_extractor=lambda msg: msg.get("topic"),
    subscribe_msg=lambda ch: {"op": "subscribe", "args": [ch]},
    unsubscribe_msg=lambda ch: {"op": "unsubscribe", "args": [ch]},
) as mux:
    trades = await mux.subscribe("publicTrade.BTCUSDT")
```

## Full Example

```python
import asyncio
from wsfabric import Multiplex

async def process_subscription(sub, name):
    async for msg in sub:
        data = msg.get("data", msg)
        print(f"{name}: {data}")

async def main():
    async with Multiplex(
        "wss://stream.binance.com:9443/ws",
        channel_key="stream",
        subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        heartbeat=20.0,
    ) as mux:
        btc = await mux.subscribe("btcusdt@trade")
        eth = await mux.subscribe("ethusdt@trade")

        await asyncio.gather(
            process_subscription(btc, "BTC"),
            process_subscription(eth, "ETH"),
        )

if __name__ == "__main__":
    asyncio.run(main())
```
