"""Tests for the pure-Python _PythonRingBuffer in buffer.py.

Forces the Python fallback path by testing _PythonRingBuffer directly.
"""

from __future__ import annotations

import pytest

from wsfabric.buffer import _PythonRingBuffer


class TestPythonRingBuffer:
    """Tests for _PythonRingBuffer covering buffer.py lines 109-238."""

    def test_basic_push_pop(self) -> None:
        """Test basic push and pop."""
        buf = _PythonRingBuffer(5, "drop_oldest")
        assert buf.push("a") is True
        assert buf.push("b") is True
        assert buf.pop() == "a"
        assert buf.pop() == "b"
        assert buf.pop() is None

    def test_drop_oldest(self) -> None:
        """Test drop_oldest overflow."""
        buf = _PythonRingBuffer(3, "drop_oldest")
        for i in range(5):
            buf.push(i)
        assert buf.len == 3
        assert buf.pop() == 2
        assert buf.total_dropped == 2

    def test_drop_newest(self) -> None:
        """Test drop_newest overflow."""
        buf = _PythonRingBuffer(3, "drop_newest")
        for i in range(5):
            buf.push(i)
        assert buf.len == 3
        assert buf.pop() == 0
        assert buf.total_dropped == 2

    def test_error_policy(self) -> None:
        """Test error overflow policy."""
        buf = _PythonRingBuffer(2, "error")
        buf.push("a")
        buf.push("b")
        with pytest.raises(Exception):
            buf.push("c")

    def test_push_with_sequence(self) -> None:
        """Test push with sequence ID."""
        buf = _PythonRingBuffer(5, "drop_oldest")
        buf.push("msg", sequence_id="seq-1")
        items = buf.drain_with_sequences()
        assert items[0] == ("msg", "seq-1")

    def test_drain(self) -> None:
        """Test drain returns all items in order."""
        buf = _PythonRingBuffer(10, "drop_oldest")
        for i in range(5):
            buf.push(i)
        items = buf.drain()
        assert items == [0, 1, 2, 3, 4]
        assert buf.len == 0

    def test_drain_with_sequences(self) -> None:
        """Test drain_with_sequences returns items with seq IDs."""
        buf = _PythonRingBuffer(10, "drop_oldest")
        buf.push("a", "s1")
        buf.push("b", None)
        buf.push("c", "s3")
        items = buf.drain_with_sequences()
        assert items == [("a", "s1"), ("b", None), ("c", "s3")]

    def test_clear(self) -> None:
        """Test clear empties buffer."""
        buf = _PythonRingBuffer(5, "drop_oldest")
        for i in range(5):
            buf.push(i)
        buf.clear()
        assert buf.len == 0
        assert buf.is_empty

    def test_properties(self) -> None:
        """Test all properties."""
        buf = _PythonRingBuffer(10, "drop_oldest")
        assert buf.capacity == 10
        assert buf.is_empty is True
        assert buf.is_full is False
        assert buf.fill_ratio == 0.0
        assert buf.total_dropped == 0

        for i in range(10):
            buf.push(i)
        assert buf.is_full is True
        assert buf.fill_ratio == 1.0

    def test_dropped_counter(self) -> None:
        """Test dropped counter tracks dropped items."""
        buf = _PythonRingBuffer(2, "drop_oldest")
        for i in range(5):
            buf.push(i)
        assert buf.total_dropped == 3

    def test_len_property(self) -> None:
        """Test len property."""
        buf = _PythonRingBuffer(5, "drop_oldest")
        assert buf.len == 0
        buf.push("x")
        assert buf.len == 1

    def test_wraparound(self) -> None:
        """Test circular buffer wraparound correctness."""
        buf = _PythonRingBuffer(3, "drop_oldest")
        buf.push(1)
        buf.push(2)
        buf.push(3)
        buf.pop()
        buf.push(4)
        assert buf.drain() == [2, 3, 4]

    def test_fill_drain_cycles(self) -> None:
        """Test repeated fill/drain cycles."""
        buf = _PythonRingBuffer(5, "drop_oldest")
        for _ in range(10):
            for j in range(5):
                buf.push(j)
            items = buf.drain()
            assert items == [0, 1, 2, 3, 4]

    def test_drop_oldest_preserves_order(self) -> None:
        """Test drop_oldest preserves FIFO order."""
        buf = _PythonRingBuffer(3, "drop_oldest")
        for i in range(10):
            buf.push(i)
        assert buf.drain() == [7, 8, 9]

    def test_drop_newest_returns_false(self) -> None:
        """Test drop_newest push returns False when dropping."""
        buf = _PythonRingBuffer(2, "drop_newest")
        assert buf.push("a") is True
        assert buf.push("b") is True
        assert buf.push("c") is False  # Dropped
