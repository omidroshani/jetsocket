"""Tests for jetsocket.state module."""

from __future__ import annotations

import pytest

from jetsocket.state import (
    VALID_TRANSITIONS,
    ConnectionState,
    is_valid_transition,
)


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_all_states_defined(self) -> None:
        """Test that all expected states are defined."""
        expected_states = [
            "IDLE",
            "CONNECTING",
            "CONNECTED",
            "DISCONNECTING",
            "DISCONNECTED",
            "RECONNECTING",
            "BACKING_OFF",
            "FAILED",
            "CLOSED",
        ]
        actual_states = [s.name for s in ConnectionState]
        assert sorted(actual_states) == sorted(expected_states)

    def test_state_values(self) -> None:
        """Test state string values."""
        assert ConnectionState.IDLE.value == "idle"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.FAILED.value == "failed"
        assert ConnectionState.CLOSED.value == "closed"

    def test_is_active(self) -> None:
        """Test is_active property."""
        assert ConnectionState.CONNECTING.is_active
        assert ConnectionState.CONNECTED.is_active
        assert not ConnectionState.IDLE.is_active
        assert not ConnectionState.DISCONNECTED.is_active
        assert not ConnectionState.FAILED.is_active
        assert not ConnectionState.CLOSED.is_active

    def test_is_terminal(self) -> None:
        """Test is_terminal property."""
        assert ConnectionState.FAILED.is_terminal
        assert ConnectionState.CLOSED.is_terminal
        assert not ConnectionState.IDLE.is_terminal
        assert not ConnectionState.CONNECTED.is_terminal
        assert not ConnectionState.DISCONNECTED.is_terminal

    def test_can_send(self) -> None:
        """Test can_send property."""
        assert ConnectionState.CONNECTED.can_send
        assert not ConnectionState.IDLE.can_send
        assert not ConnectionState.CONNECTING.can_send
        assert not ConnectionState.DISCONNECTING.can_send
        assert not ConnectionState.FAILED.can_send

    def test_can_reconnect(self) -> None:
        """Test can_reconnect property."""
        assert ConnectionState.DISCONNECTED.can_reconnect
        assert ConnectionState.RECONNECTING.can_reconnect
        assert ConnectionState.BACKING_OFF.can_reconnect
        assert not ConnectionState.IDLE.can_reconnect
        assert not ConnectionState.CONNECTED.can_reconnect
        assert not ConnectionState.FAILED.can_reconnect
        assert not ConnectionState.CLOSED.can_reconnect


class TestStateTransitions:
    """Tests for state transition validation."""

    def test_valid_transitions_from_idle(self) -> None:
        """Test valid transitions from IDLE state."""
        assert is_valid_transition(ConnectionState.IDLE, ConnectionState.CONNECTING)
        assert not is_valid_transition(ConnectionState.IDLE, ConnectionState.CONNECTED)
        assert not is_valid_transition(ConnectionState.IDLE, ConnectionState.CLOSED)

    def test_valid_transitions_from_connecting(self) -> None:
        """Test valid transitions from CONNECTING state."""
        assert is_valid_transition(
            ConnectionState.CONNECTING, ConnectionState.CONNECTED
        )
        assert is_valid_transition(
            ConnectionState.CONNECTING, ConnectionState.BACKING_OFF
        )
        assert is_valid_transition(ConnectionState.CONNECTING, ConnectionState.FAILED)
        assert not is_valid_transition(ConnectionState.CONNECTING, ConnectionState.IDLE)

    def test_valid_transitions_from_connected(self) -> None:
        """Test valid transitions from CONNECTED state."""
        assert is_valid_transition(
            ConnectionState.CONNECTED, ConnectionState.DISCONNECTING
        )
        assert is_valid_transition(
            ConnectionState.CONNECTED, ConnectionState.DISCONNECTED
        )
        assert is_valid_transition(
            ConnectionState.CONNECTED, ConnectionState.RECONNECTING
        )
        assert not is_valid_transition(
            ConnectionState.CONNECTED, ConnectionState.CONNECTING
        )

    def test_terminal_states_have_no_transitions(self) -> None:
        """Test that terminal states have no valid transitions."""
        for state in ConnectionState:
            assert not is_valid_transition(ConnectionState.FAILED, state)
            assert not is_valid_transition(ConnectionState.CLOSED, state)

    def test_all_states_in_transition_map(self) -> None:
        """Test that all states are covered in the transition map."""
        for state in ConnectionState:
            assert state in VALID_TRANSITIONS

    @pytest.mark.parametrize(
        "from_state,to_state,expected",
        [
            (ConnectionState.IDLE, ConnectionState.CONNECTING, True),
            (ConnectionState.CONNECTING, ConnectionState.CONNECTED, True),
            (ConnectionState.CONNECTED, ConnectionState.CLOSED, False),
            (ConnectionState.DISCONNECTING, ConnectionState.CLOSED, True),
            (ConnectionState.BACKING_OFF, ConnectionState.CONNECTING, True),
            (ConnectionState.RECONNECTING, ConnectionState.BACKING_OFF, True),
        ],
    )
    def test_specific_transitions(
        self,
        from_state: ConnectionState,
        to_state: ConnectionState,
        expected: bool,
    ) -> None:
        """Test specific state transitions."""
        assert is_valid_transition(from_state, to_state) == expected
