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
    # Main API
    "WebSocketManager",
    # Configuration
    "BackoffConfig",
    "HeartbeatConfig",
    # State & Stats
    "ConnectionState",
    "ConnectionStats",
    # Types
    "Frame",
    "Opcode",
    # Exceptions
    "CloseError",
    "ConnectionError",
    "HandshakeError",
    "InvalidStateError",
    "ProtocolError",
    "TimeoutError",
    "WSFabricError",
]

# Import from submodules - lazy imports for fast startup
from wsfabric.exceptions import (
    CloseError,
    ConnectionError,
    HandshakeError,
    InvalidStateError,
    ProtocolError,
    TimeoutError,
    WSFabricError,
)
from wsfabric.state import ConnectionState
from wsfabric.types import Frame, Opcode

# Lazy imports for heavier modules
_lazy_imports: dict[str, str] = {
    "WebSocketManager": "wsfabric.manager",
    "BackoffConfig": "wsfabric.backoff",
    "HeartbeatConfig": "wsfabric.heartbeat",
    "ConnectionStats": "wsfabric.stats",
}


def __getattr__(name: str) -> object:
    """Lazy import for heavy modules."""
    if name in _lazy_imports:
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
