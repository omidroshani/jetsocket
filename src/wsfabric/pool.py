"""Connection pool for WSFabric.

This module provides connection pooling for WebSocket connections,
allowing efficient reuse of connections and management of multiple
concurrent connections with semaphore-based limiting.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)
from urllib.parse import urljoin, urlparse

from wsfabric.exceptions import InvalidStateError, PoolClosedError, PoolExhaustedError
from wsfabric.manager import WebSocket
from wsfabric.state import ConnectionState

if TYPE_CHECKING:
    from types import TracebackType

# Type variable for deserialized messages
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ConnectionPoolConfig:
    """Configuration for connection pooling.

    Args:
        max_connections: Maximum concurrent connections in the pool.
        max_idle_time: Close idle connections after this many seconds.
        health_check_interval: Interval between health checks in seconds.
        acquire_timeout: Timeout for acquiring a connection in seconds.
    """

    max_connections: int = 10
    max_idle_time: float = 300.0
    health_check_interval: float = 30.0
    acquire_timeout: float = 10.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_connections <= 0:
            msg = f"max_connections must be positive, got {self.max_connections}"
            raise ValueError(msg)
        if self.max_idle_time <= 0:
            msg = f"max_idle_time must be positive, got {self.max_idle_time}"
            raise ValueError(msg)
        if self.health_check_interval <= 0:
            msg = f"health_check_interval must be positive, got {self.health_check_interval}"
            raise ValueError(msg)
        if self.acquire_timeout <= 0:
            msg = f"acquire_timeout must be positive, got {self.acquire_timeout}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PoolStats:
    """Aggregated pool statistics.

    Args:
        total_connections: Total number of connections ever created.
        active_connections: Number of currently active (in-use) connections.
        idle_connections: Number of currently idle connections.
        total_messages_sent: Total messages sent across all connections.
        total_messages_received: Total messages received across all connections.
        total_reconnects: Total reconnection count across all connections.
    """

    total_connections: int
    active_connections: int
    idle_connections: int
    total_messages_sent: int
    total_messages_received: int
    total_reconnects: int


@dataclass
class _PooledConnectionState:
    """Internal state for a pooled connection."""

    manager: WebSocket[Any]
    uri: str
    created_at: float = field(default_factory=time.monotonic)
    last_used_at: float = field(default_factory=time.monotonic)
    in_use: bool = False

    def mark_used(self) -> None:
        """Mark the connection as in use."""
        self.in_use = True
        self.last_used_at = time.monotonic()

    def mark_released(self) -> None:
        """Mark the connection as released."""
        self.in_use = False
        self.last_used_at = time.monotonic()

    @property
    def idle_time(self) -> float:
        """Get the time since last use."""
        return time.monotonic() - self.last_used_at


class PooledConnection(Generic[T]):
    """Wrapper for pool-managed connections.

    This class wraps a WebSocket and provides automatic release
    back to the pool when used as a context manager.

    Example:
        >>> async with pool.acquire("/ws/stream") as conn:
        ...     await conn.send({"subscribe": "data"})
        ...     msg = await conn.recv()
    """

    def __init__(
        self,
        pool: ConnectionPool[T],
        state: _PooledConnectionState,
    ) -> None:
        """Initialize pooled connection.

        Args:
            pool: The parent connection pool.
            state: The internal connection state.
        """
        self._pool = pool
        self._state = state
        self._released = False

    @property
    def uri(self) -> str:
        """Get the connection URI."""
        return self._state.uri

    @property
    def is_connected(self) -> bool:
        """Return True if the underlying connection is connected."""
        return self._state.manager.is_connected

    @property
    def latency_ms(self) -> float | None:
        """Get the last measured round-trip latency in milliseconds."""
        return self._state.manager.latency_ms

    async def send(self, data: Any) -> None:
        """Send a message through the connection.

        Args:
            data: The message data to send.

        Raises:
            InvalidStateError: If connection is released or not connected.
        """
        if self._released:
            raise InvalidStateError(
                "Connection has been released",
                current_state="released",
                required_states=["active"],
            )
        await self._state.manager.send(data)

    async def send_raw(self, data: bytes, *, binary: bool = True) -> None:
        """Send raw bytes through the connection.

        Args:
            data: The raw bytes to send.
            binary: If True, send as binary frame.

        Raises:
            InvalidStateError: If connection is released or not connected.
        """
        if self._released:
            raise InvalidStateError(
                "Connection has been released",
                current_state="released",
                required_states=["active"],
            )
        await self._state.manager.send_raw(data, binary=binary)

    async def recv(self) -> T:
        """Receive a message from the connection.

        Returns:
            The deserialized message.

        Raises:
            InvalidStateError: If connection is released or not connected.
        """
        if self._released:
            raise InvalidStateError(
                "Connection has been released",
                current_state="released",
                required_states=["active"],
            )
        result: T = await self._state.manager.recv()
        return result

    async def release(self) -> None:
        """Release the connection back to the pool.

        After releasing, the connection should not be used.
        """
        if not self._released:
            self._released = True
            await self._pool.release(self)

    async def __aenter__(self) -> PooledConnection[T]:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit - releases connection."""
        await self.release()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"PooledConnection(uri={self._state.uri!r}, "
            f"connected={self.is_connected}, released={self._released})"
        )


class ConnectionPool(Generic[T]):
    """Pool of WebSocket instances.

    Manages multiple WebSocket connections with semaphore-based limiting,
    connection reuse, health checking, and idle cleanup.

    Example:
        >>> async with ConnectionPool(base_uri="wss://stream.example.com") as pool:
        ...     async with pool.acquire("/ws/btcusdt") as conn:
        ...         await conn.send({"subscribe": "trades"})
        ...         async for msg in conn:
        ...             process(msg)

    Args:
        config: Pool configuration. Uses defaults if not provided.
        base_uri: Base URI for relative paths. Required for relative paths.
        manager_kwargs: Additional kwargs to pass to WebSocket.
    """

    def __init__(
        self,
        config: ConnectionPoolConfig | None = None,
        *,
        base_uri: str | None = None,
        manager_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the connection pool."""
        self._config = config or ConnectionPoolConfig()
        self._base_uri = base_uri
        self._manager_kwargs = manager_kwargs or {}

        # Connection storage by URI
        self._connections: dict[str, list[_PooledConnectionState]] = {}
        self._connection_count = 0

        # Semaphore for limiting concurrent connections
        self._semaphore = asyncio.Semaphore(self._config.max_connections)

        # Pool state
        self._closed = False
        self._lock = asyncio.Lock()

        # Background tasks
        self._health_check_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def is_closed(self) -> bool:
        """Return True if the pool has been closed."""
        return self._closed

    async def acquire(
        self,
        uri_or_path: str,
        timeout: float | None = None,
    ) -> PooledConnection[T]:
        """Acquire a connection from the pool.

        If a matching idle connection exists, it will be reused.
        Otherwise, a new connection will be created.

        Args:
            uri_or_path: Full URI or path relative to base_uri.
            timeout: Timeout for acquiring. Uses config default if not provided.

        Returns:
            A PooledConnection wrapper.

        Raises:
            PoolClosedError: If the pool has been closed.
            PoolExhaustedError: If no connection available within timeout.
            ConnectionError: If connection fails.
        """
        if self._closed:
            raise PoolClosedError("Pool has been closed")

        timeout = timeout if timeout is not None else self._config.acquire_timeout

        # Resolve full URI
        full_uri = self._resolve_uri(uri_or_path)

        # Try to acquire semaphore with timeout
        try:
            acquired = await asyncio.wait_for(
                self._acquire_semaphore(),
                timeout=timeout,
            )
            if not acquired:
                raise PoolExhaustedError(
                    f"Could not acquire connection within {timeout}s",
                    max_connections=self._config.max_connections,
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            raise PoolExhaustedError(
                f"Could not acquire connection within {timeout}s",
                max_connections=self._config.max_connections,
                timeout=timeout,
            ) from None

        try:
            # Try to get an existing idle connection
            async with self._lock:
                conn_state = self._get_idle_connection(full_uri)

            if conn_state is not None:
                # Verify connection is still usable
                if conn_state.manager.state in (
                    ConnectionState.CONNECTED,
                    ConnectionState.RECONNECTING,
                    ConnectionState.BACKING_OFF,
                ):
                    conn_state.mark_used()
                    return PooledConnection[T](self, conn_state)
                else:
                    # Connection is dead, remove it
                    async with self._lock:
                        self._remove_connection(conn_state)

            # Create new connection
            conn_state = await self._create_connection(full_uri)
            conn_state.mark_used()
            return PooledConnection[T](self, conn_state)

        except Exception:
            # Release semaphore on failure
            self._semaphore.release()
            raise

    async def _acquire_semaphore(self) -> bool:
        """Acquire the semaphore."""
        await self._semaphore.acquire()
        return True

    async def release(self, conn: PooledConnection[T]) -> None:
        """Release a connection back to the pool.

        Args:
            conn: The pooled connection to release.
        """
        state = conn._state
        state.mark_released()

        # Release semaphore
        self._semaphore.release()

        # If pool is closed or connection is dead, close it
        if self._closed or state.manager.state.is_terminal:
            await self._close_connection(state)
            async with self._lock:
                self._remove_connection(state)

    def stats(self) -> PoolStats:
        """Get aggregated pool statistics.

        Returns:
            A PoolStats instance with current statistics.
        """
        active = 0
        idle = 0
        total_sent = 0
        total_received = 0
        total_reconnects = 0

        for conn_list in self._connections.values():
            for conn_state in conn_list:
                if conn_state.in_use:
                    active += 1
                else:
                    idle += 1

                stats = conn_state.manager.stats()
                total_sent += stats.messages_sent
                total_received += stats.messages_received
                total_reconnects += stats.reconnect_count

        return PoolStats(
            total_connections=self._connection_count,
            active_connections=active,
            idle_connections=idle,
            total_messages_sent=total_sent,
            total_messages_received=total_received,
            total_reconnects=total_reconnects,
        )

    async def close(self) -> None:
        """Close the pool and all connections.

        After closing, no new connections can be acquired.
        """
        self._closed = True

        # Cancel background tasks
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
            self._health_check_task = None

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

        # Close all connections
        async with self._lock:
            close_tasks: list[asyncio.Task[None]] = []
            for conn_list in self._connections.values():
                for conn_state in conn_list:
                    task = asyncio.create_task(self._close_connection(conn_state))
                    close_tasks.append(task)

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            self._connections.clear()

    async def __aenter__(self) -> ConnectionPool[T]:
        """Async context manager entry - starts background tasks."""
        # Start background health check
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(),
            name="wsfabric-pool-health-check",
        )

        # Start background cleanup
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="wsfabric-pool-cleanup",
        )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit - closes pool."""
        await self.close()

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _resolve_uri(self, uri_or_path: str) -> str:
        """Resolve a URI or path to a full URI.

        Args:
            uri_or_path: Full URI or relative path.

        Returns:
            Full URI string.

        Raises:
            ValueError: If relative path without base_uri.
        """
        parsed = urlparse(uri_or_path)
        if parsed.scheme:
            # Already a full URI
            return uri_or_path

        if self._base_uri is None:
            msg = "Relative path requires base_uri to be set"
            raise ValueError(msg)

        return urljoin(self._base_uri, uri_or_path)

    def _get_idle_connection(self, uri: str) -> _PooledConnectionState | None:
        """Get an idle connection for the given URI.

        Must be called with _lock held.

        Args:
            uri: The connection URI.

        Returns:
            An idle connection state, or None if none available.
        """
        if uri not in self._connections:
            return None

        for conn_state in self._connections[uri]:
            if not conn_state.in_use:
                return conn_state

        return None

    async def _create_connection(self, uri: str) -> _PooledConnectionState:
        """Create a new connection.

        Args:
            uri: The connection URI.

        Returns:
            The new connection state.
        """
        manager: WebSocket[T] = WebSocket(uri, **self._manager_kwargs)
        await manager.connect()

        state = _PooledConnectionState(manager=manager, uri=uri)

        async with self._lock:
            if uri not in self._connections:
                self._connections[uri] = []
            self._connections[uri].append(state)
            self._connection_count += 1

        return state

    async def _close_connection(self, state: _PooledConnectionState) -> None:
        """Close a connection.

        Args:
            state: The connection state to close.
        """
        with contextlib.suppress(Exception):
            await state.manager.close()

    def _remove_connection(self, state: _PooledConnectionState) -> None:
        """Remove a connection from the pool.

        Must be called with _lock held.

        Args:
            state: The connection state to remove.
        """
        uri = state.uri
        if uri in self._connections:
            try:
                self._connections[uri].remove(state)
                if not self._connections[uri]:
                    del self._connections[uri]
            except ValueError:
                pass

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not self._closed:
            try:
                await asyncio.sleep(self._config.health_check_interval)

                if self._closed:
                    break

                # Check all connections
                async with self._lock:
                    to_close: list[_PooledConnectionState] = []

                    for conn_list in self._connections.values():
                        for conn_state in conn_list:
                            # Skip in-use connections
                            if conn_state.in_use:
                                continue

                            # Check if connection is dead
                            if conn_state.manager.state.is_terminal:
                                to_close.append(conn_state)

                # Close dead connections (outside lock)
                for state in to_close:
                    await self._close_connection(state)
                    async with self._lock:
                        self._remove_connection(state)

            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop for idle connections."""
        while not self._closed:
            try:
                # Check every 30 seconds
                await asyncio.sleep(30.0)

                if self._closed:
                    break

                to_close: list[_PooledConnectionState] = []

                async with self._lock:
                    for conn_list in self._connections.values():
                        for conn_state in conn_list:
                            # Skip in-use connections
                            if conn_state.in_use:
                                continue

                            # Check if idle too long
                            if conn_state.idle_time > self._config.max_idle_time:
                                to_close.append(conn_state)

                # Close idle connections (outside lock)
                for state in to_close:
                    await self._close_connection(state)
                    async with self._lock:
                        self._remove_connection(state)

            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def __repr__(self) -> str:
        """Return string representation."""
        stats = self.stats()
        return (
            f"ConnectionPool(max_connections={self._config.max_connections}, "
            f"active={stats.active_connections}, idle={stats.idle_connections}, "
            f"closed={self._closed})"
        )
