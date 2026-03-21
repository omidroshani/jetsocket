"""Unit tests for the message buffer module."""

from __future__ import annotations

import pytest

from wsfabric.buffer import BufferConfig, MessageBuffer, ReplayConfig
from wsfabric.exceptions import BufferOverflowError


class TestBufferConfig:
    """Tests for BufferConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BufferConfig()
        assert config.capacity == 1000
        assert config.overflow_policy == "drop_oldest"
        assert config.enable_dedup is False
        assert config.dedup_window == 100

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = BufferConfig(
            capacity=500,
            overflow_policy="drop_newest",
            enable_dedup=True,
            dedup_window=50,
        )
        assert config.capacity == 500
        assert config.overflow_policy == "drop_newest"
        assert config.enable_dedup is True
        assert config.dedup_window == 50

    def test_invalid_capacity(self) -> None:
        """Test that invalid capacity raises ValueError."""
        with pytest.raises(ValueError, match="capacity must be positive"):
            BufferConfig(capacity=0)

        with pytest.raises(ValueError, match="capacity must be positive"):
            BufferConfig(capacity=-1)

    def test_invalid_overflow_policy(self) -> None:
        """Test that invalid overflow policy raises ValueError."""
        with pytest.raises(ValueError, match="Invalid overflow_policy"):
            BufferConfig(overflow_policy="invalid")  # type: ignore[arg-type]

    def test_invalid_dedup_window(self) -> None:
        """Test that invalid dedup_window raises ValueError."""
        with pytest.raises(ValueError, match="dedup_window must be positive"):
            BufferConfig(dedup_window=0)


class TestReplayConfig:
    """Tests for ReplayConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ReplayConfig()
        assert config.mode == "none"
        assert config.sequence_extractor is None
        assert config.on_replay is None

    def test_sequence_id_mode_requires_callback(self) -> None:
        """Test that sequence_id mode requires on_replay callback."""
        with pytest.raises(ValueError, match="on_replay callback is required"):
            ReplayConfig(mode="sequence_id")

    def test_sequence_id_mode_with_callback(self) -> None:
        """Test sequence_id mode with proper callback."""

        async def callback(seq_id: int | str) -> None:
            pass

        config = ReplayConfig(mode="sequence_id", on_replay=callback)
        assert config.mode == "sequence_id"
        assert config.on_replay is callback

    def test_full_buffer_mode(self) -> None:
        """Test full_buffer mode configuration."""
        config = ReplayConfig(mode="full_buffer")
        assert config.mode == "full_buffer"

    def test_invalid_mode(self) -> None:
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid replay mode"):
            ReplayConfig(mode="invalid")  # type: ignore[arg-type]


class TestMessageBuffer:
    """Tests for MessageBuffer class."""

    def test_create_empty_buffer(self) -> None:
        """Test creating an empty buffer."""
        buffer: MessageBuffer[str] = MessageBuffer()
        assert len(buffer) == 0
        assert buffer.is_empty
        assert not buffer.is_full
        assert buffer.capacity == 1000
        assert buffer.fill_ratio == 0.0

    def test_create_with_config(self) -> None:
        """Test creating buffer with custom config."""
        config = BufferConfig(capacity=50)
        buffer: MessageBuffer[str] = MessageBuffer(config)
        assert buffer.capacity == 50

    def test_push_and_pop(self) -> None:
        """Test basic push and pop operations."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        buffer.push("message1")
        buffer.push("message2")
        buffer.push("message3")

        assert len(buffer) == 3
        assert buffer.pop() == "message1"
        assert buffer.pop() == "message2"
        assert buffer.pop() == "message3"
        assert buffer.pop() is None

    def test_drain(self) -> None:
        """Test draining all messages from buffer."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        buffer.push("a")
        buffer.push("b")
        buffer.push("c")

        messages = buffer.drain()
        assert messages == ["a", "b", "c"]
        assert len(buffer) == 0
        assert buffer.is_empty

    def test_drain_with_sequences(self) -> None:
        """Test draining messages with sequence IDs."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        buffer.push("msg1", sequence_id=1)
        buffer.push("msg2", sequence_id=2)
        buffer.push("msg3")

        items = buffer.drain_with_sequences()
        assert len(items) == 3
        assert items[0] == ("msg1", 1)
        assert items[1] == ("msg2", 2)
        assert items[2][0] == "msg3"
        assert items[2][1] is None

    def test_sequence_tracking(self) -> None:
        """Test sequence ID tracking."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        assert buffer.last_sequence_id is None

        buffer.push("msg1", sequence_id=100)
        assert buffer.last_sequence_id == 100

        buffer.push("msg2", sequence_id=200)
        assert buffer.last_sequence_id == 200

        buffer.push("msg3")  # No sequence ID
        assert buffer.last_sequence_id == 200  # Unchanged

    def test_deduplication(self) -> None:
        """Test message deduplication."""
        config = BufferConfig(capacity=10, enable_dedup=True, dedup_window=5)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        # First message should be added
        assert buffer.push("msg1", sequence_id=1) is True
        assert len(buffer) == 1

        # Duplicate should be rejected
        assert buffer.push("msg1_dup", sequence_id=1) is False
        assert len(buffer) == 1

        # Different sequence ID should be added
        assert buffer.push("msg2", sequence_id=2) is True
        assert len(buffer) == 2

    def test_dedup_window_eviction(self) -> None:
        """Test that old sequence IDs are evicted from dedup window."""
        config = BufferConfig(capacity=100, enable_dedup=True, dedup_window=3)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        # Add messages with sequence IDs 1, 2, 3
        buffer.push("msg1", sequence_id=1)
        buffer.push("msg2", sequence_id=2)
        buffer.push("msg3", sequence_id=3)

        # Sequence 1 should still be in window
        assert buffer.is_duplicate(1)

        # Add more messages to evict sequence 1
        buffer.push("msg4", sequence_id=4)

        # Now sequence 1 should be evicted
        assert not buffer.is_duplicate(1)
        assert buffer.is_duplicate(2)
        assert buffer.is_duplicate(3)
        assert buffer.is_duplicate(4)

    def test_drop_oldest_policy(self) -> None:
        """Test drop_oldest overflow policy."""
        config = BufferConfig(capacity=3, overflow_policy="drop_oldest")
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("a")
        buffer.push("b")
        buffer.push("c")
        assert len(buffer) == 3

        buffer.push("d")  # Should drop 'a'
        assert len(buffer) == 3
        assert buffer.total_dropped == 1

        messages = buffer.drain()
        assert messages == ["b", "c", "d"]

    def test_drop_newest_policy(self) -> None:
        """Test drop_newest overflow policy."""
        config = BufferConfig(capacity=3, overflow_policy="drop_newest")
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("a")
        buffer.push("b")
        buffer.push("c")
        assert len(buffer) == 3

        result = buffer.push("d")  # Should be rejected
        assert result is False
        assert len(buffer) == 3
        assert buffer.total_dropped == 1

        messages = buffer.drain()
        assert messages == ["a", "b", "c"]

    def test_error_policy(self) -> None:
        """Test error overflow policy."""
        config = BufferConfig(capacity=2, overflow_policy="error")
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("a")
        buffer.push("b")

        with pytest.raises(BufferOverflowError) as exc_info:
            buffer.push("c")

        assert exc_info.value.capacity == 2
        assert exc_info.value.current_size == 2

    def test_fill_ratio(self) -> None:
        """Test fill ratio calculation."""
        config = BufferConfig(capacity=10)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        assert buffer.fill_ratio == 0.0

        buffer.push("a")
        assert buffer.fill_ratio == 0.1

        for i in range(9):
            buffer.push(f"msg{i}")
        assert buffer.fill_ratio == 1.0
        assert buffer.is_full

    def test_clear(self) -> None:
        """Test clearing the buffer."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        buffer.push("a")
        buffer.push("b")
        buffer.push("c")
        assert len(buffer) == 3

        buffer.clear()
        assert len(buffer) == 0
        assert buffer.is_empty

    def test_clear_dedup(self) -> None:
        """Test clearing the dedup window."""
        config = BufferConfig(capacity=10, enable_dedup=True)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("msg1", sequence_id=1)
        assert buffer.is_duplicate(1)

        buffer.clear_dedup()
        assert not buffer.is_duplicate(1)

    def test_reset(self) -> None:
        """Test full reset of buffer state."""
        config = BufferConfig(capacity=10, enable_dedup=True)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("msg1", sequence_id=1)
        assert len(buffer) == 1
        assert buffer.last_sequence_id == 1
        assert buffer.is_duplicate(1)

        buffer.reset()
        assert len(buffer) == 0
        assert buffer.last_sequence_id is None
        assert not buffer.is_duplicate(1)

    def test_bool_conversion(self) -> None:
        """Test boolean conversion."""
        buffer: MessageBuffer[str] = MessageBuffer(BufferConfig(capacity=10))

        assert not buffer  # Empty buffer is falsy

        buffer.push("msg")
        assert buffer  # Non-empty buffer is truthy

    def test_repr(self) -> None:
        """Test string representation."""
        config = BufferConfig(capacity=100)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("a")
        buffer.push("b")

        repr_str = repr(buffer)
        assert "MessageBuffer" in repr_str
        assert "len=2" in repr_str
        assert "capacity=100" in repr_str

    def test_generic_types(self) -> None:
        """Test buffer with various generic types."""
        # Dict buffer
        dict_buffer: MessageBuffer[dict[str, int]] = MessageBuffer()
        dict_buffer.push({"count": 1})
        assert dict_buffer.pop() == {"count": 1}

        # List buffer
        list_buffer: MessageBuffer[list[int]] = MessageBuffer()
        list_buffer.push([1, 2, 3])
        assert list_buffer.pop() == [1, 2, 3]

        # Custom object buffer
        class Event:
            def __init__(self, name: str) -> None:
                self.name = name

        event_buffer: MessageBuffer[Event] = MessageBuffer()
        event = Event("test")
        event_buffer.push(event)
        assert event_buffer.pop() is event


class TestMessageBufferWithStringSequence:
    """Tests for MessageBuffer with string sequence IDs."""

    def test_string_sequence_ids(self) -> None:
        """Test using string sequence IDs."""
        config = BufferConfig(capacity=10, enable_dedup=True)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("msg1", sequence_id="seq-001")
        buffer.push("msg2", sequence_id="seq-002")

        assert buffer.last_sequence_id == "seq-002"
        assert buffer.is_duplicate("seq-001")
        assert buffer.is_duplicate("seq-002")
        assert not buffer.is_duplicate("seq-003")

    def test_mixed_sequence_id_types(self) -> None:
        """Test mixing int and string sequence IDs."""
        config = BufferConfig(capacity=10, enable_dedup=True)
        buffer: MessageBuffer[str] = MessageBuffer(config)

        buffer.push("msg1", sequence_id=1)
        buffer.push("msg2", sequence_id="abc")
        buffer.push("msg3", sequence_id=2)

        assert buffer.last_sequence_id == 2
        assert buffer.is_duplicate(1)
        assert buffer.is_duplicate("abc")
        assert buffer.is_duplicate(2)
