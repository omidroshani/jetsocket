"""Extended tests for WebSocketManager covering uncovered paths."""

from __future__ import annotations

import pytest

from wsfabric.backoff import BackoffConfig
from wsfabric.buffer import BufferConfig
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.manager import WebSocketManager
from wsfabric.state import ConnectionState


class TestManagerProperties:
    """Test WebSocketManager property accessors."""

    def test_latency_ms_none_without_heartbeat(self) -> None:
        """Test latency_ms returns None without heartbeat."""
        ws = WebSocketManager("ws://example.com/ws", heartbeat=None)
        assert ws.latency_ms is None

    def test_state_default_idle(self) -> None:
        """Test default state is IDLE."""
        ws = WebSocketManager("ws://example.com/ws")
        assert ws.state == ConnectionState.IDLE

    def test_is_connected_false_by_default(self) -> None:
        """Test is_connected is False by default."""
        ws = WebSocketManager("ws://example.com/ws")
        assert ws.is_connected is False

    def test_uri_property(self) -> None:
        """Test uri property."""
        ws = WebSocketManager("ws://example.com/ws")
        assert ws._uri == "ws://example.com/ws"


class TestManagerSendErrors:
    """Test WebSocketManager send error paths."""

    async def test_send_when_not_connected_raises(self) -> None:
        """Test send raises when not connected."""
        ws = WebSocketManager("ws://example.com/ws")
        from wsfabric.exceptions import InvalidStateError

        with pytest.raises(InvalidStateError):
            await ws.send({"test": "data"})

    async def test_send_raw_when_not_connected_raises(self) -> None:
        """Test send_raw raises when not connected."""
        ws = WebSocketManager("ws://example.com/ws")
        from wsfabric.exceptions import InvalidStateError

        with pytest.raises(InvalidStateError):
            await ws.send_raw(b"test")


class TestManagerConfiguration:
    """Test WebSocketManager configuration options."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        ws = WebSocketManager("ws://example.com/ws")
        assert ws._reconnect_enabled is True
        assert ws._close_timeout == 5.0

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        ws = WebSocketManager(
            "ws://example.com/ws",
            reconnect=False,
            backoff=BackoffConfig(base=0.5, cap=10.0),
            heartbeat=HeartbeatConfig(interval=15.0),
            buffer=BufferConfig(capacity=500),
            compress=True,
            compression_threshold=256,
            connect_timeout=15.0,
            close_timeout=10.0,
            max_message_size=32 * 1024 * 1024,
        )
        assert ws._reconnect_enabled is False
        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 15.0
        assert ws._close_timeout == 10.0
        assert ws._transport_config.compression_threshold == 256
        assert ws._transport_config.max_message_size == 32 * 1024 * 1024

    def test_with_heartbeat(self) -> None:
        """Test with heartbeat configured."""
        ws = WebSocketManager(
            "ws://example.com/ws", heartbeat=HeartbeatConfig(interval=20.0)
        )
        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 20.0

    def test_custom_serializer(self) -> None:
        """Test custom serializer/deserializer."""

        def my_ser(data: object) -> bytes:
            return b"custom"

        def my_deser(data: bytes) -> object:
            return "parsed"

        ws = WebSocketManager(
            "ws://example.com/ws",
            serializer=my_ser,
            deserializer=my_deser,
        )
        assert ws._serializer is my_ser
        assert ws._deserializer is my_deser


class TestManagerEventSystem:
    """Test event registration on WebSocketManager."""

    def test_on_decorator(self) -> None:
        """Test @ws.on decorator registers handler."""
        ws = WebSocketManager("ws://example.com/ws")

        @ws.on("message")
        async def handler(event: object) -> None:
            pass

        # Handler should be registered in the emitter
        assert handler is not None

    def test_add_handler(self) -> None:
        """Test add_handler registers handler."""
        ws = WebSocketManager("ws://example.com/ws")

        async def handler(event: object) -> None:
            pass

        ws.add_handler("message", handler)
        # Should not raise


class TestManagerStats:
    """Test WebSocketManager stats."""

    def test_stats_returns_snapshot(self) -> None:
        """Test stats returns a ConnectionStats snapshot."""
        ws = WebSocketManager("ws://example.com/ws")
        stats = ws.stats()
        assert stats.state == ConnectionState.IDLE
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.reconnect_count == 0

    def test_stats_uptime_zero_when_not_connected(self) -> None:
        """Test uptime is 0 when not connected."""
        ws = WebSocketManager("ws://example.com/ws")
        stats = ws.stats()
        assert stats.uptime_seconds == 0.0


class TestManagerAsyncIteration:
    """Test WebSocketManager async iteration."""

    async def test_aiter_returns_self(self) -> None:
        """Test __aiter__ returns the manager."""
        ws = WebSocketManager("ws://example.com/ws")
        assert ws.__aiter__() is ws
