"""Message buffering for WSFabric.

This module provides message buffering with sequence tracking, deduplication,
and replay support for WebSocket connections.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    TypeVar,
)

from wsfabric.exceptions import BufferOverflowError

if TYPE_CHECKING:
    pass

# Type variable for message type
T = TypeVar("T")

# Type aliases for sequence IDs
SequenceId = int | str

# Overflow policy type
OverflowPolicyType = Literal["drop_oldest", "drop_newest", "error"]

# Replay mode type
ReplayModeType = Literal["sequence_id", "full_buffer", "none"]


@dataclass(frozen=True, slots=True)
class BufferConfig:
    """Configuration for message buffering.

    Args:
        capacity: Maximum number of messages to buffer.
        overflow_policy: Policy when buffer is full.
            - 'drop_oldest': Remove oldest message (FIFO eviction).
            - 'drop_newest': Discard incoming message.
            - 'error': Raise BufferOverflowError.
        enable_dedup: Whether to deduplicate messages by sequence ID.
        dedup_window: Number of recent sequence IDs to track for deduplication.
    """

    capacity: int = 1000
    overflow_policy: OverflowPolicyType = "drop_oldest"
    enable_dedup: bool = False
    dedup_window: int = 100

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.capacity <= 0:
            msg = f"capacity must be positive, got {self.capacity}"
            raise ValueError(msg)
        if self.overflow_policy not in ("drop_oldest", "drop_newest", "error"):
            msg = f"Invalid overflow_policy: {self.overflow_policy}"
            raise ValueError(msg)
        if self.dedup_window <= 0:
            msg = f"dedup_window must be positive, got {self.dedup_window}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """Configuration for message replay on reconnection.

    Args:
        mode: Replay strategy.
            - 'none': No replay.
            - 'sequence_id': Call on_replay callback with last sequence ID.
            - 'full_buffer': Resend all buffered messages.
        sequence_extractor: Function to extract sequence ID from a message.
        on_replay: Async callback invoked with last sequence ID (for sequence_id mode).
    """

    mode: ReplayModeType = "none"
    sequence_extractor: Callable[[Any], SequenceId] | None = None
    on_replay: Callable[[SequenceId], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.mode not in ("none", "sequence_id", "full_buffer"):
            msg = f"Invalid replay mode: {self.mode}"
            raise ValueError(msg)
        if self.mode == "sequence_id" and self.on_replay is None:
            msg = "on_replay callback is required for sequence_id mode"
            raise ValueError(msg)


# Try to import Rust RingBuffer, fall back to pure Python
try:
    from wsfabric._core import RingBuffer as _RustRingBuffer

    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False


class _PythonRingBuffer(Generic[T]):
    """Pure-Python fallback for RingBuffer."""

    def __init__(self, capacity: int, policy: OverflowPolicyType) -> None:
        """Initialize the ring buffer.

        Args:
            capacity: Maximum number of items.
            policy: Overflow policy.
        """
        self._buffer: list[tuple[T, SequenceId | None] | None] = [None] * capacity
        self._head = 0
        self._tail = 0
        self._len = 0
        self._capacity = capacity
        self._policy = policy
        self._total_dropped = 0

    def push(self, item: T, sequence_id: SequenceId | None = None) -> bool:
        """Push an item onto the buffer.

        Args:
            item: The item to push.
            sequence_id: Optional sequence identifier.

        Returns:
            True if item was added, False if dropped.

        Raises:
            BufferOverflowError: If buffer is full and policy is 'error'.
        """
        if self._len == self._capacity:
            if self._policy == "drop_oldest":
                self._head = (self._head + 1) % self._capacity
                self._len -= 1
                self._total_dropped += 1
            elif self._policy == "drop_newest":
                self._total_dropped += 1
                return False
            else:  # error
                raise BufferOverflowError(
                    "Buffer is full",
                    capacity=self._capacity,
                    current_size=self._len,
                )

        self._buffer[self._tail] = (item, sequence_id)
        self._tail = (self._tail + 1) % self._capacity
        self._len += 1
        return True

    def pop(self) -> T | None:
        """Pop the oldest item from the buffer.

        Returns:
            The oldest item, or None if empty.
        """
        if self._len == 0:
            return None

        item_tuple = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) % self._capacity
        self._len -= 1

        return item_tuple[0] if item_tuple else None

    def drain(self) -> list[T]:
        """Drain all items from the buffer.

        Returns:
            List of items in FIFO order.
        """
        items: list[T] = []
        while self._len > 0:
            item = self.pop()
            if item is not None:
                items.append(item)
        return items

    def drain_with_sequences(self) -> list[tuple[T, SequenceId | None]]:
        """Drain all items with their sequence IDs.

        Returns:
            List of (item, sequence_id) tuples.
        """
        items: list[tuple[T, SequenceId | None]] = []
        while self._len > 0:
            item_tuple = self._buffer[self._head]
            self._buffer[self._head] = None
            self._head = (self._head + 1) % self._capacity
            self._len -= 1
            if item_tuple is not None:
                items.append(item_tuple)
        return items

    def clear(self) -> None:
        """Clear all items from the buffer."""
        for i in range(self._capacity):
            self._buffer[i] = None
        self._head = 0
        self._tail = 0
        self._len = 0

    @property
    def len(self) -> int:
        """Get the number of items in the buffer."""
        return self._len

    @property
    def capacity(self) -> int:
        """Get the buffer capacity."""
        return self._capacity

    @property
    def is_empty(self) -> bool:
        """Check if the buffer is empty."""
        return self._len == 0

    @property
    def is_full(self) -> bool:
        """Check if the buffer is full."""
        return self._len == self._capacity

    @property
    def fill_ratio(self) -> float:
        """Get the fill ratio (0.0 to 1.0)."""
        return self._len / self._capacity if self._capacity > 0 else 0.0

    @property
    def total_dropped(self) -> int:
        """Get the total number of dropped messages."""
        return self._total_dropped


class MessageBuffer(Generic[T]):
    """High-level message buffer with sequence tracking and deduplication.

    This class wraps the Rust RingBuffer (or Python fallback) and adds:
    - Sequence ID tracking for replay
    - Deduplication based on sequence IDs
    - Statistics and fill ratio monitoring

    Example:
        >>> config = BufferConfig(capacity=100, enable_dedup=True)
        >>> buffer: MessageBuffer[dict] = MessageBuffer(config)
        >>> buffer.push({"type": "trade", "id": 1}, sequence_id=1)
        True
        >>> buffer.push({"type": "trade", "id": 1}, sequence_id=1)  # Duplicate
        False
        >>> messages = buffer.drain()
        [{"type": "trade", "id": 1}]
    """

    def __init__(self, config: BufferConfig | None = None) -> None:
        """Initialize the message buffer.

        Args:
            config: Buffer configuration. Uses defaults if not provided.
        """
        self._config = config or BufferConfig()

        # Initialize the underlying ring buffer
        if _RUST_AVAILABLE:
            self._buffer: _RustRingBuffer | _PythonRingBuffer[T] = _RustRingBuffer(
                self._config.capacity, self._config.overflow_policy
            )
        else:
            self._buffer = _PythonRingBuffer[T](
                self._config.capacity, self._config.overflow_policy
            )

        # Track last sequence ID for replay
        self._last_sequence_id: SequenceId | None = None

        # Deduplication window (LRU-style)
        self._seen_sequences: OrderedDict[SequenceId, None] = OrderedDict()

    def push(
        self,
        message: T,
        sequence_id: SequenceId | None = None,
    ) -> bool:
        """Push a message to the buffer.

        Args:
            message: The message to buffer.
            sequence_id: Optional sequence identifier for replay/dedup.

        Returns:
            True if the message was added, False if:
            - It was a duplicate (dedup enabled)
            - Buffer is full and policy is drop_newest

        Raises:
            BufferOverflowError: If buffer is full and policy is 'error'.
        """
        # Check for duplicate
        if sequence_id is not None:
            if self._config.enable_dedup and self.is_duplicate(sequence_id):
                return False

            # Update last sequence ID
            self._last_sequence_id = sequence_id

            # Track sequence for deduplication
            if self._config.enable_dedup:
                self._track_sequence(sequence_id)

        # Push to buffer
        return self._buffer.push(message, sequence_id)

    def pop(self) -> T | None:
        """Pop the oldest message from the buffer.

        Returns:
            The oldest message, or None if the buffer is empty.
        """
        return self._buffer.pop()

    def drain(self) -> list[T]:
        """Drain all messages from the buffer.

        Returns:
            List of messages in FIFO order.
        """
        return self._buffer.drain()

    def drain_with_sequences(self) -> list[tuple[T, SequenceId | None]]:
        """Drain all messages with their sequence IDs.

        Returns:
            List of (message, sequence_id) tuples in FIFO order.
        """
        return self._buffer.drain_with_sequences()

    def is_duplicate(self, sequence_id: SequenceId) -> bool:
        """Check if a sequence ID has been seen recently.

        Args:
            sequence_id: The sequence ID to check.

        Returns:
            True if this is a duplicate within the dedup window.
        """
        return sequence_id in self._seen_sequences

    def _track_sequence(self, sequence_id: SequenceId) -> None:
        """Track a sequence ID for deduplication.

        Args:
            sequence_id: The sequence ID to track.
        """
        # Remove if already exists (to update LRU order)
        if sequence_id in self._seen_sequences:
            del self._seen_sequences[sequence_id]

        # Add to end
        self._seen_sequences[sequence_id] = None

        # Evict oldest if over window size
        while len(self._seen_sequences) > self._config.dedup_window:
            self._seen_sequences.popitem(last=False)

    def clear(self) -> None:
        """Clear all messages from the buffer."""
        self._buffer.clear()

    def clear_dedup(self) -> None:
        """Clear the deduplication window."""
        self._seen_sequences.clear()

    def reset(self) -> None:
        """Reset the buffer and deduplication state."""
        self.clear()
        self.clear_dedup()
        self._last_sequence_id = None

    @property
    def last_sequence_id(self) -> SequenceId | None:
        """Get the last tracked sequence ID."""
        return self._last_sequence_id

    @property
    def fill_ratio(self) -> float:
        """Get the buffer fill ratio (0.0 to 1.0)."""
        return self._buffer.fill_ratio

    @property
    def capacity(self) -> int:
        """Get the buffer capacity."""
        return self._buffer.capacity

    @property
    def is_empty(self) -> bool:
        """Check if the buffer is empty."""
        return self._buffer.is_empty

    @property
    def is_full(self) -> bool:
        """Check if the buffer is full."""
        return self._buffer.is_full

    @property
    def total_dropped(self) -> int:
        """Get the total number of dropped messages."""
        return self._buffer.total_dropped

    def __len__(self) -> int:
        """Get the number of messages in the buffer."""
        return self._buffer.len

    def __bool__(self) -> bool:
        """Return True if the buffer is not empty."""
        return not self._buffer.is_empty

    def __repr__(self) -> str:
        """Return a string representation of the buffer."""
        return (
            f"MessageBuffer(len={len(self)}, capacity={self.capacity}, "
            f"fill_ratio={self.fill_ratio:.2f}, dropped={self.total_dropped})"
        )
