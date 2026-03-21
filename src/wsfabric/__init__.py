"""WSFabric — Production-grade, resilient WebSocket library for Python.

WSFabric provides a high-performance, memory-efficient WebSocket client with:
- Rust-powered frame parsing and compression
- Automatic reconnection with exponential backoff
- Heartbeat management (ping/pong)
- Message buffering with replay-on-reconnect
- Both async and sync APIs
- Full type safety with generics

Example:
    >>> from wsfabric import WebSocketManager
    >>>
    >>> async def main():
    ...     async with WebSocketManager("wss://example.com/ws") as ws:
    ...         async for message in ws:
    ...             print(message)

"""

from __future__ import annotations

import importlib

__version__ = "0.1.0"
__all__ = [
    "BackoffConfig",
    "BufferConfig",
    "BufferOverflowError",
    "CloseError",
    "ConnectionError",
    "ConnectionPool",
    "ConnectionPoolConfig",
    "ConnectionState",
    "ConnectionStats",
    "Frame",
    "HandshakeError",
    "HeartbeatConfig",
    "InvalidStateError",
    "MessageBuffer",
    "MultiplexConfig",
    "MultiplexConnection",
    "MultiplexStats",
    "Opcode",
    "PoolClosedError",
    "PoolExhaustedError",
    "PoolStats",
    "PooledConnection",
    "Presets",
    "ProtocolError",
    "ReplayConfig",
    "Subscription",
    "SubscriptionStats",
    "SyncWebSocketClient",
    "TimeoutError",
    "TypedWebSocket",
    "WSFabricError",
    "WebSocketManager",
]

# Import from submodules - lazy imports for fast startup
from wsfabric.exceptions import (
    BufferOverflowError,
    CloseError,
    ConnectionError,
    HandshakeError,
    InvalidStateError,
    PoolClosedError,
    PoolExhaustedError,
    ProtocolError,
    TimeoutError,
    WSFabricError,
)
from wsfabric.state import ConnectionState
from wsfabric.types import Frame, Opcode

# Lazy imports for heavier modules
_lazy_imports: dict[str, str] = {
    "BackoffConfig": "wsfabric.backoff",
    "BufferConfig": "wsfabric.buffer",
    "ConnectionPool": "wsfabric.pool",
    "ConnectionPoolConfig": "wsfabric.pool",
    "ConnectionStats": "wsfabric.stats",
    "HeartbeatConfig": "wsfabric.heartbeat",
    "MessageBuffer": "wsfabric.buffer",
    "MultiplexConfig": "wsfabric.multiplex",
    "MultiplexConnection": "wsfabric.multiplex",
    "MultiplexStats": "wsfabric.multiplex",
    "PooledConnection": "wsfabric.pool",
    "PoolStats": "wsfabric.pool",
    "Presets": "wsfabric.presets",
    "ReplayConfig": "wsfabric.buffer",
    "Subscription": "wsfabric.multiplex",
    "SubscriptionStats": "wsfabric.multiplex",
    "SyncWebSocketClient": "wsfabric.sync_client",
    "TypedWebSocket": "wsfabric.typed",
    "WebSocketManager": "wsfabric.manager",
}


def __getattr__(name: str) -> object:
    """Lazy import for heavy modules."""
    if name in _lazy_imports:
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
