"""WebSocket manager for JetSocket.

This module provides the main user-facing API for WebSocket connections,
including automatic reconnection, heartbeat management, and event handling.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl
import time
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

from jetsocket._core import Opcode
from jetsocket.backoff import BackoffConfig, BackoffStrategy
from jetsocket.buffer import BufferConfig, MessageBuffer, ReplayConfig
from jetsocket.events import (
    BufferOverflowEvent,
    ClosedEvent,
    ClosingEvent,
    ConnectedEvent,
    ConnectingEvent,
    DisconnectedEvent,
    ErrorEvent,
    EventData,
    EventEmitter,
    EventType,
    MessageEvent,
    PingEvent,
    PongEvent,
    RawMessageEvent,
    ReconnectedEvent,
    ReconnectingEvent,
    ReplayCompletedEvent,
    ReplayStartedEvent,
    StateChangeEvent,
)
from jetsocket.exceptions import (
    ConnectionError,
    HandshakeError,
    InvalidStateError,
    TimeoutError,
)
from jetsocket.heartbeat import HeartbeatConfig, HeartbeatManager
from jetsocket.state import ConnectionState, is_valid_transition
from jetsocket.stats import ConnectionStats, _MutableStats
from jetsocket.transport._async import AsyncTransport
from jetsocket.transport.base import BaseTransportConfig
from jetsocket.types import CloseCode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Type variable for deserialized messages
T = TypeVar("T")


# Default serializer/deserializer
def _default_serializer(x: Any) -> bytes:
    """Serialize data to JSON bytes."""
    return json.dumps(x).encode("utf-8")


def _default_deserializer(x: bytes) -> Any:
    """Deserialize JSON bytes to data."""
    return json.loads(x.decode("utf-8"))


# Fatal HTTP status codes - no retry
_FATAL_HTTP_CODES = {401, 403, 404, 410}

# Fatal WebSocket close codes - no retry
_FATAL_WS_CODES = {
    CloseCode.POLICY_VIOLATION,  # 1008
    4401,  # Unauthorized (custom)
    4403,  # Forbidden (custom)
}


class WebSocket(Generic[T]):
    """High-level WebSocket client with auto-reconnect and heartbeat.

    This is the main user-facing API for WebSocket connections. It provides:
    - Automatic reconnection with exponential backoff
    - Heartbeat management (ping/pong)
    - Event-based lifecycle handling
    - Both async and sync APIs
    - Message serialization/deserialization
    - Connection statistics

    Example:
        >>> ws = WebSocket("wss://example.com/ws")
        >>>
        >>> @ws.on("connected")
        ... async def on_connect(event: ConnectedEvent) -> None:
        ...     print(f"Connected to {event.uri}")
        >>>
        >>> @ws.on("message")
        ... async def on_message(event: MessageEvent) -> None:
        ...     print(f"Received: {event.data}")
        >>>
        >>> await ws.connect()
        >>> await ws.send({"type": "subscribe", "channel": "updates"})
        >>> await ws.run()  # Run message loop until closed

    Args:
        uri: The WebSocket URI to connect to.
        reconnect: Whether to automatically reconnect on disconnect.
        backoff: Backoff configuration for reconnection.
        max_connection_age: Maximum time to stay connected before reconnecting.
        heartbeat: Heartbeat configuration for ping/pong.
        buffer: Buffer configuration for message buffering.
        replay: Replay configuration for message replay on reconnect.
        serializer: Function to serialize outgoing messages.
        deserializer: Function to deserialize incoming messages.
        ssl_context: SSL context for secure connections.
        extra_headers: Additional HTTP headers for the handshake.
        subprotocols: WebSocket subprotocols to negotiate.
        compress: Whether to enable compression.
        connect_timeout: Timeout for connection establishment.
        close_timeout: Timeout for graceful close.
        max_message_size: Maximum incoming message size in bytes.
    """

    def __init__(
        self,
        uri: str,
        *,
        # Reconnect configuration
        reconnect: bool = True,
        backoff: BackoffConfig | None = None,
        max_connection_age: float | None = None,
        # Heartbeat: float (interval) or HeartbeatConfig or None
        heartbeat: float | HeartbeatConfig | None = None,
        # Buffer: int (capacity) or BufferConfig or None
        buffer: int | BufferConfig | None = None,
        replay: ReplayConfig | None = None,
        # Serialization
        serializer: Callable[[Any], bytes] | None = None,
        deserializer: Callable[[bytes], T] | None = None,
        # Typed messages (replaces TypedWebSocket)
        message_type: type | None = None,
        # Transport configuration
        ssl_context: ssl.SSLContext | None = None,
        extra_headers: dict[str, str] | None = None,
        subprotocols: list[str] | None = None,
        compress: bool = True,
        compression_threshold: int = 128,
        # Timeouts & limits
        connect_timeout: float = 10.0,
        close_timeout: float = 5.0,
        max_message_size: int = 64 * 1024 * 1024,
    ) -> None:
        """Initialize the WebSocket.

        Args:
            uri: The WebSocket URI to connect to.
            reconnect: Whether to auto-reconnect on disconnect.
            backoff: Backoff configuration for reconnection.
            max_connection_age: Max connection age before proactive reconnect.
            heartbeat: Heartbeat interval in seconds, or HeartbeatConfig.
            buffer: Buffer capacity (int) or BufferConfig.
            replay: Replay configuration for reconnection.
            serializer: Custom message serializer.
            deserializer: Custom message deserializer.
            message_type: Pydantic model for typed messages (auto-configures
                serializer/deserializer). Requires pydantic.
            ssl_context: Custom SSL context for WSS connections.
            extra_headers: Additional headers for the handshake.
            subprotocols: WebSocket subprotocols to request.
            compress: Whether to enable permessage-deflate compression.
            compression_threshold: Minimum payload size to compress.
            connect_timeout: Timeout for connection establishment.
            close_timeout: Timeout for graceful close.
            max_message_size: Maximum message size in bytes.
        """
        self._uri = uri
        self._reconnect_enabled = reconnect
        self._backoff_config = backoff or BackoffConfig()
        self._max_connection_age = max_connection_age
        self._close_timeout = close_timeout
        self._message_type = message_type

        # Normalize scalar shorthands
        if isinstance(heartbeat, (int, float)):
            heartbeat = HeartbeatConfig(interval=float(heartbeat))
        self._heartbeat_config = heartbeat

        if isinstance(buffer, int):
            buffer = BufferConfig(capacity=buffer)
        self._buffer_config = buffer

        self._replay_config = replay

        # Handle message_type (typed messages via Pydantic)
        if message_type is not None and serializer is None and deserializer is None:
            self._setup_typed_serialization(message_type)
        else:
            self._serializer = serializer or _default_serializer
            self._deserializer = deserializer or _default_deserializer

        # Transport configuration
        self._transport_config = BaseTransportConfig(
            connect_timeout=connect_timeout,
            max_message_size=max_message_size,
            ssl_context=ssl_context,
            extra_headers=extra_headers or {},
            subprotocols=subprotocols or [],
            compression=compress,
            compression_threshold=compression_threshold,
        )

        # State
        self._state = ConnectionState.IDLE
        self._transport: AsyncTransport | None = None
        self._backoff = BackoffStrategy(self._backoff_config)
        self._heartbeat: HeartbeatManager | None = None
        self._stats = _MutableStats()
        self._emitter = EventEmitter()

        # Message buffer for replay
        self._buffer: MessageBuffer[T] | None = None
        if self._buffer_config is not None:
            self._buffer = MessageBuffer(self._buffer_config)

        # Tasks
        self._message_task: asyncio.Task[None] | None = None
        self._age_task: asyncio.Task[None] | None = None

        # Message queue for recv()
        self._message_queue: asyncio.Queue[T] = asyncio.Queue()

        # Control flags
        self._running = False
        self._user_closed = False
        self._disconnect_time: float | None = None
        self._attempt = 0
        self._last_error: Exception | None = None
        self._last_dropped_count = 0  # Track buffer overflow events

    def _setup_typed_serialization(self, model_type: type) -> None:
        """Configure serializer/deserializer for Pydantic model type."""
        try:
            from pydantic import BaseModel  # type: ignore[import-not-found]  # noqa: PLC0415, I001
        except ImportError as e:
            raise ImportError(
                "pydantic is required for message_type parameter. "
                "Install it with: pip install pydantic"
            ) from e

        import json as json_mod  # noqa: PLC0415

        def deserializer(data: bytes) -> Any:
            return model_type.model_validate_json(data)  # type: ignore[attr-defined]

        def serializer(msg: Any) -> bytes:
            if isinstance(msg, BaseModel):
                return msg.model_dump_json().encode("utf-8")  # type: ignore[no-any-return]
            return json_mod.dumps(msg).encode("utf-8")

        self._serializer = serializer
        self._deserializer = deserializer

    @property
    def message_type(self) -> type | None:
        """Get the Pydantic message type, if configured."""
        return self._message_type

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def uri(self) -> str:
        """Get the WebSocket URI."""
        return self._uri

    @property
    def state(self) -> ConnectionState:
        """Get the current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected."""
        return self._state == ConnectionState.CONNECTED

    @property
    def latency_ms(self) -> float | None:
        """Get the last measured round-trip latency in milliseconds."""
        if self._heartbeat is not None:
            return self._heartbeat.latency_ms
        return None

    # -------------------------------------------------------------------------
    # Event Registration
    # -------------------------------------------------------------------------

    def on(
        self, event: EventType
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering event handlers.

        Args:
            event: The event type to handle.

        Returns:
            A decorator that registers the handler.

        Example:
            >>> @ws.on("message")
            ... async def handle_message(event: MessageEvent) -> None:
            ...     print(event.data)
        """
        return self._emitter.on(event)

    def add_handler(self, event: EventType, handler: Callable[..., Any]) -> None:
        """Register an event handler programmatically.

        Args:
            event: The event type to handle.
            handler: The callback function (sync or async).
        """
        self._emitter.add_handler(event, handler)

    def remove_handler(self, event: EventType, handler: Callable[..., Any]) -> bool:
        """Remove an event handler.

        Args:
            event: The event type.
            handler: The handler to remove.

        Returns:
            True if the handler was found and removed.
        """
        return self._emitter.remove_handler(event, handler)

    # -------------------------------------------------------------------------
    # Connection Lifecycle
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the WebSocket server.

        This is a non-blocking call that establishes the connection.
        After connecting, use `run()` to start the message loop.

        Raises:
            InvalidStateError: If already connected or connecting.
            ConnectionError: If connection fails.
            HandshakeError: If WebSocket handshake fails.
            TimeoutError: If connection times out.
        """
        if self._state not in (ConnectionState.IDLE, ConnectionState.DISCONNECTED):
            raise InvalidStateError(
                f"Cannot connect in state {self._state.value}",
                current_state=self._state.value,
                required_states=["idle", "disconnected"],
            )

        self._user_closed = False
        self._running = True
        await self._connect_internal()

    async def _connect_internal(self) -> None:
        """Internal connection logic."""
        self._attempt += 1

        # Emit connecting event
        await self._set_state(ConnectionState.CONNECTING)
        await self._emit(
            "connecting", ConnectingEvent(uri=self._uri, attempt=self._attempt)
        )

        # Create transport
        self._transport = AsyncTransport(self._transport_config)

        try:
            await self._transport.connect(self._uri)
        except (ConnectionError, HandshakeError, TimeoutError) as e:
            self._last_error = e
            self._stats.record_error()
            await self._emit(
                "error", ErrorEvent(error=e, fatal=self._is_fatal_error(e))
            )

            if self._is_fatal_error(e):
                await self._set_state(ConnectionState.FAILED)
                raise
            elif self._reconnect_enabled:
                # Schedule reconnect
                await self._schedule_reconnect()
                return
            else:
                await self._set_state(ConnectionState.FAILED)
                raise

        # Connected successfully
        is_reconnect = self._attempt > 1
        if is_reconnect:
            self._stats.mark_reconnected()
            downtime = 0.0
            if self._disconnect_time is not None:
                downtime = time.monotonic() - self._disconnect_time
            await self._emit(
                "reconnected",
                ReconnectedEvent(
                    uri=self._uri, attempt=self._attempt, downtime_seconds=downtime
                ),
            )
        else:
            self._stats.mark_connected()

        self._backoff.success()
        self._last_error = None
        self._disconnect_time = None
        await self._set_state(ConnectionState.CONNECTED)

        # Emit connected event
        subprotocol = self._transport._subprotocol if self._transport else None
        extensions = list(self._transport._extensions) if self._transport else []
        await self._emit(
            "connected",
            ConnectedEvent(
                uri=self._uri, subprotocol=subprotocol, extensions=extensions
            ),
        )

        # Execute replay strategy after reconnection
        if is_reconnect:
            await self._replay_on_reconnect()

        # Start heartbeat if configured
        if self._heartbeat_config is not None:
            self._heartbeat = HeartbeatManager(self._heartbeat_config)
            await self._heartbeat.start(self._send_ping, self._handle_heartbeat_timeout)

        # Start max connection age timer if configured
        if self._max_connection_age is not None:
            self._age_task = asyncio.create_task(
                self._connection_age_timer(), name="jetsocket-age-timer"
            )

        # Start message loop in background
        self._message_task = asyncio.create_task(
            self._message_loop(), name="jetsocket-message-loop"
        )

    async def run(self) -> None:
        """Run until the connection is closed.

        This method blocks until the connection is closed by the user,
        the server, or an unrecoverable error occurs. The message loop
        is already running in the background after connect().

        Raises:
            InvalidStateError: If not connected.
        """
        if self._state not in (
            ConnectionState.CONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.BACKING_OFF,
        ):
            raise InvalidStateError(
                f"Cannot run in state {self._state.value}",
                current_state=self._state.value,
                required_states=["connected"],
            )

        # Wait for message task to complete (connection closed)
        if self._message_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._message_task

    def run_sync(self) -> None:
        """Synchronous entry point for running the WebSocket connection.

        This connects to the server and runs the message loop until closed.

        Example:
            >>> ws = WebSocket("wss://example.com/ws")
            >>> ws.run_sync()  # Blocks until closed
        """
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Internal async run helper."""
        await self.connect()
        await self.run()

    async def close(self, code: int = CloseCode.NORMAL, reason: str = "") -> None:
        """Close the WebSocket connection gracefully.

        Args:
            code: The close code (default: 1000 normal closure).
            reason: Optional close reason string.
        """
        self._user_closed = True
        self._running = False

        if self._state.is_terminal:
            return

        if self._state == ConnectionState.CONNECTED:
            await self._emit(
                "closing", ClosingEvent(code=code, reason=reason, initiated_by="local")
            )
            await self._set_state(ConnectionState.DISCONNECTING)

        # Stop heartbeat
        if self._heartbeat is not None:
            await self._heartbeat.stop()
            self._heartbeat = None

        # Stop age timer
        if self._age_task is not None:
            self._age_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._age_task
            self._age_task = None

        # Close transport
        if self._transport is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._transport.close(code, reason),
                    timeout=self._close_timeout,
                )
            self._transport = None

        # Cancel message task if running
        if self._message_task is not None:
            self._message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._message_task
            self._message_task = None

        self._stats.mark_disconnected()
        await self._set_state(ConnectionState.CLOSED)
        await self._emit(
            "closed", ClosedEvent(code=code, reason=reason, reconnecting=False)
        )

    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------

    async def send(self, data: Any) -> None:
        """Send a message to the server.

        The message is serialized using the configured serializer.

        Args:
            data: The message data to send.

        Raises:
            InvalidStateError: If not connected.
            ConnectionError: If sending fails.
        """
        if not self._state.can_send or self._transport is None:
            raise InvalidStateError(
                f"Cannot send in state {self._state.value}",
                current_state=self._state.value,
                required_states=["connected"],
            )

        serialized = self._serializer(data)
        await self._transport.send(serialized, binary=False)
        self._stats.record_message_sent(len(serialized))

    async def send_raw(self, data: bytes, *, binary: bool = True) -> None:
        """Send raw bytes to the server.

        Args:
            data: The raw bytes to send.
            binary: If True, send as binary frame. If False, send as text.

        Raises:
            InvalidStateError: If not connected.
            ConnectionError: If sending fails.
        """
        if not self._state.can_send or self._transport is None:
            raise InvalidStateError(
                f"Cannot send in state {self._state.value}",
                current_state=self._state.value,
                required_states=["connected"],
            )

        await self._transport.send(data, binary=binary)
        self._stats.record_message_sent(len(data))

    async def recv(self) -> T:
        """Receive the next message from the server.

        This method blocks until a message is received. The message loop
        runs in the background and populates the message queue.

        Returns:
            The deserialized message.

        Raises:
            InvalidStateError: If not connected.
            ConnectionError: If the connection is lost.
        """
        if self._state not in (
            ConnectionState.CONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.BACKING_OFF,
        ):
            # Check if there are queued messages even when disconnected
            if not self._message_queue.empty():
                return await self._message_queue.get()
            raise InvalidStateError(
                f"Cannot receive in state {self._state.value}",
                current_state=self._state.value,
                required_states=["connected"],
            )

        try:
            return await self._message_queue.get()
        except asyncio.CancelledError:
            raise ConnectionError(
                "Connection closed while waiting for message"
            ) from None

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def stats(self) -> ConnectionStats:
        """Get a snapshot of connection statistics.

        Returns:
            An immutable ConnectionStats instance.
        """
        self._stats.state = self._state
        if self._heartbeat is not None:
            latency = self._heartbeat.latency_ms
            avg = self._heartbeat.latency_avg_ms
            if latency is not None:
                self._stats.update_latency(latency, avg)
        return self._stats.snapshot()

    # -------------------------------------------------------------------------
    # Async Iteration
    # -------------------------------------------------------------------------

    def __aiter__(self) -> AsyncIterator[T]:
        """Iterate over incoming messages.

        Example:
            >>> async for message in ws:
            ...     print(message)
        """
        return self

    async def __anext__(self) -> T:
        """Get the next message.

        Raises:
            StopAsyncIteration: When the connection is closed.
        """
        if not self._running and self._message_queue.empty():
            raise StopAsyncIteration

        try:
            return await self._message_queue.get()
        except asyncio.CancelledError:
            raise StopAsyncIteration from None

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> WebSocket[T]:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        """Async context manager exit."""
        await self.close()

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    async def _set_state(self, new_state: ConnectionState) -> None:
        """Transition to a new state with validation and event emission."""
        if new_state == self._state:
            return

        if not is_valid_transition(self._state, new_state):
            # Log warning but allow transition for robustness
            pass

        old_state = self._state
        self._state = new_state
        self._stats.state = new_state

        await self._emit(
            "state_change", StateChangeEvent(old_state=old_state, new_state=new_state)
        )

    async def _emit(self, event: EventType, data: EventData) -> None:
        """Emit an event to registered handlers."""
        await self._emitter.emit_async(event, data)

    async def _message_loop(self) -> None:
        """Main message receiving loop."""
        if self._transport is None:
            return

        while self._running and self._state == ConnectionState.CONNECTED:
            try:
                frame = await self._transport.recv()

                # Handle pong frames for heartbeat
                if frame.opcode == Opcode.PONG:
                    await self._handle_pong(frame.payload)
                    continue

                # Emit raw message event
                await self._emit(
                    "raw_message",
                    RawMessageEvent(data=frame.payload, opcode=int(frame.opcode)),
                )

                # Deserialize and emit message event
                try:
                    data = self._deserializer(frame.payload)

                    # Check for application-level pong
                    if (
                        self._heartbeat is not None
                        and self._heartbeat.on_application_message(data)
                    ):
                        continue

                    # Track message in buffer for replay
                    await self._track_received_message(data)

                    await self._emit(
                        "message", MessageEvent(data=data, raw=frame.payload)
                    )

                    # Add to queue for recv()
                    await self._message_queue.put(data)
                    self._stats.record_message_received(len(frame.payload))

                except Exception as e:
                    # Deserialization error - emit error but continue
                    self._stats.record_error()
                    await self._emit("error", ErrorEvent(error=e, fatal=False))

            except ConnectionError as e:
                # Connection lost
                self._last_error = e
                self._stats.record_error()
                await self._handle_disconnect(
                    code=CloseCode.ABNORMAL,
                    reason=str(e),
                    was_clean=False,
                )
                break

            except Exception as e:
                # Unexpected error
                self._last_error = e
                self._stats.record_error()
                await self._emit("error", ErrorEvent(error=e, fatal=True))
                await self._handle_disconnect(
                    code=CloseCode.INTERNAL_ERROR,
                    reason=str(e),
                    was_clean=False,
                )
                break

    async def _handle_disconnect(self, code: int, reason: str, was_clean: bool) -> None:
        """Handle a disconnection event."""
        self._disconnect_time = time.monotonic()
        self._stats.mark_disconnected()

        # Stop heartbeat
        if self._heartbeat is not None:
            await self._heartbeat.stop()
            self._heartbeat.reset()

        # Stop age timer
        if self._age_task is not None:
            self._age_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._age_task
            self._age_task = None

        await self._set_state(ConnectionState.DISCONNECTED)
        await self._emit(
            "disconnected",
            DisconnectedEvent(code=code, reason=reason, was_clean=was_clean),
        )

        # Reconnect if enabled and not user-initiated
        if (
            self._reconnect_enabled
            and not self._user_closed
            and not self._is_fatal_code(code)
        ):
            await self._schedule_reconnect()
            return

        # No reconnect - close permanently
        await self._set_state(ConnectionState.CLOSED)
        await self._emit(
            "closed", ClosedEvent(code=code, reason=reason, reconnecting=False)
        )

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._backoff.exhausted:
            await self._set_state(ConnectionState.FAILED)
            await self._emit(
                "error",
                ErrorEvent(
                    error=ConnectionError("Max reconnection attempts exhausted"),
                    fatal=True,
                ),
            )
            return

        await self._set_state(ConnectionState.RECONNECTING)

        # Calculate delay
        delay = self._backoff.next_delay()

        await self._emit(
            "reconnecting",
            ReconnectingEvent(
                attempt=self._backoff.attempt,
                delay=delay,
                last_error=self._last_error,
            ),
        )

        await self._set_state(ConnectionState.BACKING_OFF)

        # Wait for backoff delay
        await asyncio.sleep(delay)

        if not self._running or self._user_closed:
            return

        # Attempt reconnection (which will start the message loop)
        await self._connect_internal()

    async def _send_ping(self, payload: bytes) -> None:
        """Send a ping frame (callback for HeartbeatManager)."""
        if self._transport is None or not self._state.can_send:
            return

        await self._transport.ping(payload)
        await self._emit("ping", PingEvent(payload=payload))

    async def _handle_pong(self, payload: bytes) -> None:
        """Handle a received pong frame."""
        latency_ms: float | None = None
        if self._heartbeat is not None:
            latency_ms = self._heartbeat.on_pong(payload)
        await self._emit("pong", PongEvent(payload=payload, latency_ms=latency_ms))

    async def _handle_heartbeat_timeout(self) -> None:
        """Handle heartbeat timeout (callback for HeartbeatManager)."""
        await self._emit(
            "error",
            ErrorEvent(
                error=TimeoutError("Heartbeat timeout", timeout=0, operation="pong"),
                fatal=True,
            ),
        )

        # Close and reconnect
        if self._transport is not None:
            self._transport._connected = False

        await self._handle_disconnect(
            code=CloseCode.ABNORMAL,
            reason="Heartbeat timeout",
            was_clean=False,
        )

    async def _connection_age_timer(self) -> None:
        """Timer to enforce max connection age."""
        if self._max_connection_age is None:
            return

        await asyncio.sleep(self._max_connection_age)

        if self._state == ConnectionState.CONNECTED:
            # Close current connection to trigger reconnect
            await self._emit(
                "closing",
                ClosingEvent(
                    code=CloseCode.NORMAL,
                    reason="Max connection age reached",
                    initiated_by="local",
                ),
            )

            if self._transport is not None:
                self._transport._connected = False

            await self._handle_disconnect(
                code=CloseCode.NORMAL,
                reason="Max connection age reached",
                was_clean=True,
            )

    def _is_fatal_error(self, error: Exception) -> bool:
        """Check if an error is fatal (no retry)."""
        # Config errors
        if isinstance(error, (ValueError, TypeError)):
            return True

        # Handshake errors with fatal HTTP status
        return (
            isinstance(error, HandshakeError) and error.status_code in _FATAL_HTTP_CODES
        )

    def _is_fatal_code(self, code: int) -> bool:
        """Check if a close code is fatal (no retry)."""
        return code in _FATAL_WS_CODES

    async def _replay_on_reconnect(self) -> None:
        """Execute replay strategy after reconnection.

        This method is called after a successful reconnection to replay
        messages according to the configured replay strategy.
        """
        if self._replay_config is None or self._replay_config.mode == "none":
            return

        mode = self._replay_config.mode
        start_time = time.monotonic()

        # Get buffer state
        last_seq = self._buffer.last_sequence_id if self._buffer else None
        message_count = len(self._buffer) if self._buffer else 0

        # Emit replay started event
        await self._emit(
            "replay_started",
            ReplayStartedEvent(
                mode=mode,
                last_sequence_id=last_seq,
                message_count=message_count,
            ),
        )

        replayed_count = 0

        if mode == "sequence_id":
            # Call the on_replay callback with last sequence ID
            if last_seq is not None and self._replay_config.on_replay is not None:
                try:
                    await self._replay_config.on_replay(last_seq)
                    replayed_count = 1  # Callback was executed
                except Exception as e:
                    self._stats.record_error()
                    await self._emit("error", ErrorEvent(error=e, fatal=False))

        elif mode == "full_buffer" and self._buffer is not None:
            # Resend all buffered messages
            messages = self._buffer.drain()
            for msg in messages:
                try:
                    await self.send(msg)
                    replayed_count += 1
                except Exception as e:
                    self._stats.record_error()
                    await self._emit("error", ErrorEvent(error=e, fatal=False))
                    break

        # Emit replay completed event
        duration_ms = (time.monotonic() - start_time) * 1000
        await self._emit(
            "replay_completed",
            ReplayCompletedEvent(
                mode=mode,
                replayed_count=replayed_count,
                duration_ms=duration_ms,
            ),
        )

    async def _track_received_message(self, data: T) -> None:
        """Track a received message in the buffer for replay.

        Args:
            data: The deserialized message data.
        """
        if self._buffer is None or self._replay_config is None:
            return

        # Extract sequence ID if configured
        sequence_id = None
        if self._replay_config.sequence_extractor is not None:
            with contextlib.suppress(Exception):
                sequence_id = self._replay_config.sequence_extractor(data)

        # Push to buffer
        prev_dropped = self._buffer.total_dropped
        with contextlib.suppress(Exception):
            self._buffer.push(data, sequence_id)

        # Check for buffer overflow
        if self._buffer.total_dropped > prev_dropped:
            dropped_count = self._buffer.total_dropped - self._last_dropped_count
            self._last_dropped_count = self._buffer.total_dropped
            await self._emit(
                "buffer_overflow",
                BufferOverflowEvent(
                    capacity=self._buffer.capacity,
                    dropped_count=dropped_count,
                    policy=self._buffer_config.overflow_policy
                    if self._buffer_config
                    else "drop_oldest",
                ),
            )

    @property
    def buffer(self) -> MessageBuffer[T] | None:
        """Get the message buffer, if configured."""
        return self._buffer

    @property
    def buffer_fill_ratio(self) -> float:
        """Get the buffer fill ratio (0.0 to 1.0), or 0.0 if no buffer."""
        return self._buffer.fill_ratio if self._buffer else 0.0
