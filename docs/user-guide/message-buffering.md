# Message Buffering

WSFabric can buffer received messages with sequence tracking and deduplication.

## Basic Configuration

```python
from wsfabric import WebSocketManager, BufferConfig

ws = WebSocketManager(
    "wss://example.com/ws",
    buffer=BufferConfig(
        capacity=1000,                  # Max messages to buffer
        overflow_policy="drop_oldest",  # Policy when full
    ),
)
```

## Overflow Policies

| Policy | Behavior |
|--------|----------|
| `drop_oldest` | Remove oldest message, add new (FIFO eviction) |
| `drop_newest` | Discard incoming message |
| `error` | Raise `BufferOverflowError` |

```python
# Discard new messages when full
buffer = BufferConfig(
    capacity=100,
    overflow_policy="drop_newest",
)
```

## Deduplication

Enable deduplication to prevent duplicate messages:

```python
buffer = BufferConfig(
    capacity=1000,
    enable_dedup=True,
    dedup_window=100,  # Track last 100 sequence IDs
)
```

## Replay on Reconnect

WSFabric can replay messages after reconnection:

```python
from wsfabric import WebSocketManager, BufferConfig, ReplayConfig

ws = WebSocketManager(
    "wss://example.com/ws",
    buffer=BufferConfig(capacity=1000),
    replay=ReplayConfig(
        mode="sequence_id",
        sequence_extractor=lambda msg: msg.get("seq"),
        on_replay=on_replay_callback,
    ),
)

async def on_replay_callback(last_seq):
    # Request missed messages from server
    await ws.send({"action": "replay", "from": last_seq})
```

### Replay Modes

| Mode | Description |
|------|-------------|
| `none` | No replay (default) |
| `sequence_id` | Call `on_replay` with last sequence ID |
| `full_buffer` | Resend all buffered messages |

## Buffer Statistics

```python
# Access buffer directly
buffer = ws.buffer
if buffer:
    print(f"Messages in buffer: {len(buffer)}")
    print(f"Fill ratio: {buffer.fill_ratio:.1%}")
    print(f"Dropped messages: {buffer.total_dropped}")

# From connection stats
stats = ws.stats()
print(f"Buffer fill: {stats.buffer_fill_ratio:.1%}")
```

## Buffer Events

```python
@ws.on("buffer_overflow")
async def on_overflow(event):
    print(f"Buffer overflow: dropped {event.dropped_count} messages")
    print(f"Policy: {event.policy}")

@ws.on("replay_started")
async def on_replay_start(event):
    print(f"Replay started: mode={event.mode}, messages={event.message_count}")

@ws.on("replay_completed")
async def on_replay_done(event):
    print(f"Replay completed: {event.replayed_count} messages in {event.duration_ms}ms")
```

## Recommended Settings

| Use Case | Capacity | Policy |
|----------|----------|--------|
| Trading | 10,000 | drop_oldest + dedup |
| LLM Streaming | 500 | drop_oldest |
| Dashboard | 100 | drop_oldest |
