"""Unit tests for the replay functionality."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from wsfabric.buffer import BufferConfig, ReplayConfig
from wsfabric.events import (
    BufferOverflowEvent,
    ReplayCompletedEvent,
    ReplayStartedEvent,
)
from wsfabric.manager import WebSocketManager


class TestReplayEvents:
    """Tests for replay event dataclasses."""

    def test_replay_started_event(self) -> None:
        """Test ReplayStartedEvent creation."""
        event = ReplayStartedEvent(
            mode="sequence_id",
            last_sequence_id=100,
            message_count=5,
        )
        assert event.mode == "sequence_id"
        assert event.last_sequence_id == 100
        assert event.message_count == 5

    def test_replay_started_event_with_string_id(self) -> None:
        """Test ReplayStartedEvent with string sequence ID."""
        event = ReplayStartedEvent(
            mode="full_buffer",
            last_sequence_id="seq-abc",
            message_count=10,
        )
        assert event.last_sequence_id == "seq-abc"

    def test_replay_started_event_no_sequence(self) -> None:
        """Test ReplayStartedEvent with no sequence ID."""
        event = ReplayStartedEvent(
            mode="none",
            last_sequence_id=None,
            message_count=0,
        )
        assert event.last_sequence_id is None

    def test_replay_completed_event(self) -> None:
        """Test ReplayCompletedEvent creation."""
        event = ReplayCompletedEvent(
            mode="full_buffer",
            replayed_count=10,
            duration_ms=50.5,
        )
        assert event.mode == "full_buffer"
        assert event.replayed_count == 10
        assert event.duration_ms == 50.5

    def test_buffer_overflow_event(self) -> None:
        """Test BufferOverflowEvent creation."""
        event = BufferOverflowEvent(
            capacity=100,
            dropped_count=5,
            policy="drop_oldest",
        )
        assert event.capacity == 100
        assert event.dropped_count == 5
        assert event.policy == "drop_oldest"


class TestWebSocketManagerBuffer:
    """Tests for WebSocketManager buffer integration."""

    def test_manager_without_buffer(self) -> None:
        """Test manager without buffer configuration."""
        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080"
        )
        assert manager.buffer is None
        assert manager.buffer_fill_ratio == 0.0

    def test_manager_with_buffer(self) -> None:
        """Test manager with buffer configuration."""
        config = BufferConfig(capacity=100)
        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=config,
        )
        assert manager.buffer is not None
        assert manager.buffer.capacity == 100
        assert manager.buffer_fill_ratio == 0.0

    def test_manager_with_buffer_and_replay(self) -> None:
        """Test manager with buffer and replay configuration."""

        async def replay_callback(seq_id: int | str) -> None:
            pass

        buffer_config = BufferConfig(capacity=50)
        replay_config = ReplayConfig(mode="sequence_id", on_replay=replay_callback)

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        assert manager.buffer is not None
        assert manager._replay_config is not None
        assert manager._replay_config.mode == "sequence_id"


class TestReplayOnReconnect:
    """Tests for replay on reconnect behavior."""

    @pytest.mark.asyncio
    async def test_replay_sequence_id_mode(self) -> None:
        """Test replay with sequence_id mode."""
        replay_called = False
        called_with: int | str | None = None

        async def replay_callback(seq_id: int | str) -> None:
            nonlocal replay_called, called_with
            replay_called = True
            called_with = seq_id

        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(mode="sequence_id", on_replay=replay_callback)

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        # Simulate having received a message with sequence ID
        # NOTE: Use 'is not None' because empty buffer is falsy
        if manager.buffer is not None:
            manager.buffer.push({"data": "test"}, sequence_id=42)

        # Capture emitted events
        events: list[ReplayStartedEvent | ReplayCompletedEvent] = []

        @manager.on("replay_started")
        async def on_started(event: ReplayStartedEvent) -> None:
            events.append(event)

        @manager.on("replay_completed")
        async def on_completed(event: ReplayCompletedEvent) -> None:
            events.append(event)

        # Call replay method directly
        await manager._replay_on_reconnect()

        # Verify callback was called with correct sequence ID
        assert replay_called
        assert called_with == 42

        # Verify events were emitted
        assert len(events) == 2
        started = events[0]
        assert isinstance(started, ReplayStartedEvent)
        assert started.mode == "sequence_id"
        assert started.last_sequence_id == 42

        completed = events[1]
        assert isinstance(completed, ReplayCompletedEvent)
        assert completed.mode == "sequence_id"
        assert completed.replayed_count == 1

    @pytest.mark.asyncio
    async def test_replay_full_buffer_mode(self) -> None:
        """Test replay with full_buffer mode."""
        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(mode="full_buffer")

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        # Add messages to buffer
        # NOTE: Use 'is not None' because empty buffer is falsy
        if manager.buffer is not None:
            manager.buffer.push({"type": "msg1"})
            manager.buffer.push({"type": "msg2"})
            manager.buffer.push({"type": "msg3"})

        # Mock the send method
        sent_messages: list[dict[str, Any]] = []

        async def mock_send(data: Any) -> None:
            sent_messages.append(data)

        manager.send = mock_send  # type: ignore[method-assign]

        # Capture events
        events: list[ReplayCompletedEvent] = []

        @manager.on("replay_completed")
        async def on_completed(event: ReplayCompletedEvent) -> None:
            events.append(event)

        # Call replay
        await manager._replay_on_reconnect()

        # Verify messages were sent
        assert len(sent_messages) == 3
        assert sent_messages[0] == {"type": "msg1"}
        assert sent_messages[1] == {"type": "msg2"}
        assert sent_messages[2] == {"type": "msg3"}

        # Verify buffer is empty after replay
        assert manager.buffer is not None
        assert manager.buffer.is_empty

        # Verify event
        assert len(events) == 1
        assert events[0].replayed_count == 3

    @pytest.mark.asyncio
    async def test_replay_none_mode(self) -> None:
        """Test that replay does nothing when mode is none."""
        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(mode="none")

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        events_emitted = False

        @manager.on("replay_started")
        async def on_started(event: ReplayStartedEvent) -> None:
            nonlocal events_emitted
            events_emitted = True

        await manager._replay_on_reconnect()

        # No events should be emitted
        assert not events_emitted

    @pytest.mark.asyncio
    async def test_replay_without_config(self) -> None:
        """Test replay with no replay configuration."""
        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080"
        )

        events_emitted = False

        @manager.on("replay_started")
        async def on_started(event: ReplayStartedEvent) -> None:
            nonlocal events_emitted
            events_emitted = True

        await manager._replay_on_reconnect()

        # No events should be emitted
        assert not events_emitted

    @pytest.mark.asyncio
    async def test_replay_error_handling(self) -> None:
        """Test that replay handles errors gracefully."""

        async def failing_callback(seq_id: int | str) -> None:
            raise RuntimeError("Replay failed")

        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(mode="sequence_id", on_replay=failing_callback)

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        # NOTE: Use 'is not None' because empty buffer is falsy
        if manager.buffer is not None:
            manager.buffer.push({"data": "test"}, sequence_id=1)

        error_events: list[Any] = []

        @manager.on("error")
        async def on_error(event: Any) -> None:
            error_events.append(event)

        # Should not raise, errors are caught
        await manager._replay_on_reconnect()

        # Error event should be emitted
        assert len(error_events) == 1
        assert isinstance(error_events[0].error, RuntimeError)


class TestTrackReceivedMessage:
    """Tests for message tracking functionality."""

    @pytest.mark.asyncio
    async def test_track_message_with_sequence_extractor(self) -> None:
        """Test tracking message with sequence extractor."""

        def extract_seq(msg: dict[str, Any]) -> int:
            return msg.get("seq", 0)

        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(
            mode="sequence_id",
            sequence_extractor=extract_seq,
            on_replay=AsyncMock(),
        )

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        # Track a message
        await manager._track_received_message({"seq": 42, "data": "test"})

        assert manager.buffer is not None
        assert manager.buffer.last_sequence_id == 42
        assert len(manager.buffer) == 1

    @pytest.mark.asyncio
    async def test_track_message_without_extractor(self) -> None:
        """Test tracking message without sequence extractor."""
        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(mode="full_buffer")

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        await manager._track_received_message({"data": "test"})

        assert manager.buffer is not None
        assert manager.buffer.last_sequence_id is None
        assert len(manager.buffer) == 1

    @pytest.mark.asyncio
    async def test_track_message_without_buffer(self) -> None:
        """Test that tracking does nothing without buffer."""
        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080"
        )

        # Should not raise
        await manager._track_received_message({"data": "test"})

    @pytest.mark.asyncio
    async def test_buffer_overflow_event(self) -> None:
        """Test buffer overflow event emission."""
        buffer_config = BufferConfig(capacity=2, overflow_policy="drop_oldest")
        replay_config = ReplayConfig(mode="full_buffer")

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        overflow_events: list[BufferOverflowEvent] = []

        @manager.on("buffer_overflow")
        async def on_overflow(event: BufferOverflowEvent) -> None:
            overflow_events.append(event)

        # Fill buffer
        await manager._track_received_message({"data": 1})
        await manager._track_received_message({"data": 2})

        # No overflow yet
        assert len(overflow_events) == 0

        # This should trigger overflow
        await manager._track_received_message({"data": 3})

        assert len(overflow_events) == 1
        assert overflow_events[0].capacity == 2
        assert overflow_events[0].policy == "drop_oldest"

    @pytest.mark.asyncio
    async def test_sequence_extractor_error_handling(self) -> None:
        """Test that extractor errors are ignored."""

        def failing_extractor(msg: dict[str, Any]) -> int:
            raise ValueError("Extraction failed")

        buffer_config = BufferConfig(capacity=100)
        replay_config = ReplayConfig(
            mode="sequence_id",
            sequence_extractor=failing_extractor,
            on_replay=AsyncMock(),
        )

        manager: WebSocketManager[dict[str, Any]] = WebSocketManager(
            "ws://localhost:8080",
            buffer=buffer_config,
            replay=replay_config,
        )

        # Should not raise, errors are ignored
        await manager._track_received_message({"data": "test"})

        # Message should still be buffered
        assert manager.buffer is not None
        assert len(manager.buffer) == 1
        # But sequence ID should be None due to extractor failure
        assert manager.buffer.last_sequence_id is None
