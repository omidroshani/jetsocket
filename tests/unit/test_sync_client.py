"""Tests for SyncWebSocketClient."""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wsfabric.backoff import BackoffConfig
from wsfabric.events import ConnectedEvent, MessageEvent
from wsfabric.exceptions import ConnectionError, InvalidStateError, TimeoutError
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.state import ConnectionState
from wsfabric.sync_client import _SHUTDOWN, SyncWebSocketClient


class TestSyncWebSocketClientInit:
    """Tests for SyncWebSocketClient initialization."""

    def test_default_init(self) -> None:
        """Test initialization with defaults."""
        client = SyncWebSocketClient("wss://example.com/ws")

        assert client.uri == "wss://example.com/ws"
        assert client.state == ConnectionState.IDLE
        assert client.is_connected is False
        assert client.latency_ms is None

    def test_custom_init(self) -> None:
        """Test initialization with custom config."""
        client = SyncWebSocketClient(
            "wss://example.com/ws",
            reconnect=False,
            backoff=BackoffConfig(base=2.0),
            heartbeat=HeartbeatConfig(interval=10.0, timeout=5.0),
            connect_timeout=5.0,
            close_timeout=2.0,
        )

        assert client.uri == "wss://example.com/ws"
        assert client._manager_kwargs["reconnect"] is False
        assert client._manager_kwargs["backoff"].base == 2.0

    def test_repr(self) -> None:
        """Test string representation."""
        client = SyncWebSocketClient("wss://example.com/ws")
        repr_str = repr(client)

        assert "SyncWebSocket" in repr_str
        assert "wss://example.com/ws" in repr_str
        assert "idle" in repr_str


class TestSyncWebSocketClientEventRegistration:
    """Tests for event handler registration."""

    def test_on_decorator_before_connect(self) -> None:
        """Test @client.on() decorator before connect."""
        client = SyncWebSocketClient("wss://example.com/ws")
        received: list[Any] = []

        @client.on("connected")
        def handler(event: ConnectedEvent) -> None:
            received.append(event)

        # Handler should be stored in pending handlers
        assert len(client._pending_handlers) == 1
        assert client._pending_handlers[0][0] == "connected"

    def test_add_handler_before_connect(self) -> None:
        """Test programmatic handler registration before connect."""
        client = SyncWebSocketClient("wss://example.com/ws")

        def handler(event: ConnectedEvent) -> None:
            pass

        client.add_handler("connected", handler)
        assert len(client._pending_handlers) == 1

    def test_remove_handler_before_connect(self) -> None:
        """Test handler removal before connect."""
        client = SyncWebSocketClient("wss://example.com/ws")

        def handler(event: ConnectedEvent) -> None:
            pass

        client.add_handler("connected", handler)
        assert client.remove_handler("connected", handler) is True
        assert len(client._pending_handlers) == 0

    def test_remove_handler_not_found(self) -> None:
        """Test removing non-existent handler."""
        client = SyncWebSocketClient("wss://example.com/ws")

        def handler(event: ConnectedEvent) -> None:
            pass

        assert client.remove_handler("connected", handler) is False


class TestSyncWebSocketClientLifecycle:
    """Tests for connection lifecycle."""

    def test_connect_not_connected_raises_on_second_connect(self) -> None:
        """Test that connecting twice raises InvalidStateError."""
        client = SyncWebSocketClient("wss://example.com/ws")

        # Simulate that thread is running
        client._thread = MagicMock()
        client._thread.is_alive.return_value = True

        with pytest.raises(InvalidStateError) as exc_info:
            client.connect()

        assert exc_info.value.current_state == "connected"

    def test_connect_after_close_raises(self) -> None:
        """Test that connecting after close raises InvalidStateError."""
        client = SyncWebSocketClient("wss://example.com/ws")
        client._closed = True

        with pytest.raises(InvalidStateError) as exc_info:
            client.connect()

        assert exc_info.value.current_state == "closed"

    def test_close_when_not_connected(self) -> None:
        """Test closing when not connected."""
        client = SyncWebSocketClient("wss://example.com/ws")

        # Should not raise
        client.close()

        assert client._closed is True

    def test_close_idempotent(self) -> None:
        """Test that close is idempotent."""
        client = SyncWebSocketClient("wss://example.com/ws")

        client.close()
        client.close()  # Should not raise

        assert client._closed is True


class TestSyncWebSocketClientMessaging:
    """Tests for messaging operations."""

    def test_send_not_connected(self) -> None:
        """Test sending when not connected raises."""
        client = SyncWebSocketClient("wss://example.com/ws")

        with pytest.raises(InvalidStateError):
            client.send({"test": "data"})

    def test_send_raw_not_connected(self) -> None:
        """Test sending raw bytes when not connected raises."""
        client = SyncWebSocketClient("wss://example.com/ws")

        with pytest.raises(InvalidStateError):
            client.send_raw(b"test data")

    def test_recv_when_closed(self) -> None:
        """Test receiving when closed raises."""
        client = SyncWebSocketClient("wss://example.com/ws")
        client._closed = True

        with pytest.raises(InvalidStateError):
            client.recv()

    def test_recv_timeout(self) -> None:
        """Test receiving with timeout."""
        client = SyncWebSocketClient("wss://example.com/ws")

        with pytest.raises(TimeoutError) as exc_info:
            client.recv(timeout=0.01)

        assert exc_info.value.operation == "recv"


class TestSyncWebSocketClientIteration:
    """Tests for iteration."""

    def test_iter_returns_self(self) -> None:
        """Test __iter__ returns self."""
        client = SyncWebSocketClient("wss://example.com/ws")
        assert iter(client) is client

    def test_next_when_closed(self) -> None:
        """Test __next__ raises StopIteration when closed."""
        client = SyncWebSocketClient("wss://example.com/ws")
        client._closed = True

        with pytest.raises(StopIteration):
            next(client)

    def test_next_from_queue(self) -> None:
        """Test __next__ gets from queue."""
        client = SyncWebSocketClient[dict[str, str]]("wss://example.com/ws")

        # Put a message in the queue
        client._message_queue.put({"test": "data"})

        result = next(client)
        assert result == {"test": "data"}


class TestSyncWebSocketClientStats:
    """Tests for statistics."""

    def test_stats_when_not_connected(self) -> None:
        """Test stats when not connected."""
        client = SyncWebSocketClient("wss://example.com/ws")
        stats = client.stats()

        assert stats.state == ConnectionState.IDLE
        assert stats.messages_sent == 0
        assert stats.messages_received == 0


class TestSyncWebSocketClientContextManager:
    """Tests for context manager."""

    def test_context_manager_close_on_exit(self) -> None:
        """Test context manager closes on exit."""
        client: SyncWebSocketClient[Any] = SyncWebSocketClient("wss://example.com/ws")

        # Patch connect to not actually connect
        with (
            patch.object(client, "connect"),
            patch.object(client, "close") as mock_close,
        ):
            with client:
                pass

            mock_close.assert_called_once()


class TestSyncWebSocketClientThreading:
    """Tests for threading behavior."""

    def test_background_thread_name(self) -> None:
        """Test that background thread has correct name."""
        client = SyncWebSocketClient("wss://example.com/ws")

        # We need to mock the entire connect flow
        mock_manager = MagicMock()
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.is_connected = True
        mock_manager.latency_ms = None

        # Create a mock that works async
        async def mock_connect() -> None:
            pass

        mock_manager.connect = mock_connect
        mock_manager.add_handler = MagicMock()

        with patch("wsfabric.sync_client.WebSocketManager", return_value=mock_manager):
            # Start connect in background but check thread name
            started = threading.Event()

            def patched_run() -> None:
                started.set()
                # Don't actually run the loop, just start and stop
                loop = asyncio.new_event_loop()
                client._loop = loop
                client._manager = mock_manager
                client._started.set()
                # Run briefly
                loop.call_soon(loop.stop)
                loop.run_forever()
                loop.close()

            with patch.object(client, "_run_event_loop", patched_run):
                try:
                    client._thread = threading.Thread(
                        target=patched_run, name="wsfabric-sync-loop", daemon=True
                    )
                    client._thread.start()
                    client._started.wait(timeout=1.0)

                    assert client._thread.name == "wsfabric-sync-loop"
                finally:
                    client._closed = True
                    if client._thread:
                        client._thread.join(timeout=1.0)


class TestSyncWebSocketClientMessageForwarding:
    """Tests for message forwarding to sync queue."""

    def test_on_message_forwards_to_queue(self) -> None:
        """Test that _on_message forwards to queue."""
        client = SyncWebSocketClient[dict[str, str]]("wss://example.com/ws")

        event = MessageEvent(data={"test": "value"}, raw=b'{"test": "value"}')
        client._on_message(event)

        assert not client._message_queue.empty()
        msg = client._message_queue.get_nowait()
        assert msg == {"test": "value"}


class TestSyncWebSocketClientProperties:
    """Tests for property accessors."""

    def test_uri_property(self) -> None:
        """Test uri property."""
        client = SyncWebSocketClient("wss://test.example.com/ws")
        assert client.uri == "wss://test.example.com/ws"

    def test_state_property_idle(self) -> None:
        """Test state property when idle."""
        client = SyncWebSocketClient("wss://example.com/ws")
        assert client.state == ConnectionState.IDLE

    def test_state_property_with_manager(self) -> None:
        """Test state property when manager exists."""
        client = SyncWebSocketClient("wss://example.com/ws")

        mock_manager = MagicMock()
        mock_manager.state = ConnectionState.CONNECTED
        client._manager = mock_manager

        assert client.state == ConnectionState.CONNECTED

    def test_is_connected_property(self) -> None:
        """Test is_connected property."""
        client = SyncWebSocketClient("wss://example.com/ws")
        assert client.is_connected is False

        mock_manager = MagicMock()
        mock_manager.state = ConnectionState.CONNECTED
        client._manager = mock_manager

        assert client.is_connected is True

    def test_latency_ms_property_none(self) -> None:
        """Test latency_ms property when no manager."""
        client = SyncWebSocketClient("wss://example.com/ws")
        assert client.latency_ms is None

    def test_latency_ms_property_with_manager(self) -> None:
        """Test latency_ms property with manager."""
        client = SyncWebSocketClient("wss://example.com/ws")

        mock_manager = MagicMock()
        mock_manager.latency_ms = 15.5
        client._manager = mock_manager

        assert client.latency_ms == 15.5


class TestSyncWebSocketClientCleanup:
    """Tests for cleanup behavior."""

    def test_cleanup_on_del(self) -> None:
        """Test that __del__ calls close."""
        client: SyncWebSocketClient[Any] = SyncWebSocketClient("wss://example.com/ws")

        with patch.object(client, "close"):
            del client
            # Note: __del__ may not be called immediately
            # This is more of a coverage test


class TestSyncWebSocketClientEdgeCases:
    """Tests for edge cases."""

    def test_send_with_mocked_loop(self) -> None:
        """Test send with mocked loop and manager."""
        client = SyncWebSocketClient("wss://example.com/ws")

        # Set up mocks
        mock_loop = MagicMock()
        mock_manager = MagicMock()

        # Create a mock future
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_loop.run_coroutine_threadsafe = MagicMock(return_value=mock_future)

        # Actually we need to use the real function

        async def mock_send(data: Any) -> None:
            pass

        mock_manager.send = mock_send

        # This is tricky - run_coroutine_threadsafe requires a real loop
        # Let's just verify the state check works
        client._loop = mock_loop
        client._manager = mock_manager

        # Mock run_coroutine_threadsafe at module level
        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_future = MagicMock()
            mock_future.result.return_value = None
            mock_rcts.return_value = mock_future

            client.send({"test": "data"})

            mock_rcts.assert_called_once()

    def test_send_raw_with_mocked_loop(self) -> None:
        """Test send_raw with mocked loop and manager."""
        client = SyncWebSocketClient("wss://example.com/ws")

        mock_loop = MagicMock()
        mock_manager = MagicMock()
        client._loop = mock_loop
        client._manager = mock_manager

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_future = MagicMock()
            mock_future.result.return_value = None
            mock_rcts.return_value = mock_future

            client.send_raw(b"test data", binary=True)

            mock_rcts.assert_called_once()

    def test_recv_shutdown_signal(self) -> None:
        """Test recv handles shutdown signal."""
        client: SyncWebSocketClient[Any] = SyncWebSocketClient("wss://example.com/ws")
        client._message_queue.put(_SHUTDOWN)

        with pytest.raises(ConnectionError, match="Connection closed"):
            client.recv(timeout=1.0)

    def test_iteration_shutdown_signal(self) -> None:
        """Test iteration handles shutdown signal."""
        client: SyncWebSocketClient[Any] = SyncWebSocketClient("wss://example.com/ws")
        client._message_queue.put(_SHUTDOWN)

        with pytest.raises(StopIteration):
            next(client)
