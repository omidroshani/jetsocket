"""Tests for ConnectionPool."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wsfabric.exceptions import (
    InvalidStateError,
    PoolClosedError,
    PoolExhaustedError,
)
from wsfabric.pool import (
    ConnectionPool,
    ConnectionPoolConfig,
    PooledConnection,
    PoolStats,
    _PooledConnectionState,
)
from wsfabric.state import ConnectionState


class TestConnectionPoolConfig:
    """Tests for ConnectionPoolConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ConnectionPoolConfig()

        assert config.max_connections == 10
        assert config.max_idle_time == 300.0
        assert config.health_check_interval == 30.0
        assert config.acquire_timeout == 10.0

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = ConnectionPoolConfig(
            max_connections=5,
            max_idle_time=60.0,
            health_check_interval=10.0,
            acquire_timeout=5.0,
        )

        assert config.max_connections == 5
        assert config.max_idle_time == 60.0
        assert config.health_check_interval == 10.0
        assert config.acquire_timeout == 5.0

    def test_invalid_max_connections(self) -> None:
        """Test that invalid max_connections raises."""
        with pytest.raises(ValueError, match="max_connections must be positive"):
            ConnectionPoolConfig(max_connections=0)

        with pytest.raises(ValueError, match="max_connections must be positive"):
            ConnectionPoolConfig(max_connections=-1)

    def test_invalid_max_idle_time(self) -> None:
        """Test that invalid max_idle_time raises."""
        with pytest.raises(ValueError, match="max_idle_time must be positive"):
            ConnectionPoolConfig(max_idle_time=0)

        with pytest.raises(ValueError, match="max_idle_time must be positive"):
            ConnectionPoolConfig(max_idle_time=-1.0)

    def test_invalid_health_check_interval(self) -> None:
        """Test that invalid health_check_interval raises."""
        with pytest.raises(ValueError, match="health_check_interval must be positive"):
            ConnectionPoolConfig(health_check_interval=0)

    def test_invalid_acquire_timeout(self) -> None:
        """Test that invalid acquire_timeout raises."""
        with pytest.raises(ValueError, match="acquire_timeout must be positive"):
            ConnectionPoolConfig(acquire_timeout=0)


class TestPoolStats:
    """Tests for PoolStats."""

    def test_pool_stats_creation(self) -> None:
        """Test PoolStats creation."""
        stats = PoolStats(
            total_connections=10,
            active_connections=3,
            idle_connections=5,
            total_messages_sent=100,
            total_messages_received=200,
            total_reconnects=2,
        )

        assert stats.total_connections == 10
        assert stats.active_connections == 3
        assert stats.idle_connections == 5
        assert stats.total_messages_sent == 100
        assert stats.total_messages_received == 200
        assert stats.total_reconnects == 2

    def test_pool_stats_immutable(self) -> None:
        """Test that PoolStats is immutable."""
        stats = PoolStats(
            total_connections=1,
            active_connections=1,
            idle_connections=0,
            total_messages_sent=0,
            total_messages_received=0,
            total_reconnects=0,
        )

        # Should raise on assignment
        with pytest.raises(AttributeError):
            stats.total_connections = 2  # type: ignore[misc]


class TestPooledConnectionState:
    """Tests for _PooledConnectionState."""

    def test_state_creation(self) -> None:
        """Test state creation."""
        mock_manager = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        assert state.uri == "wss://example.com/ws"
        assert state.in_use is False

    def test_mark_used(self) -> None:
        """Test marking state as used."""
        mock_manager = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        state.mark_used()

        assert state.in_use is True

    def test_mark_released(self) -> None:
        """Test marking state as released."""
        mock_manager = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        state.mark_used()
        state.mark_released()

        assert state.in_use is False

    def test_idle_time(self) -> None:
        """Test idle time calculation."""
        mock_manager = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        # Should be small initially
        assert state.idle_time < 1.0

        # Wait a bit
        time.sleep(0.1)

        assert state.idle_time >= 0.1


class TestPooledConnection:
    """Tests for PooledConnection."""

    def test_pooled_connection_properties(self) -> None:
        """Test PooledConnection properties."""
        mock_manager = MagicMock()
        mock_manager.is_connected = True
        mock_manager.latency_ms = 10.5

        mock_pool = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)

        assert conn.uri == "wss://example.com/ws"
        assert conn.is_connected is True
        assert conn.latency_ms == 10.5

    @pytest.mark.asyncio
    async def test_pooled_connection_send(self) -> None:
        """Test PooledConnection send."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)

        await conn.send({"test": "data"})

        mock_manager.send.assert_called_once_with({"test": "data"})

    @pytest.mark.asyncio
    async def test_pooled_connection_send_after_release(self) -> None:
        """Test PooledConnection send after release raises."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.release = AsyncMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)
        await conn.release()

        with pytest.raises(InvalidStateError, match="released"):
            await conn.send({"test": "data"})

    @pytest.mark.asyncio
    async def test_pooled_connection_send_raw(self) -> None:
        """Test PooledConnection send_raw."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)

        await conn.send_raw(b"raw data", binary=True)

        mock_manager.send_raw.assert_called_once_with(b"raw data", binary=True)

    @pytest.mark.asyncio
    async def test_pooled_connection_send_raw_after_release(self) -> None:
        """Test PooledConnection send_raw after release raises."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.release = AsyncMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)
        await conn.release()

        with pytest.raises(InvalidStateError, match="released"):
            await conn.send_raw(b"raw data")

    @pytest.mark.asyncio
    async def test_pooled_connection_recv(self) -> None:
        """Test PooledConnection recv."""
        mock_manager = AsyncMock()
        mock_manager.recv.return_value = {"msg": "data"}
        mock_pool = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn: PooledConnection[dict[str, str]] = PooledConnection(mock_pool, state)

        result = await conn.recv()

        assert result == {"msg": "data"}
        mock_manager.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_pooled_connection_recv_after_release(self) -> None:
        """Test PooledConnection recv after release raises."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.release = AsyncMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)
        await conn.release()

        with pytest.raises(InvalidStateError, match="released"):
            await conn.recv()

    @pytest.mark.asyncio
    async def test_pooled_connection_context_manager(self) -> None:
        """Test PooledConnection as context manager."""
        mock_manager = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.release = AsyncMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)

        async with conn:
            await conn.send({"test": "data"})

        mock_pool.release.assert_called_once()

    def test_pooled_connection_repr(self) -> None:
        """Test PooledConnection repr."""
        mock_manager = MagicMock()
        mock_manager.is_connected = True
        mock_pool = MagicMock()
        state = _PooledConnectionState(manager=mock_manager, uri="wss://example.com/ws")

        conn = PooledConnection(mock_pool, state)
        repr_str = repr(conn)

        assert "PooledConnection" in repr_str
        assert "wss://example.com/ws" in repr_str


class TestConnectionPoolInit:
    """Tests for ConnectionPool initialization."""

    def test_default_init(self) -> None:
        """Test default initialization."""
        pool: ConnectionPool[Any] = ConnectionPool()

        assert pool._config.max_connections == 10
        assert pool._base_uri is None
        assert pool.is_closed is False

    def test_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = ConnectionPoolConfig(max_connections=5)
        pool: ConnectionPool[Any] = ConnectionPool(config)

        assert pool._config.max_connections == 5

    def test_with_base_uri(self) -> None:
        """Test initialization with base URI."""
        pool: ConnectionPool[Any] = ConnectionPool(base_uri="wss://example.com")

        assert pool._base_uri == "wss://example.com"

    def test_with_manager_kwargs(self) -> None:
        """Test initialization with manager kwargs."""
        pool: ConnectionPool[Any] = ConnectionPool(
            manager_kwargs={"compress": False, "connect_timeout": 5.0}
        )

        assert pool._manager_kwargs["compress"] is False
        assert pool._manager_kwargs["connect_timeout"] == 5.0

    def test_repr(self) -> None:
        """Test string representation."""
        pool: ConnectionPool[Any] = ConnectionPool()
        repr_str = repr(pool)

        assert "ConnectionPool" in repr_str
        assert "max_connections=10" in repr_str


class TestConnectionPoolUriResolution:
    """Tests for URI resolution."""

    def test_resolve_full_uri(self) -> None:
        """Test resolving a full URI."""
        pool: ConnectionPool[Any] = ConnectionPool()
        resolved = pool._resolve_uri("wss://example.com/ws")

        assert resolved == "wss://example.com/ws"

    def test_resolve_relative_path(self) -> None:
        """Test resolving a relative path."""
        pool: ConnectionPool[Any] = ConnectionPool(base_uri="wss://example.com")
        resolved = pool._resolve_uri("/ws/stream")

        assert resolved == "wss://example.com/ws/stream"

    def test_resolve_relative_without_base(self) -> None:
        """Test resolving relative path without base raises."""
        pool: ConnectionPool[Any] = ConnectionPool()

        with pytest.raises(ValueError, match="base_uri"):
            pool._resolve_uri("/ws/stream")


class TestConnectionPoolAcquire:
    """Tests for connection acquisition."""

    @pytest.mark.asyncio
    async def test_acquire_closed_pool(self) -> None:
        """Test acquiring from closed pool raises."""
        pool: ConnectionPool[Any] = ConnectionPool()
        pool._closed = True

        with pytest.raises(PoolClosedError):
            await pool.acquire("wss://example.com/ws")

    @pytest.mark.asyncio
    async def test_acquire_timeout(self) -> None:
        """Test acquire timeout raises PoolExhaustedError."""
        config = ConnectionPoolConfig(max_connections=1, acquire_timeout=0.1)
        pool: ConnectionPool[Any] = ConnectionPool(config)

        # Acquire the only available slot
        await pool._semaphore.acquire()

        with pytest.raises(PoolExhaustedError) as exc_info:
            await pool.acquire("wss://example.com/ws", timeout=0.05)

        assert exc_info.value.max_connections == 1
        assert exc_info.value.timeout == 0.05

    @pytest.mark.asyncio
    async def test_acquire_creates_connection(self) -> None:
        """Test that acquire creates a new connection."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.is_connected = True

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            conn = await pool.acquire("wss://example.com/ws")

            assert isinstance(conn, PooledConnection)
            assert conn.uri == "wss://example.com/ws"
            mock_manager.connect.assert_called_once()

            # Release the connection
            await conn.release()

    @pytest.mark.asyncio
    async def test_acquire_reuses_idle_connection(self) -> None:
        """Test that acquire reuses an idle connection."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_stats = MagicMock()
        mock_stats.messages_sent = 0
        mock_stats.messages_received = 0
        mock_stats.reconnect_count = 0

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.is_connected = True
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            # Acquire and release
            conn1 = await pool.acquire("wss://example.com/ws")
            await conn1.release()

            # Acquire again - should reuse
            conn2 = await pool.acquire("wss://example.com/ws")

            # Should only have created one manager
            assert mock_manager.connect.call_count == 1

            await conn2.release()


class TestConnectionPoolRelease:
    """Tests for connection release."""

    @pytest.mark.asyncio
    async def test_release_returns_to_pool(self) -> None:
        """Test that release returns connection to pool."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_stats = MagicMock()
        mock_stats.messages_sent = 0
        mock_stats.messages_received = 0
        mock_stats.reconnect_count = 0

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.is_connected = True
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            conn = await pool.acquire("wss://example.com/ws")

            stats_before = pool.stats()
            assert stats_before.active_connections == 1

            await conn.release()

            stats_after = pool.stats()
            assert stats_after.active_connections == 0
            assert stats_after.idle_connections == 1

    @pytest.mark.asyncio
    async def test_release_dead_connection_closes(self) -> None:
        """Test that releasing a dead connection closes it."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_stats = MagicMock()
        mock_stats.messages_sent = 0
        mock_stats.messages_received = 0
        mock_stats.reconnect_count = 0

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            conn = await pool.acquire("wss://example.com/ws")

            # Simulate connection death
            mock_manager.state = ConnectionState.CLOSED

            await conn.release()

            # Should have called close
            mock_manager.close.assert_called()


class TestConnectionPoolStats:
    """Tests for pool statistics."""

    @pytest.mark.asyncio
    async def test_stats_empty_pool(self) -> None:
        """Test stats on empty pool."""
        pool: ConnectionPool[Any] = ConnectionPool()
        stats = pool.stats()

        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.idle_connections == 0
        assert stats.total_messages_sent == 0
        assert stats.total_messages_received == 0
        assert stats.total_reconnects == 0

    @pytest.mark.asyncio
    async def test_stats_with_connections(self) -> None:
        """Test stats with active connections."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_stats = MagicMock()
        mock_stats.messages_sent = 10
        mock_stats.messages_received = 20
        mock_stats.reconnect_count = 1

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            conn = await pool.acquire("wss://example.com/ws")

            stats = pool.stats()

            assert stats.total_connections == 1
            assert stats.active_connections == 1
            assert stats.idle_connections == 0
            assert stats.total_messages_sent == 10
            assert stats.total_messages_received == 20
            assert stats.total_reconnects == 1

            await conn.release()


class TestConnectionPoolClose:
    """Tests for pool closing."""

    @pytest.mark.asyncio
    async def test_close_empty_pool(self) -> None:
        """Test closing an empty pool."""
        pool: ConnectionPool[Any] = ConnectionPool()

        await pool.close()

        assert pool.is_closed is True

    @pytest.mark.asyncio
    async def test_close_with_connections(self) -> None:
        """Test closing pool with connections."""
        pool: ConnectionPool[Any] = ConnectionPool()

        mock_stats = MagicMock()
        mock_stats.messages_sent = 0
        mock_stats.messages_received = 0
        mock_stats.reconnect_count = 0

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            conn = await pool.acquire("wss://example.com/ws")
            await conn.release()

            await pool.close()

            assert pool.is_closed is True
            mock_manager.close.assert_called()

    @pytest.mark.asyncio
    async def test_close_cancels_background_tasks(self) -> None:
        """Test closing cancels background tasks."""
        pool: ConnectionPool[Any] = ConnectionPool()

        # Start context manager to create background tasks
        async with pool:
            assert pool._health_check_task is not None
            assert pool._cleanup_task is not None

        # After exit, tasks should be cancelled
        assert pool._health_check_task is None
        assert pool._cleanup_task is None


class TestConnectionPoolContextManager:
    """Tests for context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_starts_tasks(self) -> None:
        """Test context manager starts background tasks."""
        pool: ConnectionPool[Any] = ConnectionPool()

        async with pool:
            assert pool._health_check_task is not None
            assert pool._cleanup_task is not None
            assert not pool._health_check_task.done()
            assert not pool._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exit(self) -> None:
        """Test context manager closes pool on exit."""
        pool: ConnectionPool[Any] = ConnectionPool()

        async with pool:
            pass

        assert pool.is_closed is True

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exception(self) -> None:
        """Test context manager closes on exception."""
        pool: ConnectionPool[Any] = ConnectionPool()

        with pytest.raises(RuntimeError):
            async with pool:
                raise RuntimeError("Test error")

        assert pool.is_closed is True


class TestConnectionPoolHealthCheck:
    """Tests for health check behavior."""

    @pytest.mark.asyncio
    async def test_health_check_removes_dead_connections(self) -> None:
        """Test health check removes dead connections."""
        config = ConnectionPoolConfig(health_check_interval=0.05)
        pool: ConnectionPool[Any] = ConnectionPool(config)

        mock_stats = MagicMock()
        mock_stats.messages_sent = 0
        mock_stats.messages_received = 0
        mock_stats.reconnect_count = 0

        mock_manager = AsyncMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.pool.WebSocket", return_value=mock_manager):
            async with pool:
                conn = await pool.acquire("wss://example.com/ws")
                await conn.release()

                # Simulate connection death
                mock_manager.state = ConnectionState.CLOSED

                # Wait for health check
                await asyncio.sleep(0.1)

                # Connection should be removed
                stats = pool.stats()
                assert stats.idle_connections == 0


class TestPoolExceptions:
    """Tests for pool exceptions."""

    def test_pool_exhausted_error(self) -> None:
        """Test PoolExhaustedError creation."""
        error = PoolExhaustedError("Pool exhausted", max_connections=5, timeout=10.0)

        assert error.max_connections == 5
        assert error.timeout == 10.0
        assert "Pool exhausted" in str(error)

    def test_pool_closed_error(self) -> None:
        """Test PoolClosedError creation."""
        error = PoolClosedError("Pool is closed")

        assert "Pool is closed" in str(error)
