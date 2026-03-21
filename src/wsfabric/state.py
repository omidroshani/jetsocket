"""Connection state machine for WSFabric.

This module defines the connection states and manages state transitions
for WebSocket connections. All state changes emit events for observability.
"""

from __future__ import annotations

import enum


class ConnectionState(enum.Enum):
    """WebSocket connection states.

    The state machine follows this general flow:

        IDLE → CONNECTING → CONNECTED ←→ RECONNECTING
                    ↓           ↓              ↓
               FAILED      DISCONNECTING  BACKING_OFF
                              ↓
                           CLOSED

    States:
        IDLE: Initial state, no connection attempted.
        CONNECTING: TCP connection and WebSocket handshake in progress.
        CONNECTED: Fully connected and ready for messages.
        DISCONNECTING: Close handshake initiated.
        DISCONNECTED: Connection closed (may reconnect).
        RECONNECTING: Preparing to reconnect.
        BACKING_OFF: Waiting before reconnect attempt.
        FAILED: Max retries exhausted or fatal error.
        CLOSED: User explicitly closed, no reconnect.
    """

    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    BACKING_OFF = "backing_off"
    FAILED = "failed"
    CLOSED = "closed"

    @property
    def is_active(self) -> bool:
        """Return True if the connection is active or connecting."""
        return self in (
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
        )

    @property
    def is_terminal(self) -> bool:
        """Return True if this is a terminal state (no further transitions)."""
        return self in (
            ConnectionState.FAILED,
            ConnectionState.CLOSED,
        )

    @property
    def can_send(self) -> bool:
        """Return True if messages can be sent in this state."""
        return self == ConnectionState.CONNECTED

    @property
    def can_reconnect(self) -> bool:
        """Return True if reconnection is possible from this state."""
        return self in (
            ConnectionState.DISCONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.BACKING_OFF,
        )


# Valid state transitions
VALID_TRANSITIONS: dict[ConnectionState, set[ConnectionState]] = {
    ConnectionState.IDLE: {ConnectionState.CONNECTING},
    ConnectionState.CONNECTING: {
        ConnectionState.CONNECTED,
        ConnectionState.BACKING_OFF,
        ConnectionState.FAILED,
    },
    ConnectionState.CONNECTED: {
        ConnectionState.DISCONNECTING,
        ConnectionState.DISCONNECTED,
        ConnectionState.RECONNECTING,
    },
    ConnectionState.DISCONNECTING: {
        ConnectionState.DISCONNECTED,
        ConnectionState.CLOSED,
    },
    ConnectionState.DISCONNECTED: {
        ConnectionState.RECONNECTING,
        ConnectionState.CLOSED,
    },
    ConnectionState.RECONNECTING: {
        ConnectionState.BACKING_OFF,
        ConnectionState.CONNECTING,
        ConnectionState.FAILED,
    },
    ConnectionState.BACKING_OFF: {
        ConnectionState.CONNECTING,
        ConnectionState.FAILED,
        ConnectionState.CLOSED,
    },
    ConnectionState.FAILED: set(),  # Terminal
    ConnectionState.CLOSED: set(),  # Terminal
}


def is_valid_transition(from_state: ConnectionState, to_state: ConnectionState) -> bool:
    """Check if a state transition is valid.

    Args:
        from_state: The current state.
        to_state: The desired next state.

    Returns:
        True if the transition is valid.
    """
    return to_state in VALID_TRANSITIONS.get(from_state, set())
