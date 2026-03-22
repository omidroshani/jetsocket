"""Multiplexed WebSocket connections for WSFabric.

This module provides multiplexing support for managing multiple logical
subscriptions over a single WebSocket connection.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

from wsfabric.exceptions import InvalidStateError, TimeoutError
from wsfabric.manager import WebSocket
from wsfabric.state import ConnectionState
from wsfabric.stats import ConnectionStats

if TYPE_CHECKING:
    from types import TracebackType

# Type variable for message type
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class MultiplexConfig:
    """Configuration for multiplexed connections.

    Args:
        channel_extractor: Function to extract channel name from message.
            Required for routing messages to correct subscription.
        subscribe_message: Function to generate subscribe message for a channel.
        unsubscribe_message: Function to generate unsubscribe message for a channel.
        queue_size: Max messages per subscription queue (0 = unbounded).
    """

    channel_extractor: Callable[[Any], str | None]
    subscribe_message: Callable[[str], Any] | None = None
    unsubscribe_message: Callable[[str], Any] | None = None
    queue_size: int = 1000

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.queue_size < 0:
            msg = f"queue_size must be non-negative, got {self.queue_size}"
            raise ValueError(msg)


@dataclass
class SubscriptionStats:
    """Statistics for a single subscription.

    Args:
        channel: The channel name.
        messages_received: Number of messages received.
        queue_size: Current queue size.
        is_active: Whether the subscription is active.
    """

    channel: str
    messages_received: int = 0
    queue_size: int = 0
    is_active: bool = True


@dataclass
class MultiplexStats:
    """Aggregated statistics for multiplexed connection.

    Args:
        total_subscriptions: Total number of subscriptions created.
        active_subscriptions: Number of currently active subscriptions.
        total_messages_routed: Total messages successfully routed.
        unroutable_messages: Messages that couldn't be routed.
        connection_stats: Underlying connection statistics.
    """

    total_subscriptions: int
    active_subscriptions: int
    total_messages_routed: int
    unroutable_messages: int
    connection_stats: ConnectionStats


@dataclass
class _MutableMultiplexStats:
    """Mutable statistics for internal tracking."""

    total_subscriptions: int = 0
    total_messages_routed: int = 0
    unroutable_messages: int = 0


class Subscription(Generic[T]):
    """A logical subscription within a multiplexed connection.

    Represents a single channel subscription that receives routed messages.
    Implements async iteration for convenient message consumption.

    Example:
        >>> async for msg in subscription:
        ...     print(f"Trade: {msg['price']}")
    """

    def __init__(
        self,
        channel: str,
        queue: asyncio.Queue[T | None],
        mux: Multiplex[T],
    ) -> None:
        """Initialize a subscription.

        Args:
            channel: The channel name.
            queue: The message queue for this subscription.
            mux: The parent Multiplex.
        """
        self._channel = channel
        self._queue = queue
        self._mux = mux
        self._active = True
        self._messages_received = 0

    @property
    def channel(self) -> str:
        """Get the channel name."""
        return self._channel

    @property
    def is_active(self) -> bool:
        """Check if subscription is still active."""
        return self._active

    async def recv(self, timeout: float | None = None) -> T:
        """Receive the next message for this subscription.

        Args:
            timeout: Maximum wait time in seconds. None = wait forever.

        Returns:
            The next message.

        Raises:
            TimeoutError: If timeout exceeded.
            InvalidStateError: If subscription is closed.
        """
        if not self._active:
            raise InvalidStateError(
                "Subscription is closed",
                current_state="closed",
                required_states=["active"],
            )

        try:
            if timeout is not None:
                msg = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                msg = await self._queue.get()

            if msg is None:
                self._active = False
                raise InvalidStateError(
                    "Subscription is closed",
                    current_state="closed",
                    required_states=["active"],
                )

            return msg

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"No message received within {timeout} seconds",
                timeout=timeout or 0.0,
                operation="recv",
            ) from None

    async def close(self) -> None:
        """Unsubscribe and close this subscription."""
        if not self._active:
            return
        self._active = False
        await self._mux.unsubscribe(self._channel)

    def stats(self) -> SubscriptionStats:
        """Get subscription statistics."""
        return SubscriptionStats(
            channel=self._channel,
            messages_received=self._messages_received,
            queue_size=self._queue.qsize(),
            is_active=self._active,
        )

    def __aiter__(self) -> AsyncIterator[T]:
        """Async iteration over messages."""
        return self

    async def __anext__(self) -> T:
        """Get next message.

        Raises:
            StopAsyncIteration: When subscription is closed.
        """
        if not self._active:
            raise StopAsyncIteration

        try:
            msg = await self._queue.get()
            if msg is None:
                self._active = False
                raise StopAsyncIteration
            return msg
        except asyncio.CancelledError:
            raise StopAsyncIteration from None


class Multiplex(Generic[T]):
    """Manages multiple logical subscriptions over a single WebSocket.

    Routes incoming messages to the appropriate subscription queue based
    on channel extraction. Handles subscribe/unsubscribe without reconnect.

    Example:
        >>> config = MultiplexConfig(
        ...     channel_extractor=lambda msg: msg.get("stream"),
        ...     subscribe_message=lambda ch: {"method": "SUBSCRIBE", "params": [ch]},
        ...     unsubscribe_message=lambda ch: {
        ...         "method": "UNSUBSCRIBE",
        ...         "params": [ch],
        ...     },
        ... )
        >>> async with Multiplex(
        ...     "wss://stream.binance.com/ws", config
        ... ) as mux:
        ...     btc = await mux.subscribe("btcusdt@trade")
        ...     eth = await mux.subscribe("ethusdt@trade")
        ...     async for msg in btc:
        ...         print(f"BTC: {msg}")
    """

    def __init__(
        self,
        uri: str,
        config: MultiplexConfig | None = None,
        *,
        # Flattened config kwargs (alternative to config=)
        channel_key: str | None = None,
        channel_extractor: Callable[[Any], str | None] | None = None,
        subscribe_msg: Callable[[str], Any] | None = None,
        unsubscribe_msg: Callable[[str], Any] | None = None,
        queue_size: int = 1000,
        # Backward compat
        manager_kwargs: dict[str, Any] | None = None,
        # WebSocket kwargs (forwarded to internal WebSocket)
        **ws_kwargs: Any,
    ) -> None:
        """Initialize multiplexed connection.

        Args:
            uri: WebSocket URI.
            config: Multiplex configuration (legacy, use kwargs instead).
            channel_key: Dict key to extract channel name (e.g. "stream").
            channel_extractor: Function to extract channel from message.
            subscribe_msg: Function to build subscribe message for a channel.
            unsubscribe_msg: Function to build unsubscribe message.
            queue_size: Max messages per subscription queue.
            manager_kwargs: Legacy kwargs passed to WebSocket.
            **ws_kwargs: Additional kwargs passed to internal WebSocket
                (heartbeat, reconnect, buffer, etc.)
        """
        self._uri = uri

        # Build config from kwargs or use provided config
        if config is not None:
            self._config = config
        elif channel_extractor is not None:
            self._config = MultiplexConfig(
                channel_extractor=channel_extractor,
                subscribe_message=subscribe_msg,
                unsubscribe_message=unsubscribe_msg,
                queue_size=queue_size,
            )
        elif channel_key is not None:
            self._config = MultiplexConfig(
                channel_extractor=lambda msg, _k=channel_key: msg.get(_k)
                if isinstance(msg, dict)
                else None,
                subscribe_message=subscribe_msg,
                unsubscribe_message=unsubscribe_msg,
                queue_size=queue_size,
            )
        else:
            msg = "Either 'config', 'channel_key', or 'channel_extractor' is required"
            raise ValueError(msg)

        self._manager_kwargs = {**(manager_kwargs or {}), **ws_kwargs}

        # Will be created on connect
        self._manager: WebSocket[T] | None = None

        # Subscriptions by channel name
        self._subscriptions: dict[str, Subscription[T]] = {}

        # Statistics
        self._stats = _MutableMultiplexStats()

        # Router task
        self._router_task: asyncio.Task[None] | None = None

        # Control
        self._closed = False

    @property
    def uri(self) -> str:
        """Get the WebSocket URI."""
        return self._uri

    @property
    def is_connected(self) -> bool:
        """Check if underlying connection is established."""
        if self._manager is None:
            return False
        return self._manager.is_connected

    @property
    def state(self) -> ConnectionState:
        """Get the connection state."""
        if self._manager is None:
            return ConnectionState.IDLE
        return self._manager.state

    async def connect(self) -> None:
        """Connect to the WebSocket server.

        Raises:
            InvalidStateError: If already connected.
            ConnectionError: If connection fails.
        """
        if self._closed:
            raise InvalidStateError(
                "Connection has been closed",
                current_state="closed",
                required_states=["idle"],
            )

        if self._manager is not None:
            raise InvalidStateError(
                "Already connected",
                current_state="connected",
                required_states=["idle"],
            )

        # Create manager
        self._manager = WebSocket(self._uri, **self._manager_kwargs)

        # Connect
        await self._manager.connect()

        # Start message router
        self._router_task = asyncio.create_task(
            self._message_router(), name="wsfabric-multiplex-router"
        )

    async def close(self) -> None:
        """Close all subscriptions and the connection."""
        if self._closed:
            return
        self._closed = True

        # Signal all subscriptions to close
        for subscription in self._subscriptions.values():
            subscription._active = False
            with contextlib.suppress(asyncio.QueueFull):
                subscription._queue.put_nowait(None)

        # Stop router
        if self._router_task is not None:
            self._router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._router_task
            self._router_task = None

        # Close manager
        if self._manager is not None:
            await self._manager.close()
            self._manager = None

        self._subscriptions.clear()

    async def subscribe(
        self,
        channel: str,
        *,
        timeout: float | None = None,
    ) -> Subscription[T]:
        """Subscribe to a channel.

        Args:
            channel: Channel identifier (e.g., "btcusdt@trade").
            timeout: Timeout for subscribe message (not currently used).

        Returns:
            A Subscription object for receiving messages.

        Raises:
            InvalidStateError: If not connected.
        """
        if self._manager is None or not self.is_connected:
            raise InvalidStateError(
                "Not connected",
                current_state="disconnected",
                required_states=["connected"],
            )

        # Return existing subscription if already subscribed
        if channel in self._subscriptions:
            return self._subscriptions[channel]

        # Create subscription queue
        maxsize = self._config.queue_size if self._config.queue_size > 0 else 0
        queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=maxsize)

        # Create subscription
        subscription = Subscription(channel, queue, self)
        self._subscriptions[channel] = subscription
        self._stats.total_subscriptions += 1

        # Send subscribe message if configured
        if self._config.subscribe_message is not None:
            msg = self._config.subscribe_message(channel)
            await self._manager.send(msg)

        return subscription

    async def unsubscribe(self, channel: str) -> bool:
        """Unsubscribe from a channel.

        Args:
            channel: Channel to unsubscribe from.

        Returns:
            True if channel was subscribed, False otherwise.
        """
        subscription = self._subscriptions.pop(channel, None)
        if subscription is None:
            return False

        # Mark as inactive
        subscription._active = False

        # Signal queue closure
        with contextlib.suppress(asyncio.QueueFull):
            subscription._queue.put_nowait(None)

        # Send unsubscribe message if configured
        if (
            self._manager is not None
            and self.is_connected
            and self._config.unsubscribe_message is not None
        ):
            msg = self._config.unsubscribe_message(channel)
            with contextlib.suppress(Exception):
                await self._manager.send(msg)

        return True

    def get_subscription(self, channel: str) -> Subscription[T] | None:
        """Get an existing subscription by channel name.

        Args:
            channel: The channel name.

        Returns:
            The Subscription or None if not found.
        """
        return self._subscriptions.get(channel)

    def list_subscriptions(self) -> list[str]:
        """List all active channel subscriptions.

        Returns:
            List of channel names.
        """
        return [ch for ch, sub in self._subscriptions.items() if sub.is_active]

    def stats(self) -> MultiplexStats:
        """Get aggregated statistics.

        Returns:
            MultiplexStats instance.
        """
        active = sum(1 for sub in self._subscriptions.values() if sub.is_active)
        conn_stats = (
            self._manager.stats()
            if self._manager is not None
            else ConnectionStats(
                state=ConnectionState.IDLE,
                uptime_seconds=0.0,
                messages_sent=0,
                messages_received=0,
                bytes_sent=0,
                bytes_received=0,
                reconnect_count=0,
                last_reconnect_at=None,
                latency_ms=None,
                latency_avg_ms=None,
                last_message_at=None,
                connection_age_seconds=0.0,
                errors=0,
            )
        )

        return MultiplexStats(
            total_subscriptions=self._stats.total_subscriptions,
            active_subscriptions=active,
            total_messages_routed=self._stats.total_messages_routed,
            unroutable_messages=self._stats.unroutable_messages,
            connection_stats=conn_stats,
        )

    async def _message_router(self) -> None:
        """Route incoming messages to subscription queues.

        This runs as a background task, consuming messages from the
        WebSocket and routing them to the correct subscription
        queue based on channel_extractor.
        """
        if self._manager is None:
            return

        try:
            async for message in self._manager:
                # Extract channel from message
                channel = self._config.channel_extractor(message)

                if channel is None:
                    self._stats.unroutable_messages += 1
                    continue

                # Find subscription
                subscription = self._subscriptions.get(channel)
                if subscription is None or not subscription.is_active:
                    self._stats.unroutable_messages += 1
                    continue

                # Route message to subscription queue
                try:
                    subscription._queue.put_nowait(message)
                    subscription._messages_received += 1
                    self._stats.total_messages_routed += 1
                except asyncio.QueueFull:
                    # Drop oldest if queue is full
                    with contextlib.suppress(asyncio.QueueEmpty):
                        _ = subscription._queue.get_nowait()
                    subscription._queue.put_nowait(message)
                    subscription._messages_received += 1
                    self._stats.total_messages_routed += 1

        except asyncio.CancelledError:
            pass

    async def __aenter__(self) -> Multiplex[T]:
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        await self.close()

    def __repr__(self) -> str:
        """Return string representation."""
        active = sum(1 for sub in self._subscriptions.values() if sub.is_active)
        return (
            f"Multiplex(uri={self._uri!r}, "
            f"state={self.state.value}, subscriptions={active})"
        )


# Backward compatibility alias
MultiplexConnection = Multiplex
