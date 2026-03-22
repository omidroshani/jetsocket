# MultiplexConnection

Manages multiple logical subscriptions over a single WebSocket connection.

::: wsfabric.multiplex.MultiplexConnection
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

::: wsfabric.multiplex.MultiplexConfig
    options:
      show_source: true

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
from wsfabric import MultiplexConnection, MultiplexConfig

config = MultiplexConfig(
    channel_extractor=lambda msg: msg.get("stream"),
    subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
    unsubscribe_message=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]},
    queue_size=1000,
)

async with MultiplexConnection("wss://stream.binance.com/ws", config) as mux:
    btc = await mux.subscribe("btcusdt@trade")
    eth = await mux.subscribe("ethusdt@trade")

    async for trade in btc:
        print(f"BTC: {trade}")
```

## Configuration

### channel_extractor (required)

Function to extract the channel name from incoming messages:

```python
# Binance: {"stream": "btcusdt@trade", "data": {...}}
channel_extractor=lambda msg: msg.get("stream")

# Bybit: {"topic": "trade.BTCUSDT", ...}
channel_extractor=lambda msg: msg.get("topic")
```

### subscribe_message / unsubscribe_message (optional)

Functions to generate protocol-specific messages:

```python
subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]}
unsubscribe_message=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]}
```

### queue_size

Maximum messages per subscription queue (default: 1000, 0 = unbounded):

```python
config = MultiplexConfig(
    channel_extractor=...,
    queue_size=5000,  # Large buffer for high-throughput streams
)
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
