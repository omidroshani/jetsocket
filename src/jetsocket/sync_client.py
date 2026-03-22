"""Synchronous WebSocket client for JetSocket.

This module provides a synchronous API that wraps the async WebSocket
using a background thread with its own event loop. This approach provides
full feature parity with the async API including reconnection, heartbeat,
buffering, and event handling.

This is the same approach used by libraries like grpcio, httpx, and websocket-client.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import queue
import ssl
import threading
import weakref
from collections.abc import Callable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

from jetsocket.backoff import BackoffConfig
from jetsocket.buffer import BufferConfig, ReplayConfig
from jetsocket.events import EventData, EventType, Handler, MessageEvent
from jetsocket.exceptions import ConnectionError, InvalidStateError, TimeoutError
from jetsocket.heartbeat import HeartbeatConfig
from jetsocket.manager import WebSocket
from jetsocket.state import ConnectionState
from jetsocket.stats import ConnectionStats, _MutableStats

if TYPE_CHECKING:
    from types import TracebackType


# Type variable for deserialized messages
T = TypeVar("T")

# Sentinel for shutdown
_SHUTDOWN = object()

# Track all active sync clients for cleanup at exit
_active_clients: weakref.WeakSet[SyncWebSocket[Any]] = weakref.WeakSet()


def _cleanup_clients() -> None:
    """Clean up all active sync clients on exit."""
    for client in list(_active_clients):
        with contextlib.suppress(Exception):
            client.close()


atexit.register(_cleanup_clients)


class SyncWebSocket(Generic[T]):
    """Synchronous WebSocket client with full feature parity.

    Wraps WebSocket with a background event loop thread, providing
    a blocking API for WebSocket communication. Supports all features of
    the async API including reconnection, heartbeat, buffering, and events.

    Example:
        >>> with SyncWebSocket("wss://example.com/ws") as ws:
        ...     ws.send({"subscribe": "trades"})
        ...     for msg in ws:
        ...         print(msg)

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
        # Typed messages
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
        """Initialize the synchronous WebSocket."""
        self._uri = uri
        self._manager_kwargs: dict[str, Any] = {
            "reconnect": reconnect,
            "backoff": backoff,
            "max_connection_age": max_connection_age,
            "heartbeat": heartbeat,
            "buffer": buffer,
            "replay": replay,
            "serializer": serializer,
            "deserializer": deserializer,
            "message_type": message_type,
            "ssl_context": ssl_context,
            "extra_headers": extra_headers,
            "subprotocols": subprotocols,
            "compress": compress,
            "compression_threshold": compression_threshold,
            "connect_timeout": connect_timeout,
            "close_timeout": close_timeout,
            "max_message_size": max_message_size,
        }

        # Background thread and event loop
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._manager: WebSocket[T] | None = None
        self._started = threading.Event()
        self._closed = False

        # Message queue for sync recv
        self._message_queue: queue.Queue[T | object] = queue.Queue()

        # Event handlers storage (registered before connect)
        self._pending_handlers: list[tuple[EventType, Handler]] = []

        # Thread lock for state access
        self._lock = threading.Lock()

        # Track for cleanup
        _active_clients.add(self)

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
        if self._manager is None:
            return ConnectionState.IDLE
        return self._manager.state

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected."""
        return self.state == ConnectionState.CONNECTED

    @property
    def latency_ms(self) -> float | None:
        """Get the last measured round-trip latency in milliseconds."""
        if self._manager is None:
            return None
        return self._manager.latency_ms

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the WebSocket server.

        This starts a background thread with an event loop and establishes
        the WebSocket connection. Blocks until connection is established.

        Raises:
            InvalidStateError: If already connected or connecting.
            ConnectionError: If connection fails.
            TimeoutError: If connection times out.
        """
        with self._lock:
            if self._closed:
                raise InvalidStateError(
                    "Client has been closed",
                    current_state="closed",
                    required_states=["idle"],
                )
            if self._thread is not None and self._thread.is_alive():
                raise InvalidStateError(
                    "Already connected or connecting",
                    current_state="connected",
                    required_states=["idle"],
                )

        # Start background thread
        self._closed = False
        self._started.clear()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="jetsocket-sync-loop",
            daemon=True,
        )
        self._thread.start()

        # Wait for event loop to start
        if not self._started.wait(timeout=30.0):
            raise TimeoutError(
                "Background event loop failed to start",
                timeout=30.0,
                operation="start_loop",
            )

        # Connect via the background loop
        if self._loop is None:
            raise ConnectionError("Event loop not available")

        future = asyncio.run_coroutine_threadsafe(self._connect_async(), self._loop)
        try:
            future.result(
                timeout=self._manager_kwargs.get("connect_timeout", 10.0) + 5.0
            )
        except Exception as e:
            self._shutdown_loop()
            if isinstance(e, ConnectionError | TimeoutError):
                raise
            raise ConnectionError(f"Failed to connect: {e}") from e

    async def _connect_async(self) -> None:
        """Async connect implementation."""
        if self._manager is None:
            raise ConnectionError("Manager not initialized")
        await self._manager.connect()

    def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection gracefully.

        Args:
            code: The close code (default: 1000 normal closure).
            reason: Optional close reason string.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True

        # Signal message queue shutdown
        self._message_queue.put(_SHUTDOWN)

        # Close via the background loop
        if self._loop is not None and self._manager is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._manager.close(code, reason), self._loop
                )
                future.result(
                    timeout=self._manager_kwargs.get("close_timeout", 5.0) + 2.0
                )
            except Exception:
                pass

        self._shutdown_loop()

    def _shutdown_loop(self) -> None:
        """Shutdown the background event loop and thread."""
        loop = self._loop
        thread = self._thread

        self._loop = None
        self._manager = None
        self._thread = None

        if loop is not None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(loop.stop)

        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------

    def send(self, data: Any) -> None:
        """Send a message to the server.

        The message is serialized using the configured serializer.

        Args:
            data: The message data to send.

        Raises:
            InvalidStateError: If not connected.
            ConnectionError: If sending fails.
        """
        if self._loop is None or self._manager is None:
            raise InvalidStateError(
                "Not connected",
                current_state="disconnected",
                required_states=["connected"],
            )

        future = asyncio.run_coroutine_threadsafe(self._manager.send(data), self._loop)
        try:
            future.result(timeout=30.0)
        except Exception as e:
            if isinstance(e, InvalidStateError | ConnectionError):
                raise
            raise ConnectionError(f"Failed to send: {e}") from e

    def send_raw(self, data: bytes, *, binary: bool = True) -> None:
        """Send raw bytes to the server.

        Args:
            data: The raw bytes to send.
            binary: If True, send as binary frame. If False, send as text.

        Raises:
            InvalidStateError: If not connected.
            ConnectionError: If sending fails.
        """
        if self._loop is None or self._manager is None:
            raise InvalidStateError(
                "Not connected",
                current_state="disconnected",
                required_states=["connected"],
            )

        future = asyncio.run_coroutine_threadsafe(
            self._manager.send_raw(data, binary=binary), self._loop
        )
        try:
            future.result(timeout=30.0)
        except Exception as e:
            if isinstance(e, InvalidStateError | ConnectionError):
                raise
            raise ConnectionError(f"Failed to send: {e}") from e

    def recv(self, timeout: float | None = None) -> T:
        """Receive the next message from the server.

        This method blocks until a message is received.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            The deserialized message.

        Raises:
            InvalidStateError: If not connected.
            TimeoutError: If timeout is exceeded.
            ConnectionError: If the connection is closed.
        """
        if self._closed and self._message_queue.empty():
            raise InvalidStateError(
                "Connection closed",
                current_state="closed",
                required_states=["connected"],
            )

        try:
            msg = self._message_queue.get(timeout=timeout)
            if msg is _SHUTDOWN:
                raise ConnectionError("Connection closed")
            return msg  # type: ignore[return-value]
        except queue.Empty:
            raise TimeoutError(
                f"No message received within {timeout} seconds",
                timeout=timeout or 0.0,
                operation="recv",
            ) from None

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def stats(self) -> ConnectionStats:
        """Get a snapshot of connection statistics.

        Returns:
            An immutable ConnectionStats instance.
        """
        if self._manager is None:
            return _MutableStats().snapshot()
        return self._manager.stats()

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def on(self, event: EventType) -> Callable[[Handler], Handler]:
        """Decorator for registering event handlers.

        Handlers can be registered before or after connecting. Note that
        event handlers will be called from the background thread, so they
        should be thread-safe.

        Args:
            event: The event type to handle.

        Returns:
            A decorator that registers the handler.

        Example:
            >>> @ws.on("message")
            ... def handle_message(event: MessageEvent) -> None:
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
            if self._manager is not None:
                self._manager.add_handler(event, handler)
            else:
                self._pending_handlers.append((event, handler))

    def remove_handler(self, event: EventType, handler: Handler) -> bool:
        """Remove an event handler.

        Args:
            event: The event type.
            handler: The handler to remove.

        Returns:
            True if the handler was found and removed.
        """
        with self._lock:
            if self._manager is not None:
                return self._manager.remove_handler(event, handler)
            else:
                for i, (e, h) in enumerate(self._pending_handlers):
                    if e == event and h == handler:
                        self._pending_handlers.pop(i)
                        return True
                return False

    # -------------------------------------------------------------------------
    # Iteration
    # -------------------------------------------------------------------------

    def __iter__(self) -> Iterator[T]:
        """Iterate over incoming messages.

        Example:
            >>> for message in ws:
            ...     print(message)
        """
        return self

    def __next__(self) -> T:
        """Get the next message.

        Raises:
            StopIteration: When the connection is closed.
        """
        if self._closed and self._message_queue.empty():
            raise StopIteration

        try:
            msg = self._message_queue.get(timeout=0.1)
            if msg is _SHUTDOWN:
                raise StopIteration
            return msg  # type: ignore[return-value]
        except queue.Empty:
            # Check if still running
            if self._closed:
                raise StopIteration
            # Retry
            return self.__next__()

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    def __enter__(self) -> SyncWebSocket[T]:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.close()

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _run_event_loop(self) -> None:
        """Run the event loop in the background thread."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Create the manager
            self._manager = WebSocket[T](self._uri, **self._manager_kwargs)

            # Register pending handlers
            with self._lock:
                for event, handler in self._pending_handlers:
                    self._manager.add_handler(event, handler)
                self._pending_handlers.clear()

            # Set up message forwarding
            self._manager.add_handler("message", self._on_message)

            # Signal that we're ready
            self._started.set()

            # Run the event loop
            self._loop.run_forever()

        except Exception:
            self._started.set()  # Unblock waiting connect
        finally:
            # Clean up
            if self._loop is not None:
                try:
                    # Cancel all tasks
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()

                    # Run until tasks complete
                    if pending:
                        self._loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )

                    self._loop.close()
                except Exception:
                    pass

    def _on_message(self, event: EventData) -> None:
        """Forward messages to the sync queue.

        Args:
            event: The message event.
        """
        if isinstance(event, MessageEvent):
            with contextlib.suppress(queue.Full):
                self._message_queue.put_nowait(event.data)

    def __repr__(self) -> str:
        """Return a string representation of the client."""
        return f"SyncWebSocket(uri={self._uri!r}, state={self.state.value})"

    def __del__(self) -> None:
        """Clean up resources on deletion."""
        try:
            if not self._closed:
                self.close()
        except Exception:
            pass