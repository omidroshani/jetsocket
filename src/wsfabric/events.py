"""Event system for WSFabric.

This module provides a decorator-based event system for handling WebSocket
lifecycle events. Events are emitted at key points during connection management.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    TypeVar,
)

if TYPE_CHECKING:
    from wsfabric.state import ConnectionState

# Event type literal for type safety
EventType = Literal[
    "connecting",
    "connected",
    "disconnected",
    "reconnecting",
    "reconnected",
    "message",
    "raw_message",
    "error",
    "state_change",
    "ping",
    "pong",
    "closing",
    "closed",
]

# Type variable for generic message data
T = TypeVar("T")

# Handler type - can be sync or async
Handler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ConnectingEvent:
    """Emitted when a connection attempt begins.

    Args:
        uri: The WebSocket URI being connected to.
        attempt: The attempt number (1-based).
    """

    uri: str
    attempt: int


@dataclass(frozen=True, slots=True)
class ConnectedEvent:
    """Emitted when connection is successfully established.

    Args:
        uri: The connected WebSocket URI.
        subprotocol: Negotiated subprotocol (if any).
        extensions: Negotiated extensions list.
    """

    uri: str
    subprotocol: str | None = None
    extensions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DisconnectedEvent:
    """Emitted when connection is lost or closed by remote.

    Args:
        code: WebSocket close code.
        reason: Close reason string.
        was_clean: True if close handshake completed properly.
    """

    code: int
    reason: str
    was_clean: bool


@dataclass(frozen=True, slots=True)
class ReconnectingEvent:
    """Emitted before each reconnection attempt.

    Args:
        attempt: The reconnect attempt number (1-based).
        delay: Delay in seconds before this attempt.
        last_error: The error that triggered reconnection.
    """

    attempt: int
    delay: float
    last_error: Exception | None = None


@dataclass(frozen=True, slots=True)
class ReconnectedEvent:
    """Emitted after successful reconnection.

    Args:
        uri: The reconnected WebSocket URI.
        attempt: The successful attempt number.
        downtime_seconds: Time spent disconnected.
    """

    uri: str
    attempt: int
    downtime_seconds: float


@dataclass(frozen=True, slots=True)
class MessageEvent(Generic[T]):
    """Emitted when a deserialized message is received.

    Args:
        data: The deserialized message data.
        raw: The raw bytes before deserialization.
    """

    data: T
    raw: bytes


@dataclass(frozen=True, slots=True)
class RawMessageEvent:
    """Emitted for every raw message frame received.

    Args:
        data: Raw message bytes.
        opcode: The WebSocket opcode (text=1, binary=2).
    """

    data: bytes
    opcode: int


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Emitted when an error occurs.

    Args:
        error: The exception that occurred.
        fatal: True if error will cause disconnect/failure.
    """

    error: Exception
    fatal: bool


@dataclass(frozen=True, slots=True)
class StateChangeEvent:
    """Emitted on every state transition.

    Args:
        old_state: The previous connection state.
        new_state: The new connection state.
    """

    old_state: ConnectionState
    new_state: ConnectionState


@dataclass(frozen=True, slots=True)
class PingEvent:
    """Emitted when a ping frame is sent.

    Args:
        payload: The ping payload bytes.
    """

    payload: bytes


@dataclass(frozen=True, slots=True)
class PongEvent:
    """Emitted when a pong frame is received.

    Args:
        payload: The pong payload bytes.
        latency_ms: Round-trip latency in milliseconds.
    """

    payload: bytes
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class ClosingEvent:
    """Emitted when close handshake is initiated.

    Args:
        code: The close code being sent.
        reason: The close reason being sent.
        initiated_by: Who initiated the close ('local' or 'remote').
    """

    code: int
    reason: str
    initiated_by: Literal["local", "remote"]


@dataclass(frozen=True, slots=True)
class ClosedEvent:
    """Emitted when connection is fully closed.

    Args:
        code: Final close code.
        reason: Final close reason.
        reconnecting: True if reconnection will be attempted.
    """

    code: int
    reason: str
    reconnecting: bool


# Union type for all event data
EventData = (
    ConnectingEvent
    | ConnectedEvent
    | DisconnectedEvent
    | ReconnectingEvent
    | ReconnectedEvent
    | MessageEvent[Any]
    | RawMessageEvent
    | ErrorEvent
    | StateChangeEvent
    | PingEvent
    | PongEvent
    | ClosingEvent
    | ClosedEvent
)


class EventEmitter:
    """Thread-safe event emitter with decorator support.

    Supports both synchronous and asynchronous event handlers.
    Handlers are called in registration order.

    Example:
        >>> emitter = EventEmitter()
        >>>
        >>> @emitter.on("connected")
        ... async def on_connect(event: ConnectedEvent) -> None:
        ...     print(f"Connected to {event.uri}")
        >>>
        >>> await emitter.emit_async("connected", ConnectedEvent(uri="wss://..."))
    """

    def __init__(self) -> None:
        """Initialize the event emitter."""
        self._handlers: dict[EventType, list[Handler]] = {}
        self._lock = threading.Lock()

    def on(self, event: EventType) -> Callable[[Handler], Handler]:
        """Decorator for registering event handlers.

        Args:
            event: The event type to handle.

        Returns:
            A decorator that registers the handler.

        Example:
            >>> @emitter.on("message")
            ... async def handle_message(event: MessageEvent) -> None:
            ...     print(event.data)
        """

        def decorator(handler: Handler) -> Handler:
            self.add_handler(event, handler)
            return handler

        return decorator

    def add_handler(self, event: EventType, handler: Handler) -> None:
        """Register an event handler programmatically.

        Args:
            event: The event type to handle.
            handler: The callback function (sync or async).
        """
        with self._lock:
            if event not in self._handlers:
                self._handlers[event] = []
            if handler not in self._handlers[event]:
                self._handlers[event].append(handler)

    def remove_handler(self, event: EventType, handler: Handler) -> bool:
        """Remove an event handler.

        Args:
            event: The event type.
            handler: The handler to remove.

        Returns:
            True if the handler was found and removed.
        """
        with self._lock:
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)
                return True
            return False

    def clear_handlers(self, event: EventType | None = None) -> None:
        """Clear event handlers.

        Args:
            event: Specific event to clear, or None to clear all.
        """
        with self._lock:
            if event is None:
                self._handlers.clear()
            elif event in self._handlers:
                self._handlers[event].clear()

    def handler_count(self, event: EventType | None = None) -> int:
        """Get the number of registered handlers.

        Args:
            event: Specific event to count, or None for total.

        Returns:
            Number of registered handlers.
        """
        with self._lock:
            if event is None:
                return sum(len(h) for h in self._handlers.values())
            return len(self._handlers.get(event, []))

    async def emit_async(self, event: EventType, data: EventData) -> None:
        """Emit an event asynchronously.

        Calls all handlers for the event. Async handlers are awaited,
        sync handlers are called directly.

        Args:
            event: The event type to emit.
            data: The event data to pass to handlers.
        """
        with self._lock:
            handlers = list(self._handlers.get(event, []))

        for handler in handlers:
            try:
                result = handler(data)
                if inspect.iscoroutine(result):
                    await result
            except Exception:
                # Handlers should not raise, but if they do, continue
                # The manager can add its own error handler
                pass

    def emit_sync(self, event: EventType, data: EventData) -> None:
        """Emit an event synchronously.

        Calls all handlers for the event. Async handlers are scheduled
        on the event loop if one is running, otherwise skipped with a warning.

        Args:
            event: The event type to emit.
            data: The event data to pass to handlers.
        """
        with self._lock:
            handlers = list(self._handlers.get(event, []))

        for handler in handlers:
            try:
                result = handler(data)
                if inspect.iscoroutine(result):
                    # Try to schedule on running loop
                    try:
                        loop = asyncio.get_running_loop()
                        _task = loop.create_task(result)
                        del _task  # Explicitly discard - fire-and-forget
                    except RuntimeError:
                        # No running loop - close the coroutine to avoid warning
                        result.close()
            except Exception:
                # Handlers should not raise, but if they do, continue
                pass
