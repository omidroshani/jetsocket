# Changelog

All notable changes to JetSocket will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-22

First public release.

### Core

- `WebSocket` — async WebSocket client with automatic reconnection, heartbeat, and message buffering
- `SyncWebSocket` — synchronous wrapper for scripts and notebooks
- `connect()` — one-liner async context manager for quick connections
- Cython-optimized core: C-speed frame parsing, masking (uint64 XOR), and UTF-8 validation
- asyncio Protocol-based transport (no StreamReader/StreamWriter overhead)
- TCP_NODELAY enabled by default for lower latency

### Resilience

- Exponential backoff with jitter (`BackoffConfig`)
- Configurable heartbeat management with ping/pong (`HeartbeatConfig`)
- Message buffering with ring buffer and replay-on-reconnect (`BufferConfig`, `ReplayConfig`)
- `max_connection_age` for proactive reconnection (exchange 24h limit handling)
- DNS re-resolution on reconnect
- Fatal vs retriable error classification

### Compression

- permessage-deflate (RFC 7692) via Python zlib
- Configurable compression threshold (skip small messages)
- Full extension parameter negotiation

### Multiplexing & Pooling

- `Multiplex` — multiple logical subscriptions over a single WebSocket
- Flat API: `channel_key="stream"` instead of separate config classes
- `ConnectionPool` — manage multiple independent connections with health checking

### Type Safety

- `message_type=` parameter for Pydantic model validation (replaces `TypedWebSocket`)
- Scalar config shorthands: `heartbeat=20.0`, `buffer=1000`
- Full `py.typed` support (PEP 561)
- Complete `.pyi` type stubs for Cython extension

### Presets

- `jetsocket.presets.trading()` — optimized for crypto exchanges
- `jetsocket.presets.llm_stream()` — optimized for LLM streaming APIs
- `jetsocket.presets.dashboard()` — optimized for real-time dashboards
- `jetsocket.presets.minimal()` — basic configuration

### Developer Experience

- Simple API: 14 exports in `__all__`
- Comprehensive documentation with mkdocs-material
- 745 tests across unit, integration, security, stress, and benchmark suites
- Exchange integration tests (Binance, Bybit, OKX, Kraken, Coinbase)
- Comparative benchmarks vs websockets, websocket-client, aiohttp, picows
- CI/CD with GitHub Actions (test, lint, publish, docs)

### Performance

- Beats `websockets` by 20-30% across all benchmarks
- Competitive with `aiohttp` on connection and round-trip latency
- 159µs small message round-trip, 127ms/1000 message throughput
