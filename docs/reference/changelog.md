# Changelog

All notable changes to WSFabric will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Multiplex` for managing multiple logical subscriptions over a single WebSocket
- `WebSocket(message_type=...)` for Pydantic-validated messages
- Preset functions (`trading`, `llm_stream`, `dashboard`, `minimal`) in `wsfabric.presets`
- `py.typed` marker for PEP 561 type checking support
- Connection pooling with `ConnectionPool` and `ConnectionPoolConfig`
- Synchronous API with `SyncWebSocket`
- Message buffering with `BufferConfig`
- Replay-on-reconnect with `ReplayConfig`

### Changed

- Simplified API names: `WebSocket` (was `WebSocketManager`), `SyncWebSocket` (was `SyncWebSocketClient`), `Multiplex` (was `MultiplexConnection`)
- Improved reconnection logic with configurable backoff
- Enhanced heartbeat management with application-level ping support

## [0.1.0] - 2024-01-01

### Added

- Initial release
- `WebSocket` async WebSocket client
- Automatic reconnection with exponential backoff
- Heartbeat management (ping/pong)
- Event-driven architecture
- Rust-powered frame parsing via PyO3
- Comprehensive exception hierarchy
