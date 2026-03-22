"""Exponential backoff strategy for reconnection.

This module implements exponential backoff with jitter, following AWS
recommendations for preventing thundering herd problems.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    """Configuration for exponential backoff.

    Attributes:
        base: Initial delay in seconds.
        multiplier: Exponential multiplier applied each attempt.
        cap: Maximum delay in seconds.
        jitter: Whether to add random jitter (recommended).
        max_attempts: Maximum number of retry attempts (0 = infinite).
        reset_after: Reset attempt counter after this many seconds connected.
    """

    base: float = 1.0
    multiplier: float = 2.0
    cap: float = 60.0
    jitter: bool = True
    max_attempts: int = 0
    reset_after: float = 60.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.base <= 0:
            msg = "base must be positive"
            raise ValueError(msg)
        if self.multiplier < 1:
            msg = "multiplier must be >= 1"
            raise ValueError(msg)
        if self.cap < self.base:
            msg = "cap must be >= base"
            raise ValueError(msg)
        if self.max_attempts < 0:
            msg = "max_attempts must be >= 0"
            raise ValueError(msg)
        if self.reset_after < 0:
            msg = "reset_after must be >= 0"
            raise ValueError(msg)


class BackoffStrategy:
    """Exponential backoff with optional jitter.

    This implementation uses "full jitter" as recommended by AWS:
    https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

    Full jitter provides better performance under contention than
    "equal jitter" or "decorrelated jitter" in most scenarios.

    Example:
        >>> config = BackoffConfig(base=1.0, cap=30.0)
        >>> backoff = BackoffStrategy(config)
        >>> delay = backoff.next_delay()  # Get delay for next attempt
        >>> backoff.success()  # Call on successful connection
    """

    def __init__(self, config: BackoffConfig | None = None) -> None:
        """Initialize the backoff strategy.

        Args:
            config: Backoff configuration. Uses defaults if not provided.
        """
        self._config = config or BackoffConfig()
        self._attempt = 0
        self._last_success: float | None = None

    @property
    def config(self) -> BackoffConfig:
        """Get the current configuration."""
        return self._config

    @property
    def attempt(self) -> int:
        """Get the current attempt number (0-indexed)."""
        return self._attempt

    @property
    def exhausted(self) -> bool:
        """Return True if max attempts have been reached."""
        if self._config.max_attempts == 0:
            return False
        return self._attempt >= self._config.max_attempts

    def next_delay(self) -> float:
        """Calculate the next backoff delay.

        Returns:
            The delay in seconds before the next retry attempt.

        Raises:
            RuntimeError: If max_attempts has been reached.
        """
        if self.exhausted:
            msg = f"Max attempts ({self._config.max_attempts}) exhausted"
            raise RuntimeError(msg)

        # Calculate exponential delay
        delay = min(
            self._config.base * (self._config.multiplier**self._attempt),
            self._config.cap,
        )

        # Apply full jitter: random value between 0 and delay
        if self._config.jitter:
            delay = random.uniform(0, delay)

        self._attempt += 1
        return delay

    def peek_delay(self) -> float:
        """Preview the next delay without incrementing the attempt counter.

        Returns:
            The delay that would be returned by next_delay().
        """
        delay = min(
            self._config.base * (self._config.multiplier**self._attempt),
            self._config.cap,
        )
        # Note: jitter makes this non-deterministic
        if self._config.jitter:
            delay = delay / 2  # Return expected value
        return delay

    def success(self) -> None:
        """Mark a successful connection.

        This records the success time for potential attempt counter reset.
        Call this when a connection is successfully established.
        """
        self._last_success = time.monotonic()

    def reset(self) -> None:
        """Reset the attempt counter to zero.

        Call this to manually reset the backoff state.
        """
        self._attempt = 0
        self._last_success = None

    def maybe_reset(self) -> bool:
        """Reset the attempt counter if enough time has passed since last success.

        Returns:
            True if the counter was reset, False otherwise.
        """
        if self._last_success is None:
            return False

        elapsed = time.monotonic() - self._last_success
        if elapsed >= self._config.reset_after:
            self._attempt = 0
            return True
        return False

    def __repr__(self) -> str:
        return (
            f"BackoffStrategy(attempt={self._attempt}, "
            f"exhausted={self.exhausted}, "
            f"config={self._config})"
        )
