"""Connection statistics for JetSocket.

This module provides statistics tracking for WebSocket connections,
including message counts, byte counters, latency, and uptime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jetsocket.state import ConnectionState


@dataclass(frozen=True, slots=True)
class ConnectionStats:
    """Immutable snapshot of connection statistics.

    This dataclass provides a read-only view of connection metrics
    at a specific point in time.

    Args:
        state: Current connection state.
        uptime_seconds: Time since connection established (0 if not connected).
        messages_sent: Total messages sent.
        messages_received: Total messages received.
        bytes_sent: Total bytes sent.
        bytes_received: Total bytes received.
        reconnect_count: Number of successful reconnections.
        last_reconnect_at: Timestamp of last reconnection.
        latency_ms: Last measured round-trip latency in milliseconds.
        latency_avg_ms: Rolling average latency in milliseconds.
        last_message_at: Timestamp of last message (sent or received).
        connection_age_seconds: Total time since first connection attempt.
        errors: Total error count.
    """

    state: ConnectionState
    uptime_seconds: float
    messages_sent: int
    messages_received: int
    bytes_sent: int
    bytes_received: int
    reconnect_count: int
    last_reconnect_at: datetime | None
    latency_ms: float | None
    latency_avg_ms: float | None
    last_message_at: datetime | None
    connection_age_seconds: float
    errors: int


@dataclass
class _MutableStats:
    """Internal mutable statistics tracker.

    This class tracks statistics during operation and provides
    a method to create an immutable snapshot.

    Not part of the public API.
    """

    # Import state lazily to avoid circular imports
    _state: ConnectionState | None = field(default=None, repr=False)

    # Counters
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    reconnect_count: int = 0
    errors: int = 0

    # Timestamps (monotonic for duration calculations)
    _connected_at: float | None = field(default=None, repr=False)
    _first_connect_at: float | None = field(default=None, repr=False)
    _last_reconnect_at: datetime | None = None
    _last_message_at: datetime | None = None

    # Latency
    _latency_ms: float | None = field(default=None, repr=False)
    _latency_avg_ms: float | None = field(default=None, repr=False)

    @property
    def state(self) -> ConnectionState:
        """Get the current connection state."""
        if self._state is None:
            # Lazy import to avoid circular dependency
            from jetsocket.state import ConnectionState  # noqa: PLC0415

            return ConnectionState.IDLE
        return self._state

    @state.setter
    def state(self, value: ConnectionState) -> None:
        """Set the current connection state."""
        self._state = value

    def mark_connected(self) -> None:
        """Mark the connection as established."""
        now = time.monotonic()
        self._connected_at = now
        if self._first_connect_at is None:
            self._first_connect_at = now

    def mark_disconnected(self) -> None:
        """Mark the connection as disconnected."""
        self._connected_at = None

    def mark_reconnected(self) -> None:
        """Mark a successful reconnection."""
        self.reconnect_count += 1
        self._last_reconnect_at = datetime.now(timezone.utc)
        self.mark_connected()

    def record_message_sent(self, byte_count: int) -> None:
        """Record a sent message.

        Args:
            byte_count: Number of bytes sent.
        """
        self.messages_sent += 1
        self.bytes_sent += byte_count
        self._last_message_at = datetime.now(timezone.utc)

    def record_message_received(self, byte_count: int) -> None:
        """Record a received message.

        Args:
            byte_count: Number of bytes received.
        """
        self.messages_received += 1
        self.bytes_received += byte_count
        self._last_message_at = datetime.now(timezone.utc)

    def record_error(self) -> None:
        """Record an error occurrence."""
        self.errors += 1

    def update_latency(self, latency_ms: float, avg_ms: float | None) -> None:
        """Update latency measurements.

        Args:
            latency_ms: Last measured latency.
            avg_ms: Rolling average latency.
        """
        self._latency_ms = latency_ms
        self._latency_avg_ms = avg_ms

    def reset(self) -> None:
        """Reset all statistics.

        Called when a fresh connection is desired (not reconnection).
        """
        self.messages_sent = 0
        self.messages_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.reconnect_count = 0
        self.errors = 0
        self._connected_at = None
        self._first_connect_at = None
        self._last_reconnect_at = None
        self._last_message_at = None
        self._latency_ms = None
        self._latency_avg_ms = None

    def snapshot(self) -> ConnectionStats:
        """Create an immutable snapshot of current statistics.

        Returns:
            A frozen ConnectionStats instance.
        """
        now = time.monotonic()

        # Calculate uptime and connection age
        uptime = now - self._connected_at if self._connected_at is not None else 0.0
        age = (
            now - self._first_connect_at if self._first_connect_at is not None else 0.0
        )

        return ConnectionStats(
            state=self.state,
            uptime_seconds=uptime,
            messages_sent=self.messages_sent,
            messages_received=self.messages_received,
            bytes_sent=self.bytes_sent,
            bytes_received=self.bytes_received,
            reconnect_count=self.reconnect_count,
            last_reconnect_at=self._last_reconnect_at,
            latency_ms=self._latency_ms,
            latency_avg_ms=self._latency_avg_ms,
            last_message_at=self._last_message_at,
            connection_age_seconds=age,
            errors=self.errors,
        )
