# Presets

Pre-configured WebSocket profiles for common use cases.

::: wsfabric.presets.Presets
    options:
      show_source: true
      members:
        - trading
        - llm_stream
        - dashboard
        - minimal

## Usage

```python
from wsfabric.presets import trading, llm_stream, dashboard

# For crypto trading
ws = trading("wss://stream.binance.com/ws")

# For LLM streaming
ws = llm_stream("wss://api.openai.com/v1/realtime")

# For dashboards
ws = dashboard("wss://dashboard.example.com/ws")
```

## Preset Details

### trading()

Optimized for exchange WebSocket connections:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Backoff base | 0.5s | Fast initial reconnect |
| Backoff cap | 30s | Don't wait too long |
| Max attempts | Infinite | Never give up |
| Heartbeat interval | 20s | Aggressive keep-alive |
| Buffer capacity | 10,000 | Large for high throughput |
| Deduplication | Enabled | Prevent duplicate trades |
| Max connection age | 23h 50m | Rotate before 24h limit |
| Compression | Enabled | Reduce bandwidth |

### llm_stream()

Optimized for LLM streaming APIs:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Backoff base | 1s | Quick retry |
| Backoff cap | 10s | Fast fail for UX |
| Max attempts | 5 | Don't retry forever |
| Heartbeat interval | 30s | Less overhead |
| Buffer capacity | 500 | Smaller (sequential) |
| Max message size | 128MB | Large responses |
| Compression | Disabled | Token streaming doesn't benefit |

### dashboard()

Optimized for real-time dashboard feeds:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Backoff base | 2s | Relaxed reconnect |
| Backoff cap | 60s | Patient retry |
| Max attempts | Infinite | Always reconnect |
| Heartbeat interval | 30s | Standard keep-alive |
| Buffer capacity | 100 | Small (latest data only) |
| Overflow policy | drop_oldest | Stale data is useless |

### minimal()

Basic configuration with sensible defaults:

| Setting | Value |
|---------|-------|
| Reconnect | Enabled |
| Heartbeat interval | 30s |
| Buffer capacity | 100 |

## Overriding Defaults

All presets accept `**overrides` to customize settings:

```python
from wsfabric.presets import trading, llm_stream

# Trading preset with custom buffer
ws = trading(
    "wss://stream.binance.com/ws",
    buffer=BufferConfig(capacity=50000),  # Override buffer
)

# LLM preset with longer timeout
ws = llm_stream(
    "wss://api.openai.com/v1/realtime",
    heartbeat=HeartbeatConfig(interval=60.0, timeout=30.0),
)
```
