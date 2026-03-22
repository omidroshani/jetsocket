# Multiplex

Manages multiple logical subscriptions over a single WebSocket connection.

::: wsfabric.multiplex.Multiplex
    options:
      show_source: true
      members:
        - __init__
        - connect
        - close
        - subscribe
        - unsubscribe
        - get_subscription
        - list_subscriptions
        - stats

::: wsfabric.multiplex.Subscription
    options:
      show_source: true
      members:
        - recv
        - close
        - stats
        - channel
        - is_active

## Usage

```python
from wsfabric import Multiplex

async with Multiplex(
    "wss://stream.binance.com/ws",
    channel_key="stream",
    subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
    unsubscribe_msg=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]},
    queue_size=1000,
) as mux:
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@trade")

    async for trade in btc:
        print(f"BTC: {trade}")
```

## Configuration

### channel_key / channel_extractor

Use `channel_key` for simple key-based routing, or `channel_extractor` for custom logic:

```python
# Binance: {"stream": "btcusdt@trade", "data": {...}}
async with Multiplex("wss://...", channel_key="stream") as mux:
    ...

# Bybit: {"topic": "trade.BTCUSDT", ...}
async with Multiplex(
    "wss://...",
    channel_extractor=lambda msg: msg.get("topic"),
) as mux:
    ...
```

### subscribe_msg / unsubscribe_msg (optional)

Functions to generate protocol-specific messages:

```python
subscribe_msg=lambda ch: {"method": "SUBSCRIBE", "params": [ch]}
unsubscribe_msg=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]}
```

### queue_size

Maximum messages per subscription queue (default: 1000, 0 = unbounded):

```python
async with Multiplex(
    "wss://...",
    channel_key="stream",
    queue_size=5000,  # Large buffer for high-throughput streams
) as mux:
    ...
```

## Statistics

```python
# Multiplex stats
stats = mux.stats()
print(f"Total subscriptions: {stats.total_subscriptions}")
print(f"Active: {stats.active_subscriptions}")
print(f"Messages routed: {stats.total_messages_routed}")
print(f"Unroutable: {stats.unroutable_messages}")

# Per-subscription stats
sub_stats = btc.stats()
print(f"Channel: {sub_stats.channel}")
print(f"Messages received: {sub_stats.messages_received}")
```
