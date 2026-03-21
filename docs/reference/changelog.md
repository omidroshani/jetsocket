# Changelog

All notable changes to WSFabric will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `MultiplexConnection` for managing multiple logical subscriptions over a single WebSocket
- `TypedWebSocket` for Pydantic-validated messages
- `Presets` class with pre-configured profiles (trading, llm_stream, dashboard, minimal)
- `py.typed` marker for PEP 561 type checking support
- Connection pooling with `ConnectionPool` and `ConnectionPoolConfig`
- Synchronous API with `SyncWebSocketClient`
- Message buffering with `BufferConfig`
- Replay-on-reconnect with `ReplayConfig`

### Changed

- Improved reconnection logic with configurable backoff
- Enhanced heartbeat management with application-level ping support

## [0.1.0] - 2024-01-01

### Added

- Initial release
- `WebSocketManager` async WebSocket client
- Automatic reconnection with exponential backoff
- Heartbeat management (ping/pong)
- Event-driven architecture
- Rust-powered frame parsing via PyO3
- Comprehensive exception hierarchy
