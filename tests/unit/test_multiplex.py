"""Tests for MultiplexConnection."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wsfabric.exceptions import InvalidStateError, TimeoutError
from wsfabric.multiplex import (
    MultiplexConfig,
    MultiplexConnection,
    MultiplexStats,
    Subscription,
    SubscriptionStats,
    _MutableMultiplexStats,
)
from wsfabric.state import ConnectionState


class TestMultiplexConfig:
    """Tests for MultiplexConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))

        assert config.channel_extractor is not None
        assert config.subscribe_message is None
        assert config.unsubscribe_message is None
        assert config.queue_size == 1000

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("topic"),
            subscribe_message=lambda ch: {"op": "subscribe", "args": [ch]},
            unsubscribe_message=lambda ch: {"op": "unsubscribe", "args": [ch]},
            queue_size=500,
        )

        assert config.queue_size == 500
        assert config.subscribe_message is not None
        assert config.unsubscribe_message is not None

    def test_invalid_queue_size(self) -> None:
        """Test that negative queue_size raises."""
        with pytest.raises(ValueError, match="queue_size must be non-negative"):
            MultiplexConfig(
                channel_extractor=lambda msg: msg.get("stream"),
                queue_size=-1,
            )

    def test_zero_queue_size_valid(self) -> None:
        """Test that zero queue_size is valid (unbounded)."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("stream"),
            queue_size=0,
        )
        assert config.queue_size == 0

    def test_channel_extractor(self) -> None:
        """Test channel extractor function."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))

        assert config.channel_extractor({"stream": "btcusdt@trade"}) == "btcusdt@trade"
        assert config.channel_extractor({"other": "value"}) is None

    def test_subscribe_message(self) -> None:
        """Test subscribe message generator."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("stream"),
            subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        )

        msg = config.subscribe_message("btcusdt@trade")
        assert msg == {"method": "SUBSCRIBE", "params": ["btcusdt@trade"]}


class TestSubscriptionStats:
    """Tests for SubscriptionStats."""

    def test_subscription_stats_creation(self) -> None:
        """Test SubscriptionStats creation."""
        stats = SubscriptionStats(
            channel="btcusdt@trade",
            messages_received=100,
            queue_size=5,
            is_active=True,
        )

        assert stats.channel == "btcusdt@trade"
        assert stats.messages_received == 100
        assert stats.queue_size == 5
        assert stats.is_active is True

    def test_subscription_stats_defaults(self) -> None:
        """Test SubscriptionStats default values."""
        stats = SubscriptionStats(channel="test")

        assert stats.messages_received == 0
        assert stats.queue_size == 0
        assert stats.is_active is True


class TestMultiplexStats:
    """Tests for MultiplexStats."""

    def test_multiplex_stats_creation(self) -> None:
        """Test MultiplexStats creation."""
        from wsfabric.stats import ConnectionStats

        conn_stats = ConnectionStats(
            state=ConnectionState.CONNECTED,
            uptime_seconds=100.0,
            messages_sent=50,
            messages_received=100,
            bytes_sent=1000,
            bytes_received=2000,
            reconnect_count=1,
            last_reconnect_at=None,
            latency_ms=10.0,
            latency_avg_ms=12.0,
            last_message_at=None,
            connection_age_seconds=100.0,
            errors=0,
        )

        stats = MultiplexStats(
            total_subscriptions=5,
            active_subscriptions=3,
            total_messages_routed=100,
            unroutable_messages=2,
            connection_stats=conn_stats,
        )

        assert stats.total_subscriptions == 5
        assert stats.active_subscriptions == 3
        assert stats.total_messages_routed == 100
        assert stats.unroutable_messages == 2
        assert stats.connection_stats.state == ConnectionState.CONNECTED


class TestMutableMultiplexStats:
    """Tests for _MutableMultiplexStats."""

    def test_mutable_stats_defaults(self) -> None:
        """Test default values."""
        stats = _MutableMultiplexStats()

        assert stats.total_subscriptions == 0
        assert stats.total_messages_routed == 0
        assert stats.unroutable_messages == 0

    def test_mutable_stats_increment(self) -> None:
        """Test incrementing values."""
        stats = _MutableMultiplexStats()

        stats.total_subscriptions += 1
        stats.total_messages_routed += 10
        stats.unroutable_messages += 2

        assert stats.total_subscriptions == 1
        assert stats.total_messages_routed == 10
        assert stats.unroutable_messages == 2


class TestSubscription:
    """Tests for Subscription."""

    def test_subscription_properties(self) -> None:
        """Test subscription properties."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        assert sub.channel == "btcusdt@trade"
        assert sub.is_active is True

    def test_subscription_stats(self) -> None:
        """Test subscription stats method."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)
        sub._messages_received = 50

        stats = sub.stats()

        assert stats.channel == "btcusdt@trade"
        assert stats.messages_received == 50
        assert stats.queue_size == 0
        assert stats.is_active is True

    @pytest.mark.asyncio
    async def test_subscription_recv(self) -> None:
        """Test receiving a message."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        # Put message in queue
        await queue.put({"price": "50000"})

        msg = await sub.recv()

        assert msg == {"price": "50000"}

    @pytest.mark.asyncio
    async def test_subscription_recv_timeout(self) -> None:
        """Test receiving with timeout."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        with pytest.raises(TimeoutError) as exc_info:
            await sub.recv(timeout=0.01)

        assert exc_info.value.operation == "recv"

    @pytest.mark.asyncio
    async def test_subscription_recv_when_closed(self) -> None:
        """Test receiving when subscription is closed."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)
        sub._active = False

        with pytest.raises(InvalidStateError) as exc_info:
            await sub.recv()

        assert exc_info.value.current_state == "closed"

    @pytest.mark.asyncio
    async def test_subscription_recv_none_closes(self) -> None:
        """Test that receiving None closes subscription."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)
        await queue.put(None)

        with pytest.raises(InvalidStateError):
            await sub.recv()

        assert sub.is_active is False

    @pytest.mark.asyncio
    async def test_subscription_close(self) -> None:
        """Test closing subscription."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = AsyncMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        await sub.close()

        assert sub.is_active is False
        mux.unsubscribe.assert_called_once_with("btcusdt@trade")

    @pytest.mark.asyncio
    async def test_subscription_close_idempotent(self) -> None:
        """Test closing subscription is idempotent."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = AsyncMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        await sub.close()
        await sub.close()

        # Should only call unsubscribe once
        mux.unsubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscription_iteration(self) -> None:
        """Test async iteration over subscription."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)

        # Put messages
        await queue.put({"price": "50000"})
        await queue.put({"price": "51000"})
        await queue.put(None)  # Close signal

        messages = []
        async for msg in sub:
            messages.append(msg)

        assert len(messages) == 2
        assert messages[0] == {"price": "50000"}
        assert messages[1] == {"price": "51000"}
        assert sub.is_active is False

    @pytest.mark.asyncio
    async def test_subscription_iteration_when_closed(self) -> None:
        """Test iteration stops when closed."""
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        mux = MagicMock()

        sub = Subscription("btcusdt@trade", queue, mux)
        sub._active = False

        messages = []
        async for msg in sub:
            messages.append(msg)

        assert len(messages) == 0


class TestMultiplexConnectionInit:
    """Tests for MultiplexConnection initialization."""

    def test_basic_init(self) -> None:
        """Test basic initialization."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        assert mux.uri == "wss://example.com/ws"
        assert mux.is_connected is False
        assert mux.state == ConnectionState.IDLE

    def test_init_with_manager_kwargs(self) -> None:
        """Test initialization with manager kwargs."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection(
            "wss://example.com/ws",
            config,
            manager_kwargs={"reconnect": False, "connect_timeout": 5.0},
        )

        assert mux._manager_kwargs == {"reconnect": False, "connect_timeout": 5.0}

    def test_repr(self) -> None:
        """Test string representation."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        repr_str = repr(mux)

        assert "MultiplexConnection" in repr_str
        assert "wss://example.com/ws" in repr_str
        assert "idle" in repr_str


class TestMultiplexConnectionLifecycle:
    """Tests for MultiplexConnection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect(self) -> None:
        """Test connecting."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

        assert mux._manager is not None
        mock_manager.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self) -> None:
        """Test connecting when already connected raises."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            with pytest.raises(InvalidStateError) as exc_info:
                await mux.connect()

            assert exc_info.value.current_state == "connected"

    @pytest.mark.asyncio
    async def test_connect_after_close(self) -> None:
        """Test connecting after close raises."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        await mux.close()

        with pytest.raises(InvalidStateError) as exc_info:
            await mux.connect()

        assert exc_info.value.current_state == "closed"

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test closing when not connected."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        # Should not raise
        await mux.close()

        assert mux._closed is True

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        """Test closing is idempotent."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        await mux.close()
        await mux.close()

        assert mux._closed is True

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test context manager."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            async with MultiplexConnection("wss://example.com/ws", config) as mux:
                assert mux._manager is not None

        mock_manager.close.assert_called_once()


class TestMultiplexConnectionSubscriptions:
    """Tests for subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe(self) -> None:
        """Test subscribing to a channel."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("stream"),
            subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        )
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub = await mux.subscribe("btcusdt@trade")

            assert sub.channel == "btcusdt@trade"
            assert sub.is_active is True
            mock_manager.send.assert_called_once_with(
                {"method": "SUBSCRIBE", "params": ["btcusdt@trade"]}
            )

    @pytest.mark.asyncio
    async def test_subscribe_without_message(self) -> None:
        """Test subscribing without subscribe message configured."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub = await mux.subscribe("btcusdt@trade")

            assert sub.channel == "btcusdt@trade"
            mock_manager.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_duplicate_returns_existing(self) -> None:
        """Test subscribing to same channel returns existing subscription."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub1 = await mux.subscribe("btcusdt@trade")
            sub2 = await mux.subscribe("btcusdt@trade")

            assert sub1 is sub2

    @pytest.mark.asyncio
    async def test_subscribe_not_connected(self) -> None:
        """Test subscribing when not connected raises."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        with pytest.raises(InvalidStateError) as exc_info:
            await mux.subscribe("btcusdt@trade")

        assert exc_info.value.current_state == "disconnected"

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        """Test unsubscribing from a channel."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("stream"),
            unsubscribe_message=lambda ch: {"method": "UNSUBSCRIBE", "params": [ch]},
        )
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub = await mux.subscribe("btcusdt@trade")
            result = await mux.unsubscribe("btcusdt@trade")

            assert result is True
            assert sub.is_active is False
            mock_manager.send.assert_called_with(
                {"method": "UNSUBSCRIBE", "params": ["btcusdt@trade"]}
            )

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self) -> None:
        """Test unsubscribing from unsubscribed channel."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            result = await mux.unsubscribe("btcusdt@trade")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_subscription(self) -> None:
        """Test getting subscription by channel."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub = await mux.subscribe("btcusdt@trade")
            found = mux.get_subscription("btcusdt@trade")

            assert found is sub

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(self) -> None:
        """Test getting non-existent subscription."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        assert mux.get_subscription("btcusdt@trade") is None

    @pytest.mark.asyncio
    async def test_list_subscriptions(self) -> None:
        """Test listing subscriptions."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            await mux.subscribe("btcusdt@trade")
            await mux.subscribe("ethusdt@trade")

            channels = mux.list_subscriptions()

            assert "btcusdt@trade" in channels
            assert "ethusdt@trade" in channels

    @pytest.mark.asyncio
    async def test_list_subscriptions_excludes_inactive(self) -> None:
        """Test listing subscriptions excludes inactive."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            await mux.subscribe("btcusdt@trade")
            sub = await mux.subscribe("ethusdt@trade")
            sub._active = False

            channels = mux.list_subscriptions()

            assert "btcusdt@trade" in channels
            assert "ethusdt@trade" not in channels


class TestMultiplexConnectionStats:
    """Tests for stats."""

    @pytest.mark.asyncio
    async def test_stats_not_connected(self) -> None:
        """Test stats when not connected."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        stats = mux.stats()

        assert stats.total_subscriptions == 0
        assert stats.active_subscriptions == 0
        assert stats.total_messages_routed == 0
        assert stats.unroutable_messages == 0
        assert stats.connection_stats.state == ConnectionState.IDLE

    @pytest.mark.asyncio
    async def test_stats_with_subscriptions(self) -> None:
        """Test stats with subscriptions."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        from wsfabric.stats import ConnectionStats

        mock_stats = ConnectionStats(
            state=ConnectionState.CONNECTED,
            uptime_seconds=100.0,
            messages_sent=10,
            messages_received=20,
            bytes_sent=1000,
            bytes_received=2000,
            reconnect_count=0,
            last_reconnect_at=None,
            latency_ms=5.0,
            latency_avg_ms=6.0,
            last_message_at=None,
            connection_age_seconds=100.0,
            errors=0,
        )
        mock_manager.stats = MagicMock(return_value=mock_stats)

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            await mux.subscribe("btcusdt@trade")
            await mux.subscribe("ethusdt@trade")

            stats = mux.stats()

            assert stats.total_subscriptions == 2
            assert stats.active_subscriptions == 2
            assert stats.connection_stats.state == ConnectionState.CONNECTED


class TestMultiplexConnectionRouting:
    """Tests for message routing."""

    @pytest.mark.asyncio
    async def test_message_routing(self) -> None:
        """Test message routing to subscriptions."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        # Create a mock manager with async iterator
        messages = [
            {"stream": "btcusdt@trade", "data": {"price": "50000"}},
            {"stream": "ethusdt@trade", "data": {"price": "3000"}},
        ]

        async def mock_iter() -> Any:
            for msg in messages:
                yield msg

        mock_manager = MagicMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.connect = AsyncMock()
        mock_manager.close = AsyncMock()
        mock_manager.send = AsyncMock()
        mock_manager.__aiter__ = lambda self: mock_iter()

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            btc_sub = await mux.subscribe("btcusdt@trade")
            eth_sub = await mux.subscribe("ethusdt@trade")

            # Let router process messages
            await asyncio.sleep(0.05)

            # Check messages were routed
            stats = mux.stats()
            assert stats.total_messages_routed == 2

            # Check queues have messages
            btc_msg = btc_sub._queue.get_nowait()
            assert btc_msg["stream"] == "btcusdt@trade"

            eth_msg = eth_sub._queue.get_nowait()
            assert eth_msg["stream"] == "ethusdt@trade"

            await mux.close()

    @pytest.mark.asyncio
    async def test_unroutable_messages(self) -> None:
        """Test unroutable messages are counted."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        # Message with no channel
        messages = [
            {"other": "data"},
            {"stream": "unknown@trade", "data": {}},
        ]

        async def mock_iter() -> Any:
            for msg in messages:
                yield msg

        mock_manager = MagicMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.connect = AsyncMock()
        mock_manager.close = AsyncMock()
        mock_manager.send = AsyncMock()
        mock_manager.__aiter__ = lambda self: mock_iter()

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            # Subscribe to btcusdt only
            await mux.subscribe("btcusdt@trade")

            # Let router process messages
            await asyncio.sleep(0.05)

            stats = mux.stats()
            # First message has no "stream" key, second has unsubscribed channel
            assert stats.unroutable_messages == 2
            assert stats.total_messages_routed == 0

            await mux.close()

    @pytest.mark.asyncio
    async def test_queue_full_drops_oldest(self) -> None:
        """Test that full queue drops oldest message."""
        config = MultiplexConfig(
            channel_extractor=lambda msg: msg.get("stream"),
            queue_size=2,
        )
        mux = MultiplexConnection("wss://example.com/ws", config)

        messages = [
            {"stream": "btcusdt@trade", "seq": 1},
            {"stream": "btcusdt@trade", "seq": 2},
            {"stream": "btcusdt@trade", "seq": 3},
        ]

        async def mock_iter() -> Any:
            for msg in messages:
                yield msg

        mock_manager = MagicMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED
        mock_manager.connect = AsyncMock()
        mock_manager.close = AsyncMock()
        mock_manager.send = AsyncMock()
        mock_manager.__aiter__ = lambda self: mock_iter()

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            sub = await mux.subscribe("btcusdt@trade")

            # Let router process messages
            await asyncio.sleep(0.05)

            # Queue should have last 2 messages (oldest dropped)
            stats = mux.stats()
            assert stats.total_messages_routed == 3

            msg1 = sub._queue.get_nowait()
            msg2 = sub._queue.get_nowait()

            # Oldest message (seq=1) should have been dropped
            assert msg1["seq"] == 2
            assert msg2["seq"] == 3

            await mux.close()

    @pytest.mark.asyncio
    async def test_close_signals_subscriptions(self) -> None:
        """Test that close signals all subscriptions."""
        config = MultiplexConfig(channel_extractor=lambda msg: msg.get("stream"))
        mux = MultiplexConnection("wss://example.com/ws", config)

        mock_manager = AsyncMock()
        mock_manager.is_connected = True
        mock_manager.state = ConnectionState.CONNECTED

        with patch("wsfabric.multiplex.WebSocketManager", return_value=mock_manager):
            await mux.connect()

            btc_sub = await mux.subscribe("btcusdt@trade")
            eth_sub = await mux.subscribe("ethusdt@trade")

            await mux.close()

            assert btc_sub.is_active is False
            assert eth_sub.is_active is False
