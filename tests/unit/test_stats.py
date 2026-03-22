"""Tests for connection statistics."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from jetsocket.state import ConnectionState
from jetsocket.stats import ConnectionStats, _MutableStats


class TestConnectionStats:
    """Tests for ConnectionStats dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        stats = ConnectionStats(
            state=ConnectionState.CONNECTED,
            uptime_seconds=123.45,
            messages_sent=100,
            messages_received=200,
            bytes_sent=1024,
            bytes_received=2048,
            reconnect_count=2,
            last_reconnect_at=datetime.now(timezone.utc),
            latency_ms=15.5,
            latency_avg_ms=20.0,
            last_message_at=datetime.now(timezone.utc),
            connection_age_seconds=3600.0,
            errors=5,
        )
        assert stats.state == ConnectionState.CONNECTED
        assert stats.uptime_seconds == 123.45
        assert stats.messages_sent == 100
        assert stats.messages_received == 200
        assert stats.bytes_sent == 1024
        assert stats.bytes_received == 2048
        assert stats.reconnect_count == 2
        assert stats.latency_ms == 15.5
        assert stats.latency_avg_ms == 20.0
        assert stats.connection_age_seconds == 3600.0
        assert stats.errors == 5

    def test_immutability(self) -> None:
        """Test that the dataclass is frozen."""
        stats = ConnectionStats(
            state=ConnectionState.IDLE,
            uptime_seconds=0,
            messages_sent=0,
            messages_received=0,
            bytes_sent=0,
            bytes_received=0,
            reconnect_count=0,
            last_reconnect_at=None,
            latency_ms=None,
            latency_avg_ms=None,
            last_message_at=None,
            connection_age_seconds=0,
            errors=0,
        )
        with pytest.raises(AttributeError):
            stats.messages_sent = 10  # type: ignore[misc]

    def test_optional_fields(self) -> None:
        """Test optional fields can be None."""
        stats = ConnectionStats(
            state=ConnectionState.IDLE,
            uptime_seconds=0,
            messages_sent=0,
            messages_received=0,
            bytes_sent=0,
            bytes_received=0,
            reconnect_count=0,
            last_reconnect_at=None,
            latency_ms=None,
            latency_avg_ms=None,
            last_message_at=None,
            connection_age_seconds=0,
            errors=0,
        )
        assert stats.last_reconnect_at is None
        assert stats.latency_ms is None
        assert stats.latency_avg_ms is None
        assert stats.last_message_at is None


class TestMutableStats:
    """Tests for _MutableStats internal class."""

    def test_default_state(self) -> None:
        """Test default state is IDLE."""
        stats = _MutableStats()
        assert stats.state == ConnectionState.IDLE

    def test_set_state(self) -> None:
        """Test setting state."""
        stats = _MutableStats()
        stats.state = ConnectionState.CONNECTING
        assert stats.state == ConnectionState.CONNECTING

    def test_initial_counters(self) -> None:
        """Test initial counter values."""
        stats = _MutableStats()
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.bytes_sent == 0
        assert stats.bytes_received == 0
        assert stats.reconnect_count == 0
        assert stats.errors == 0

    def test_mark_connected(self) -> None:
        """Test marking connection as established."""
        stats = _MutableStats()

        stats.mark_connected()
        snapshot = stats.snapshot()

        # Uptime should be very small but positive
        assert snapshot.uptime_seconds >= 0
        assert snapshot.connection_age_seconds >= 0

    def test_mark_disconnected(self) -> None:
        """Test marking connection as disconnected."""
        stats = _MutableStats()
        stats.mark_connected()
        time.sleep(0.01)
        stats.mark_disconnected()

        snapshot = stats.snapshot()
        assert snapshot.uptime_seconds == 0.0

    def test_mark_reconnected(self) -> None:
        """Test marking reconnection."""
        stats = _MutableStats()
        stats.mark_connected()
        stats.mark_disconnected()

        before = datetime.now(timezone.utc)
        stats.mark_reconnected()
        after = datetime.now(timezone.utc)

        assert stats.reconnect_count == 1
        assert stats._last_reconnect_at is not None
        assert before <= stats._last_reconnect_at <= after

    def test_record_message_sent(self) -> None:
        """Test recording sent messages."""
        stats = _MutableStats()

        before = datetime.now(timezone.utc)
        stats.record_message_sent(100)
        after = datetime.now(timezone.utc)

        assert stats.messages_sent == 1
        assert stats.bytes_sent == 100
        assert stats._last_message_at is not None
        assert before <= stats._last_message_at <= after

    def test_record_message_received(self) -> None:
        """Test recording received messages."""
        stats = _MutableStats()

        before = datetime.now(timezone.utc)
        stats.record_message_received(200)
        after = datetime.now(timezone.utc)

        assert stats.messages_received == 1
        assert stats.bytes_received == 200
        assert stats._last_message_at is not None
        assert before <= stats._last_message_at <= after

    def test_record_multiple_messages(self) -> None:
        """Test recording multiple messages."""
        stats = _MutableStats()

        stats.record_message_sent(100)
        stats.record_message_sent(150)
        stats.record_message_received(200)
        stats.record_message_received(300)
        stats.record_message_received(50)

        assert stats.messages_sent == 2
        assert stats.bytes_sent == 250
        assert stats.messages_received == 3
        assert stats.bytes_received == 550

    def test_record_error(self) -> None:
        """Test recording errors."""
        stats = _MutableStats()

        stats.record_error()
        stats.record_error()
        stats.record_error()

        assert stats.errors == 3

    def test_update_latency(self) -> None:
        """Test updating latency measurements."""
        stats = _MutableStats()

        stats.update_latency(15.5, 18.2)

        snapshot = stats.snapshot()
        assert snapshot.latency_ms == 15.5
        assert snapshot.latency_avg_ms == 18.2

    def test_reset(self) -> None:
        """Test resetting all statistics."""
        stats = _MutableStats()

        # Set some values
        stats.state = ConnectionState.CONNECTED
        stats.mark_connected()
        stats.record_message_sent(100)
        stats.record_message_received(200)
        stats.record_error()
        stats.mark_reconnected()
        stats.update_latency(10.0, 12.0)

        # Reset
        stats.reset()

        # State should not be reset (it's separate)
        assert stats.state == ConnectionState.CONNECTED

        # Counters should be reset
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.bytes_sent == 0
        assert stats.bytes_received == 0
        assert stats.reconnect_count == 0
        assert stats.errors == 0
        assert stats._connected_at is None
        assert stats._first_connect_at is None
        assert stats._last_reconnect_at is None
        assert stats._last_message_at is None
        assert stats._latency_ms is None
        assert stats._latency_avg_ms is None


class TestMutableStatsSnapshot:
    """Tests for _MutableStats.snapshot() method."""

    def test_snapshot_idle(self) -> None:
        """Test snapshot of idle connection."""
        stats = _MutableStats()
        snapshot = stats.snapshot()

        assert snapshot.state == ConnectionState.IDLE
        assert snapshot.uptime_seconds == 0.0
        assert snapshot.connection_age_seconds == 0.0
        assert snapshot.messages_sent == 0
        assert snapshot.messages_received == 0

    def test_snapshot_connected(self) -> None:
        """Test snapshot of connected session."""
        stats = _MutableStats()
        stats.state = ConnectionState.CONNECTED
        stats.mark_connected()
        time.sleep(0.1)

        snapshot = stats.snapshot()

        assert snapshot.state == ConnectionState.CONNECTED
        assert snapshot.uptime_seconds >= 0.05
        assert snapshot.connection_age_seconds >= 0.05

    def test_snapshot_after_messages(self) -> None:
        """Test snapshot reflects message counts."""
        stats = _MutableStats()
        stats.record_message_sent(100)
        stats.record_message_sent(200)
        stats.record_message_received(500)

        snapshot = stats.snapshot()

        assert snapshot.messages_sent == 2
        assert snapshot.bytes_sent == 300
        assert snapshot.messages_received == 1
        assert snapshot.bytes_received == 500

    def test_snapshot_preserves_timestamps(self) -> None:
        """Test that timestamps are included in snapshot."""
        stats = _MutableStats()
        stats.mark_reconnected()
        stats.record_message_sent(100)

        snapshot = stats.snapshot()

        assert snapshot.last_reconnect_at is not None
        assert snapshot.last_message_at is not None

    def test_snapshot_is_immutable(self) -> None:
        """Test that snapshot creates independent copy."""
        stats = _MutableStats()
        stats.record_message_sent(100)

        snapshot1 = stats.snapshot()

        stats.record_message_sent(200)
        snapshot2 = stats.snapshot()

        # First snapshot should not change
        assert snapshot1.messages_sent == 1
        assert snapshot1.bytes_sent == 100

        # Second snapshot reflects new state
        assert snapshot2.messages_sent == 2
        assert snapshot2.bytes_sent == 300

    def test_uptime_only_when_connected(self) -> None:
        """Test uptime is 0 when disconnected."""
        stats = _MutableStats()
        stats.mark_connected()
        time.sleep(0.02)

        # Check uptime while connected
        snapshot1 = stats.snapshot()
        assert snapshot1.uptime_seconds > 0

        # Disconnect
        stats.mark_disconnected()
        snapshot2 = stats.snapshot()
        assert snapshot2.uptime_seconds == 0.0

        # But connection age should still be tracked
        assert snapshot2.connection_age_seconds > 0

    def test_connection_age_persists_across_reconnects(self) -> None:
        """Test connection age tracks total time."""
        stats = _MutableStats()

        # First connection
        stats.mark_connected()
        time.sleep(0.05)
        stats.mark_disconnected()

        # Reconnect
        stats.mark_reconnected()
        time.sleep(0.05)

        snapshot = stats.snapshot()

        # Connection age should include both periods
        assert snapshot.connection_age_seconds >= 0.04
