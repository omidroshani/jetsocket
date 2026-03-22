"""Tests for WebSocket."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wsfabric.backoff import BackoffConfig
from wsfabric.events import (
    ConnectedEvent,
    ConnectingEvent,
    DisconnectedEvent,
    ErrorEvent,
    MessageEvent,
    StateChangeEvent,
)
from wsfabric.exceptions import ConnectionError, HandshakeError, InvalidStateError
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.manager import WebSocket
from wsfabric.state import ConnectionState
from wsfabric.types import CloseCode, Frame, Opcode


class TestWebSocketInit:
    """Tests for WebSocket initialization."""

    def test_default_init(self) -> None:
        """Test initialization with defaults."""
        ws = WebSocket("wss://example.com/ws")

        assert ws.uri == "wss://example.com/ws"
        assert ws.state == ConnectionState.IDLE
        assert ws.is_connected is False
        assert ws.latency_ms is None

    def test_custom_init(self) -> None:
        """Test initialization with custom config."""
        ws = WebSocket(
            "wss://example.com/ws",
            reconnect=False,
            backoff=BackoffConfig(base=2.0),
            heartbeat=HeartbeatConfig(interval=10.0, timeout=5.0),
            connect_timeout=5.0,
            close_timeout=2.0,
            max_message_size=1024 * 1024,
        )

        assert ws.uri == "wss://example.com/ws"
        assert ws._reconnect_enabled is False
        assert ws._backoff_config.base == 2.0
        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 10.0

    def test_custom_serializer(self) -> None:
        """Test custom serializer/deserializer."""

        def custom_serializer(data: Any) -> bytes:
            return str(data).encode()

        def custom_deserializer(data: bytes) -> str:
            return data.decode().upper()

        ws = WebSocket(
            "wss://example.com/ws",
            serializer=custom_serializer,
            deserializer=custom_deserializer,
        )

        assert ws._serializer({"test": 1}) == b"{'test': 1}"
        assert ws._deserializer(b"hello") == "HELLO"


class TestWebSocketEventRegistration:
    """Tests for event handler registration."""

    def test_on_decorator(self) -> None:
        """Test @ws.on() decorator."""
        ws = WebSocket("wss://example.com/ws")
        received: list[ConnectedEvent] = []

        @ws.on("connected")
        async def handler(event: ConnectedEvent) -> None:
            received.append(event)

        assert ws._emitter.handler_count("connected") == 1

    def test_add_handler(self) -> None:
        """Test programmatic handler registration."""
        ws = WebSocket("wss://example.com/ws")

        async def handler(event: ConnectedEvent) -> None:
            pass

        ws.add_handler("connected", handler)
        assert ws._emitter.handler_count("connected") == 1

    def test_remove_handler(self) -> None:
        """Test handler removal."""
        ws = WebSocket("wss://example.com/ws")

        async def handler(event: ConnectedEvent) -> None:
            pass

        ws.add_handler("connected", handler)
        assert ws.remove_handler("connected", handler) is True
        assert ws._emitter.handler_count("connected") == 0

    def test_remove_handler_not_found(self) -> None:
        """Test removing non-existent handler."""
        ws = WebSocket("wss://example.com/ws")

        async def handler(event: ConnectedEvent) -> None:
            pass

        assert ws.remove_handler("connected", handler) is False


class TestWebSocketStats:
    """Tests for connection statistics."""

    def test_stats_idle(self) -> None:
        """Test stats in idle state."""
        ws = WebSocket("wss://example.com/ws")
        stats = ws.stats()

        assert stats.state == ConnectionState.IDLE
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.errors == 0

    def test_stats_snapshot_is_immutable(self) -> None:
        """Test that stats snapshot is independent."""
        ws = WebSocket("wss://example.com/ws")

        stats1 = ws.stats()
        ws._stats.record_message_sent(100)
        stats2 = ws.stats()

        assert stats1.messages_sent == 0
        assert stats2.messages_sent == 1


class TestWebSocketConnect:
    """Tests for connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_invalid_state(self) -> None:
        """Test connecting from invalid state."""
        ws = WebSocket("wss://example.com/ws")
        ws._state = ConnectionState.CONNECTING

        with pytest.raises(InvalidStateError) as exc_info:
            await ws.connect()

        assert exc_info.value.current_state == "connecting"

    @pytest.mark.asyncio
    async def test_send_not_connected(self) -> None:
        """Test sending when not connected."""
        ws = WebSocket("wss://example.com/ws")

        with pytest.raises(InvalidStateError) as exc_info:
            await ws.send({"test": "data"})

        assert exc_info.value.current_state == "idle"

    @pytest.mark.asyncio
    async def test_recv_not_connected(self) -> None:
        """Test receiving when not connected."""
        ws = WebSocket("wss://example.com/ws")

        with pytest.raises(InvalidStateError) as exc_info:
            await ws.recv()

        assert exc_info.value.current_state == "idle"

    @pytest.mark.asyncio
    async def test_run_not_connected(self) -> None:
        """Test running when not connected."""
        ws = WebSocket("wss://example.com/ws")

        with pytest.raises(InvalidStateError) as exc_info:
            await ws.run()

        assert exc_info.value.current_state == "idle"


class TestWebSocketWithMockedTransport:
    """Tests using mocked transport."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful connection."""
        ws = WebSocket("wss://example.com/ws", reconnect=False)

        events_received: list[str] = []

        @ws.on("connecting")
        async def on_connecting(event: ConnectingEvent) -> None:
            events_received.append("connecting")

        @ws.on("connected")
        async def on_connected(event: ConnectedEvent) -> None:
            events_received.append("connected")

        @ws.on("state_change")
        async def on_state_change(event: StateChangeEvent) -> None:
            events_received.append(f"state:{event.new_state.value}")

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        # Make recv raise to stop the message loop
        mock_transport.recv.side_effect = ConnectionError("Test stop")

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            await ws.connect()
            # Give the message loop a chance to start and stop
            await asyncio.sleep(0.05)

        assert "connecting" in events_received
        assert "connected" in events_received
        assert "state:connecting" in events_received
        assert "state:connected" in events_received
        await ws.close()

    @pytest.mark.asyncio
    async def test_connect_failure_no_reconnect(self) -> None:
        """Test connection failure without reconnect."""
        ws = WebSocket("wss://example.com/ws", reconnect=False)

        error_received: list[Exception] = []

        @ws.on("error")
        async def on_error(event: ErrorEvent) -> None:
            error_received.append(event.error)

        mock_transport = AsyncMock()
        mock_transport.connect.side_effect = ConnectionError("Failed")

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            with pytest.raises(ConnectionError):
                await ws.connect()

        assert ws.state == ConnectionState.FAILED
        assert len(error_received) == 1

    @pytest.mark.asyncio
    async def test_close_idle(self) -> None:
        """Test closing when idle."""
        ws = WebSocket("wss://example.com/ws")

        # Should not raise
        await ws.close()

        assert ws.state == ConnectionState.CLOSED

    @pytest.mark.asyncio
    async def test_close_connected(self) -> None:
        """Test closing when connected."""
        ws = WebSocket("wss://example.com/ws", reconnect=False)

        events_received: list[str] = []

        @ws.on("closing")
        async def on_closing(event: Any) -> None:
            events_received.append("closing")

        @ws.on("closed")
        async def on_closed(event: Any) -> None:
            events_received.append("closed")

        # Make recv block forever so we can close while connected
        recv_event = asyncio.Event()

        async def blocking_recv() -> Frame:
            await recv_event.wait()
            raise ConnectionError("Stopped")

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        mock_transport.recv = blocking_recv

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            await ws.connect()
            # Now close while still connected
            await ws.close()
            recv_event.set()  # Unblock the recv

        assert ws.state == ConnectionState.CLOSED
        assert "closing" in events_received
        assert "closed" in events_received


class TestWebSocketSend:
    """Tests for sending messages."""

    @pytest.mark.asyncio
    async def test_send_serializes_message(self) -> None:
        """Test that send serializes the message."""
        ws = WebSocket("wss://example.com/ws")

        mock_transport = AsyncMock()
        ws._transport = mock_transport
        ws._state = ConnectionState.CONNECTED

        await ws.send({"type": "test", "value": 123})

        mock_transport.send.assert_called_once()
        call_args = mock_transport.send.call_args[0][0]
        assert b'"type": "test"' in call_args or b'"type":"test"' in call_args

    @pytest.mark.asyncio
    async def test_send_raw(self) -> None:
        """Test sending raw bytes."""
        ws = WebSocket("wss://example.com/ws")

        mock_transport = AsyncMock()
        ws._transport = mock_transport
        ws._state = ConnectionState.CONNECTED

        await ws.send_raw(b"raw data", binary=True)

        mock_transport.send.assert_called_once_with(b"raw data", binary=True)

    @pytest.mark.asyncio
    async def test_send_updates_stats(self) -> None:
        """Test that send updates statistics."""
        ws = WebSocket("wss://example.com/ws")

        mock_transport = AsyncMock()
        ws._transport = mock_transport
        ws._state = ConnectionState.CONNECTED

        await ws.send({"test": "data"})

        stats = ws.stats()
        assert stats.messages_sent == 1
        assert stats.bytes_sent > 0


class TestWebSocketIteration:
    """Tests for async iteration."""

    @pytest.mark.asyncio
    async def test_aiter_returns_self(self) -> None:
        """Test __aiter__ returns self."""
        ws = WebSocket("wss://example.com/ws")
        assert ws.__aiter__() is ws

    @pytest.mark.asyncio
    async def test_anext_from_queue(self) -> None:
        """Test __anext__ gets from queue."""
        ws = WebSocket("wss://example.com/ws")
        ws._running = True

        await ws._message_queue.put({"test": "data"})

        result = await ws.__anext__()
        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_anext_stops_when_not_running(self) -> None:
        """Test __anext__ raises StopAsyncIteration when not running."""
        ws = WebSocket("wss://example.com/ws")
        ws._running = False

        with pytest.raises(StopAsyncIteration):
            await ws.__anext__()


class TestWebSocketContextManager:
    """Tests for context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test async context manager."""
        ws = WebSocket("wss://example.com/ws", reconnect=False)

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        mock_transport.recv.side_effect = ConnectionError("Test stop")

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            async with ws:
                # State may have changed due to message loop error, but was connected
                pass

        assert ws.state == ConnectionState.CLOSED


class TestWebSocketFatalErrors:
    """Tests for fatal error classification."""

    def test_fatal_http_codes(self) -> None:
        """Test that certain HTTP codes are fatal."""
        ws = WebSocket("wss://example.com/ws")

        # 401 Unauthorized
        error = HandshakeError("Unauthorized", status_code=401)
        assert ws._is_fatal_error(error) is True

        # 403 Forbidden
        error = HandshakeError("Forbidden", status_code=403)
        assert ws._is_fatal_error(error) is True

        # 404 Not Found
        error = HandshakeError("Not Found", status_code=404)
        assert ws._is_fatal_error(error) is True

        # 410 Gone
        error = HandshakeError("Gone", status_code=410)
        assert ws._is_fatal_error(error) is True

        # 500 is not fatal (server error, may be temporary)
        error = HandshakeError("Server Error", status_code=500)
        assert ws._is_fatal_error(error) is False

    def test_fatal_close_codes(self) -> None:
        """Test that certain close codes are fatal."""
        ws = WebSocket("wss://example.com/ws")

        # Policy violation
        assert ws._is_fatal_code(CloseCode.POLICY_VIOLATION) is True

        # Custom unauthorized
        assert ws._is_fatal_code(4401) is True

        # Custom forbidden
        assert ws._is_fatal_code(4403) is True

        # Normal close is not fatal
        assert ws._is_fatal_code(CloseCode.NORMAL) is False

        # Going away is not fatal
        assert ws._is_fatal_code(CloseCode.GOING_AWAY) is False

    def test_value_error_is_fatal(self) -> None:
        """Test that ValueError is fatal."""
        ws = WebSocket("wss://example.com/ws")

        error = ValueError("Invalid configuration")
        assert ws._is_fatal_error(error) is True

    def test_type_error_is_fatal(self) -> None:
        """Test that TypeError is fatal."""
        ws = WebSocket("wss://example.com/ws")

        error = TypeError("Type mismatch")
        assert ws._is_fatal_error(error) is True


class TestWebSocketReconnect:
    """Tests for reconnection logic."""

    @pytest.mark.asyncio
    async def test_schedule_reconnect_emits_events(self) -> None:
        """Test that reconnection emits proper events."""
        ws = WebSocket(
            "wss://example.com/ws",
            backoff=BackoffConfig(base=0.01, cap=0.1),
        )

        events_received: list[str] = []

        @ws.on("reconnecting")
        async def on_reconnecting(event: Any) -> None:
            events_received.append(f"reconnecting:{event.attempt}")

        @ws.on("state_change")
        async def on_state_change(event: StateChangeEvent) -> None:
            events_received.append(f"state:{event.new_state.value}")

        ws._running = True
        ws._state = ConnectionState.DISCONNECTED

        # Mock the connect to fail once then succeed
        call_count = 0

        async def mock_connect_internal() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call is from _schedule_reconnect
                raise ConnectionError("Still failing")
            else:
                # Simulate successful connection
                ws._state = ConnectionState.CONNECTED
                ws._running = False  # Stop the loop

        with patch.object(ws, "_connect_internal", side_effect=mock_connect_internal):
            try:
                await ws._schedule_reconnect()
            except ConnectionError:
                pass  # Expected on first attempt

        assert "reconnecting:1" in events_received
        assert "state:reconnecting" in events_received
        assert "state:backing_off" in events_received

    @pytest.mark.asyncio
    async def test_reconnect_exhausted(self) -> None:
        """Test behavior when reconnection attempts are exhausted."""
        ws = WebSocket(
            "wss://example.com/ws",
            backoff=BackoffConfig(base=0.01, max_attempts=1),
        )

        error_received: list[Exception] = []

        @ws.on("error")
        async def on_error(event: ErrorEvent) -> None:
            error_received.append(event.error)

        # Exhaust the backoff
        ws._backoff.next_delay()

        ws._running = True
        ws._state = ConnectionState.DISCONNECTED

        await ws._schedule_reconnect()

        assert ws.state == ConnectionState.FAILED
        assert len(error_received) == 1
        assert "exhausted" in str(error_received[0]).lower()


class TestWebSocketHeartbeat:
    """Tests for heartbeat integration."""

    @pytest.mark.asyncio
    async def test_heartbeat_started_on_connect(self) -> None:
        """Test that heartbeat is started when configured."""
        ws = WebSocket(
            "wss://example.com/ws",
            heartbeat=HeartbeatConfig(interval=1.0, timeout=0.5),
            reconnect=False,
        )

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        mock_transport.recv.side_effect = ConnectionError("Test stop")

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            await ws.connect()
            # Heartbeat starts but may stop quickly due to recv error
            heartbeat = ws._heartbeat
            assert heartbeat is not None
            await asyncio.sleep(0.05)
            await ws.close()

    @pytest.mark.asyncio
    async def test_heartbeat_stopped_on_close(self) -> None:
        """Test that heartbeat is stopped on close."""
        ws = WebSocket(
            "wss://example.com/ws",
            heartbeat=HeartbeatConfig(interval=1.0, timeout=0.5),
            reconnect=False,
        )

        # Make recv block so we can close while connected
        recv_event = asyncio.Event()

        async def blocking_recv() -> Frame:
            await recv_event.wait()
            raise ConnectionError("Stopped")

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        mock_transport.recv = blocking_recv

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            await ws.connect()
            await ws.close()
            recv_event.set()

        assert ws._heartbeat is None


class TestWebSocketMessageLoop:
    """Tests for message loop behavior."""

    @pytest.mark.asyncio
    async def test_message_loop_handles_messages(self) -> None:
        """Test that message loop processes messages."""
        ws = WebSocket("wss://example.com/ws", reconnect=False)

        messages_received: list[Any] = []

        @ws.on("message")
        async def on_message(event: MessageEvent[dict[str, str]]) -> None:
            messages_received.append(event.data)

        # Set up mock to return one message then stop
        message_frame = Frame(
            opcode=Opcode.TEXT,
            payload=b'{"type": "test"}',
        )

        recv_call_count = 0

        async def mock_recv() -> Frame:
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return message_frame
            else:
                raise ConnectionError("Stopped")

        mock_transport = AsyncMock()
        mock_transport._subprotocol = None
        mock_transport._extensions = []
        mock_transport.recv = mock_recv

        with patch("wsfabric.manager.AsyncTransport", return_value=mock_transport):
            await ws.connect()
            # Wait for message to be processed
            await asyncio.sleep(0.1)
            await ws.close()

        assert len(messages_received) == 1
        assert messages_received[0] == {"type": "test"}
