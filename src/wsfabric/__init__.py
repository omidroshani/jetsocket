"""WSFabric — Production-grade, resilient WebSocket library for Python.

WSFabric provides a high-performance, memory-efficient WebSocket client with:
- Cython-optimized frame parsing and compression
- Automatic reconnection with exponential backoff
- Heartbeat management (ping/pong)
- Message buffering with replay-on-reconnect
- Both async and sync APIs
- Full type safety with generics

Example:
    >>> import wsfabric
    >>>
    >>> async def main():
    ...     async with wsfabric.connect("wss://example.com/ws") as ws:
    ...         async for message in ws:
    ...             print(message)

"""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import AsyncIterator
from typing import Any

__version__ = "0.1.0"
__all__ = [
    "BackoffConfig",
    "BufferConfig",
    "ConnectionError",
    "ConnectionState",
    "HandshakeError",
    "HeartbeatConfig",
    "InvalidStateError",
    "Multiplex",
    "ProtocolError",
    "SyncWebSocket",
    "TimeoutError",
    "WSFabricError",
    "WebSocket",
    "connect",
]

# Import from submodules - eager imports for exceptions and state
from wsfabric.exceptions import (
    ConnectionError,
    HandshakeError,
    InvalidStateError,
    ProtocolError,
    TimeoutError,
    WSFabricError,
)
from wsfabric.state import ConnectionState

# Lazy imports for heavier modules
_lazy_imports: dict[str, str] = {
    # Primary API (new names)
    "WebSocket": "wsfabric.manager",
    "SyncWebSocket": "wsfabric.sync_client",
    "Multiplex": "wsfabric.multiplex",
    # Configuration
    "BackoffConfig": "wsfabric.backoff",
    "BufferConfig": "wsfabric.buffer",
    "HeartbeatConfig": "wsfabric.heartbeat",
    # Exceptions (importable but not in __all__)
    "BufferOverflowError": "wsfabric.exceptions",
    "CloseError": "wsfabric.exceptions",
    "PoolClosedError": "wsfabric.exceptions",
    "PoolExhaustedError": "wsfabric.exceptions",
    # Types (importable but not in __all__)
    "Frame": "wsfabric.types",
    "Opcode": "wsfabric.types",
    # Advanced (importable but not in __all__)
    "ConnectionPool": "wsfabric.pool",
    "ConnectionPoolConfig": "wsfabric.pool",
    "ConnectionStats": "wsfabric.stats",
    "MessageBuffer": "wsfabric.buffer",
    "MultiplexConfig": "wsfabric.multiplex",
    "MultiplexStats": "wsfabric.multiplex",
    "PooledConnection": "wsfabric.pool",
    "PoolStats": "wsfabric.pool",
    "ReplayConfig": "wsfabric.buffer",
    "Subscription": "wsfabric.multiplex",
    "SubscriptionStats": "wsfabric.multiplex",
}


def __getattr__(name: str) -> object:
    """Lazy import for heavy modules."""
    if name in _lazy_imports:
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


@contextlib.asynccontextmanager
async def connect(uri: str, **kwargs: Any) -> AsyncIterator[Any]:
    """Connect to a WebSocket server.

    Convenience function that creates a WebSocket, connects it, and
    yields it as an async context manager.

    Args:
        uri: The WebSocket URI to connect to.
        **kwargs: Additional arguments passed to WebSocket.

    Yields:
        A connected WebSocket instance.

    Example:
        >>> async with wsfabric.connect("wss://example.com/ws") as ws:
        ...     await ws.send({"hello": "world"})
        ...     msg = await ws.recv()
    """
    # Import here to avoid circular import at module level
    from wsfabric.manager import WebSocket  # noqa: PLC0415

    ws: WebSocket[Any] = WebSocket(uri, **kwargs)
    await ws.connect()
    try:
        yield ws
    finally:
        await ws.close()
