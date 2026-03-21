"""Extended tests for MessageBuffer covering Python fallback paths."""

from __future__ import annotations

import pytest

from wsfabric.buffer import BufferConfig, MessageBuffer, ReplayConfig


class TestMessageBufferPythonPaths:
    """Tests to cover MessageBuffer Python wrapper paths."""

    def test_push_and_pop(self) -> None:
        """Test push and pop."""
        buf = MessageBuffer(BufferConfig(capacity=10))
        for i in range(5):
            buf.push(f"msg-{i}")
        assert buf.pop() == "msg-0"
        assert buf.pop() == "msg-1"

    def test_push_with_sequence_id(self) -> None:
        """Test push with sequence IDs."""
        buf = MessageBuffer(BufferConfig(capacity=10))
        buf.push("msg-0", sequence_id="seq-0")
        buf.push("msg-1", sequence_id="seq-1")
        assert buf.last_sequence_id == "seq-1"

    def test_overflow_drop_oldest(self) -> None:
        """Test drop_oldest overflow policy."""
        buf = MessageBuffer(BufferConfig(capacity=3, overflow_policy="drop_oldest"))
        for i in range(5):
            buf.push(i)
        assert buf.fill_ratio > 0

    def test_overflow_drop_newest(self) -> None:
        """Test drop_newest overflow policy."""
        buf = MessageBuffer(BufferConfig(capacity=3, overflow_policy="drop_newest"))
        for i in range(5):
            buf.push(i)
        assert buf.pop() == 0  # First item kept

    def test_dedup_enabled(self) -> None:
        """Test deduplication."""
        buf = MessageBuffer(
            BufferConfig(capacity=10, enable_dedup=True, dedup_window=5)
        )
        buf.push("msg-a", sequence_id="id-1")
        assert buf.is_duplicate("id-1") is True
        assert buf.is_duplicate("id-2") is False

    def test_dedup_window_eviction(self) -> None:
        """Test dedup window evicts old entries."""
        buf = MessageBuffer(
            BufferConfig(capacity=100, enable_dedup=True, dedup_window=3)
        )
        buf.push("a", sequence_id="id-1")
        buf.push("b", sequence_id="id-2")
        buf.push("c", sequence_id="id-3")
        buf.push("d", sequence_id="id-4")  # Should evict id-1 from window
        assert buf.is_duplicate("id-1") is False  # Evicted

    def test_clear(self) -> None:
        """Test clearing the buffer."""
        buf = MessageBuffer(BufferConfig(capacity=10))
        for i in range(5):
            buf.push(i)
        buf.clear()
        assert buf.is_empty

    def test_clear_dedup(self) -> None:
        """Test clearing dedup window."""
        buf = MessageBuffer(
            BufferConfig(capacity=10, enable_dedup=True, dedup_window=5)
        )
        buf.push("a", sequence_id="id-1")
        assert buf.is_duplicate("id-1") is True
        buf.clear_dedup()
        assert buf.is_duplicate("id-1") is False

    def test_reset(self) -> None:
        """Test full reset."""
        buf = MessageBuffer(
            BufferConfig(capacity=10, enable_dedup=True, dedup_window=5)
        )
        buf.push("a", sequence_id="id-1")
        buf.reset()
        assert buf.is_empty
        assert buf.is_duplicate("id-1") is False

    def test_drain(self) -> None:
        """Test draining all messages."""
        buf = MessageBuffer(BufferConfig(capacity=10))
        for i in range(5):
            buf.push(f"msg-{i}")
        drained = buf.drain()
        assert len(drained) == 5
        assert buf.is_empty

    def test_drain_with_sequences(self) -> None:
        """Test draining with sequence IDs."""
        buf = MessageBuffer(BufferConfig(capacity=10))
        buf.push("a", sequence_id="s1")
        buf.push("b", sequence_id="s2")
        items = buf.drain_with_sequences()
        assert len(items) == 2
        assert items[0] == ("a", "s1")

    def test_properties(self) -> None:
        """Test buffer properties."""
        buf = MessageBuffer(BufferConfig(capacity=5))
        assert buf.capacity == 5
        assert buf.is_empty
        assert not buf.is_full
        buf.push("a")
        assert not buf.is_empty
        assert buf.fill_ratio == pytest.approx(0.2)

    def test_total_dropped(self) -> None:
        """Test dropped counter."""
        buf = MessageBuffer(BufferConfig(capacity=2, overflow_policy="drop_oldest"))
        for i in range(5):
            buf.push(i)
        assert buf.total_dropped == 3

    def test_default_config(self) -> None:
        """Test default BufferConfig."""
        buf = MessageBuffer()
        assert buf.capacity == 1000
        assert buf.is_empty


class TestReplayConfig:
    """Tests for ReplayConfig validation (via __post_init__)."""

    def test_valid_none_mode(self) -> None:
        """Test none mode is valid."""
        config = ReplayConfig(mode="none")
        assert config.mode == "none"

    def test_valid_full_buffer_mode(self) -> None:
        """Test full_buffer mode is valid."""
        config = ReplayConfig(mode="full_buffer")
        assert config.mode == "full_buffer"

    def test_sequence_id_requires_callback(self) -> None:
        """Test sequence_id mode requires on_replay."""
        with pytest.raises(ValueError, match=r"on_replay"):
            ReplayConfig(mode="sequence_id")

    def test_sequence_id_with_callback_valid(self) -> None:
        """Test sequence_id mode with callback is valid."""

        async def replay(last_seq: object) -> None:
            pass

        config = ReplayConfig(mode="sequence_id", on_replay=replay)
        assert config.on_replay is replay

    def test_invalid_mode(self) -> None:
        """Test invalid mode raises."""
        with pytest.raises(ValueError, match=r"[Ii]nvalid"):
            ReplayConfig(mode="invalid")
