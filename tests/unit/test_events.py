"""Tests for the event system."""

from __future__ import annotations

import asyncio

import pytest

from wsfabric.events import (
    ClosedEvent,
    ClosingEvent,
    ConnectedEvent,
    ConnectingEvent,
    DisconnectedEvent,
    ErrorEvent,
    EventEmitter,
    MessageEvent,
    PingEvent,
    PongEvent,
    RawMessageEvent,
    ReconnectedEvent,
    ReconnectingEvent,
    StateChangeEvent,
)
from wsfabric.state import ConnectionState


class TestConnectingEvent:
    """Tests for ConnectingEvent dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        event = ConnectingEvent(uri="wss://example.com", attempt=1)
        assert event.uri == "wss://example.com"
        assert event.attempt == 1

    def test_immutability(self) -> None:
        """Test that the dataclass is frozen."""
        event = ConnectingEvent(uri="wss://example.com", attempt=1)
        with pytest.raises(AttributeError):
            event.uri = "wss://other.com"  # type: ignore[misc]


class TestConnectedEvent:
    """Tests for ConnectedEvent dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creation with minimal args."""
        event = ConnectedEvent(uri="wss://example.com")
        assert event.uri == "wss://example.com"
        assert event.subprotocol is None
        assert event.extensions == []

    def test_creation_full(self) -> None:
        """Test creation with all args."""
        event = ConnectedEvent(
            uri="wss://example.com",
            subprotocol="graphql-transport-ws",
            extensions=["permessage-deflate"],
        )
        assert event.uri == "wss://example.com"
        assert event.subprotocol == "graphql-transport-ws"
        assert event.extensions == ["permessage-deflate"]


class TestDisconnectedEvent:
    """Tests for DisconnectedEvent dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        event = DisconnectedEvent(code=1000, reason="Normal closure", was_clean=True)
        assert event.code == 1000
        assert event.reason == "Normal closure"
        assert event.was_clean is True

    def test_unclean_disconnect(self) -> None:
        """Test unclean disconnect."""
        event = DisconnectedEvent(code=1006, reason="", was_clean=False)
        assert event.was_clean is False


class TestReconnectingEvent:
    """Tests for ReconnectingEvent dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creation without error."""
        event = ReconnectingEvent(attempt=1, delay=1.5)
        assert event.attempt == 1
        assert event.delay == 1.5
        assert event.last_error is None

    def test_creation_with_error(self) -> None:
        """Test creation with error."""
        error = ConnectionError("Connection lost")
        event = ReconnectingEvent(attempt=2, delay=3.0, last_error=error)
        assert event.attempt == 2
        assert event.delay == 3.0
        assert event.last_error is error


class TestReconnectedEvent:
    """Tests for ReconnectedEvent dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        event = ReconnectedEvent(
            uri="wss://example.com", attempt=3, downtime_seconds=5.2
        )
        assert event.uri == "wss://example.com"
        assert event.attempt == 3
        assert event.downtime_seconds == 5.2


class TestMessageEvent:
    """Tests for MessageEvent dataclass."""

    def test_creation_dict(self) -> None:
        """Test with dict data."""
        data = {"type": "hello"}
        raw = b'{"type": "hello"}'
        event: MessageEvent[dict[str, str]] = MessageEvent(data=data, raw=raw)
        assert event.data == data
        assert event.raw == raw

    def test_creation_string(self) -> None:
        """Test with string data."""
        event: MessageEvent[str] = MessageEvent(data="hello", raw=b"hello")
        assert event.data == "hello"


class TestRawMessageEvent:
    """Tests for RawMessageEvent dataclass."""

    def test_text_message(self) -> None:
        """Test text opcode."""
        event = RawMessageEvent(data=b"hello", opcode=1)
        assert event.data == b"hello"
        assert event.opcode == 1

    def test_binary_message(self) -> None:
        """Test binary opcode."""
        event = RawMessageEvent(data=b"\x00\x01\x02", opcode=2)
        assert event.opcode == 2


class TestErrorEvent:
    """Tests for ErrorEvent dataclass."""

    def test_non_fatal_error(self) -> None:
        """Test non-fatal error."""
        error = ValueError("Bad value")
        event = ErrorEvent(error=error, fatal=False)
        assert event.error is error
        assert event.fatal is False

    def test_fatal_error(self) -> None:
        """Test fatal error."""
        error = ConnectionError("Connection refused")
        event = ErrorEvent(error=error, fatal=True)
        assert event.fatal is True


class TestStateChangeEvent:
    """Tests for StateChangeEvent dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        event = StateChangeEvent(
            old_state=ConnectionState.IDLE, new_state=ConnectionState.CONNECTING
        )
        assert event.old_state == ConnectionState.IDLE
        assert event.new_state == ConnectionState.CONNECTING


class TestPingEvent:
    """Tests for PingEvent dataclass."""

    def test_empty_payload(self) -> None:
        """Test empty ping payload."""
        event = PingEvent(payload=b"")
        assert event.payload == b""

    def test_payload_with_data(self) -> None:
        """Test ping with payload."""
        event = PingEvent(payload=b"heartbeat")
        assert event.payload == b"heartbeat"


class TestPongEvent:
    """Tests for PongEvent dataclass."""

    def test_without_latency(self) -> None:
        """Test pong without latency measurement."""
        event = PongEvent(payload=b"")
        assert event.latency_ms is None

    def test_with_latency(self) -> None:
        """Test pong with latency."""
        event = PongEvent(payload=b"", latency_ms=15.3)
        assert event.latency_ms == 15.3


class TestClosingEvent:
    """Tests for ClosingEvent dataclass."""

    def test_local_close(self) -> None:
        """Test locally initiated close."""
        event = ClosingEvent(code=1000, reason="Done", initiated_by="local")
        assert event.code == 1000
        assert event.reason == "Done"
        assert event.initiated_by == "local"

    def test_remote_close(self) -> None:
        """Test remotely initiated close."""
        event = ClosingEvent(code=1001, reason="Going away", initiated_by="remote")
        assert event.initiated_by == "remote"


class TestClosedEvent:
    """Tests for ClosedEvent dataclass."""

    def test_without_reconnect(self) -> None:
        """Test final close without reconnect."""
        event = ClosedEvent(code=1000, reason="Normal", reconnecting=False)
        assert event.reconnecting is False

    def test_with_reconnect(self) -> None:
        """Test close with pending reconnect."""
        event = ClosedEvent(code=1006, reason="", reconnecting=True)
        assert event.reconnecting is True


class TestEventEmitter:
    """Tests for EventEmitter class."""

    def test_init(self) -> None:
        """Test initialization."""
        emitter = EventEmitter()
        assert emitter.handler_count() == 0

    def test_decorator_registration(self) -> None:
        """Test registering handler with decorator."""
        emitter = EventEmitter()
        received: list[ConnectedEvent] = []

        @emitter.on("connected")
        def handler(event: ConnectedEvent) -> None:
            received.append(event)

        assert emitter.handler_count("connected") == 1

    def test_add_handler(self) -> None:
        """Test programmatic handler registration."""
        emitter = EventEmitter()
        received: list[ConnectedEvent] = []

        def handler(event: ConnectedEvent) -> None:
            received.append(event)

        emitter.add_handler("connected", handler)
        assert emitter.handler_count("connected") == 1

    def test_add_handler_no_duplicates(self) -> None:
        """Test that duplicate handlers are not added."""
        emitter = EventEmitter()

        def handler(event: ConnectedEvent) -> None:
            pass

        emitter.add_handler("connected", handler)
        emitter.add_handler("connected", handler)
        assert emitter.handler_count("connected") == 1

    def test_remove_handler(self) -> None:
        """Test removing handler."""
        emitter = EventEmitter()

        def handler(event: ConnectedEvent) -> None:
            pass

        emitter.add_handler("connected", handler)
        assert emitter.remove_handler("connected", handler) is True
        assert emitter.handler_count("connected") == 0

    def test_remove_handler_not_found(self) -> None:
        """Test removing non-existent handler."""
        emitter = EventEmitter()

        def handler(event: ConnectedEvent) -> None:
            pass

        assert emitter.remove_handler("connected", handler) is False

    def test_clear_handlers_specific(self) -> None:
        """Test clearing specific event handlers."""
        emitter = EventEmitter()

        @emitter.on("connected")
        def h1(event: ConnectedEvent) -> None:
            pass

        @emitter.on("disconnected")
        def h2(event: DisconnectedEvent) -> None:
            pass

        emitter.clear_handlers("connected")
        assert emitter.handler_count("connected") == 0
        assert emitter.handler_count("disconnected") == 1

    def test_clear_handlers_all(self) -> None:
        """Test clearing all handlers."""
        emitter = EventEmitter()

        @emitter.on("connected")
        def h1(event: ConnectedEvent) -> None:
            pass

        @emitter.on("disconnected")
        def h2(event: DisconnectedEvent) -> None:
            pass

        emitter.clear_handlers()
        assert emitter.handler_count() == 0


class TestEventEmitterAsync:
    """Async tests for EventEmitter."""

    @pytest.mark.asyncio
    async def test_emit_async_sync_handler(self) -> None:
        """Test emitting to sync handler."""
        emitter = EventEmitter()
        received: list[ConnectedEvent] = []

        @emitter.on("connected")
        def handler(event: ConnectedEvent) -> None:
            received.append(event)

        event = ConnectedEvent(uri="wss://example.com")
        await emitter.emit_async("connected", event)

        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_emit_async_async_handler(self) -> None:
        """Test emitting to async handler."""
        emitter = EventEmitter()
        received: list[ConnectedEvent] = []

        @emitter.on("connected")
        async def handler(event: ConnectedEvent) -> None:
            await asyncio.sleep(0)
            received.append(event)

        event = ConnectedEvent(uri="wss://example.com")
        await emitter.emit_async("connected", event)

        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_emit_async_multiple_handlers(self) -> None:
        """Test emitting to multiple handlers."""
        emitter = EventEmitter()
        received: list[int] = []

        @emitter.on("connected")
        def handler1(event: ConnectedEvent) -> None:
            received.append(1)

        @emitter.on("connected")
        async def handler2(event: ConnectedEvent) -> None:
            received.append(2)

        @emitter.on("connected")
        def handler3(event: ConnectedEvent) -> None:
            received.append(3)

        event = ConnectedEvent(uri="wss://example.com")
        await emitter.emit_async("connected", event)

        assert received == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_emit_async_no_handlers(self) -> None:
        """Test emitting with no handlers."""
        emitter = EventEmitter()
        event = ConnectedEvent(uri="wss://example.com")
        # Should not raise
        await emitter.emit_async("connected", event)

    @pytest.mark.asyncio
    async def test_emit_async_handler_exception(self) -> None:
        """Test that handler exceptions don't propagate."""
        emitter = EventEmitter()
        received: list[int] = []

        @emitter.on("connected")
        def handler1(event: ConnectedEvent) -> None:
            received.append(1)

        @emitter.on("connected")
        def handler2(event: ConnectedEvent) -> None:
            raise ValueError("Intentional error")

        @emitter.on("connected")
        def handler3(event: ConnectedEvent) -> None:
            received.append(3)

        event = ConnectedEvent(uri="wss://example.com")
        # Should not raise
        await emitter.emit_async("connected", event)

        # Handler 3 should still be called
        assert received == [1, 3]


class TestEventEmitterSync:
    """Sync emission tests for EventEmitter."""

    def test_emit_sync_sync_handler(self) -> None:
        """Test sync emission to sync handler."""
        emitter = EventEmitter()
        received: list[ConnectedEvent] = []

        @emitter.on("connected")
        def handler(event: ConnectedEvent) -> None:
            received.append(event)

        event = ConnectedEvent(uri="wss://example.com")
        emitter.emit_sync("connected", event)

        assert len(received) == 1
        assert received[0] is event

    def test_emit_sync_handler_exception(self) -> None:
        """Test that handler exceptions don't propagate."""
        emitter = EventEmitter()
        received: list[int] = []

        @emitter.on("connected")
        def handler1(event: ConnectedEvent) -> None:
            received.append(1)

        @emitter.on("connected")
        def handler2(event: ConnectedEvent) -> None:
            raise ValueError("Intentional error")

        @emitter.on("connected")
        def handler3(event: ConnectedEvent) -> None:
            received.append(3)

        event = ConnectedEvent(uri="wss://example.com")
        emitter.emit_sync("connected", event)

        assert received == [1, 3]

    def test_emit_sync_async_handler_no_loop(self) -> None:
        """Test sync emission with async handler when no loop is running."""
        emitter = EventEmitter()

        @emitter.on("connected")
        async def handler(event: ConnectedEvent) -> None:
            await asyncio.sleep(0)

        event = ConnectedEvent(uri="wss://example.com")
        # Should not raise (async handler is skipped)
        emitter.emit_sync("connected", event)


class TestEventEmitterThreadSafety:
    """Thread safety tests for EventEmitter."""

    def test_concurrent_add_handlers(self) -> None:
        """Test adding handlers from multiple threads."""
        import threading

        emitter = EventEmitter()
        handlers_added = []

        def add_handler(idx: int) -> None:
            def handler(event: ConnectedEvent) -> None:
                pass

            emitter.add_handler("connected", handler)
            handlers_added.append(idx)

        threads = [threading.Thread(target=add_handler, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(handlers_added) == 10
        assert emitter.handler_count("connected") == 10
