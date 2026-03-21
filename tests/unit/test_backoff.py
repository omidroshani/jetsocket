"""Tests for wsfabric.backoff module."""

from __future__ import annotations

import time

import pytest

from wsfabric.backoff import BackoffConfig, BackoffStrategy


class TestBackoffConfig:
    """Tests for BackoffConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BackoffConfig()
        assert config.base == 1.0
        assert config.multiplier == 2.0
        assert config.cap == 60.0
        assert config.jitter is True
        assert config.max_attempts == 0
        assert config.reset_after == 60.0

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = BackoffConfig(
            base=0.5,
            multiplier=1.5,
            cap=30.0,
            jitter=False,
            max_attempts=5,
            reset_after=120.0,
        )
        assert config.base == 0.5
        assert config.multiplier == 1.5
        assert config.cap == 30.0
        assert config.jitter is False
        assert config.max_attempts == 5
        assert config.reset_after == 120.0

    def test_immutable(self) -> None:
        """Test that config is immutable."""
        config = BackoffConfig()
        with pytest.raises(AttributeError):
            config.base = 2.0  # type: ignore[misc]

    def test_invalid_base(self) -> None:
        """Test that base must be positive."""
        with pytest.raises(ValueError, match="base must be positive"):
            BackoffConfig(base=0)
        with pytest.raises(ValueError, match="base must be positive"):
            BackoffConfig(base=-1)

    def test_invalid_multiplier(self) -> None:
        """Test that multiplier must be >= 1."""
        with pytest.raises(ValueError, match="multiplier must be >= 1"):
            BackoffConfig(multiplier=0.5)

    def test_invalid_cap(self) -> None:
        """Test that cap must be >= base."""
        with pytest.raises(ValueError, match="cap must be >= base"):
            BackoffConfig(base=10.0, cap=5.0)

    def test_invalid_max_attempts(self) -> None:
        """Test that max_attempts must be >= 0."""
        with pytest.raises(ValueError, match="max_attempts must be >= 0"):
            BackoffConfig(max_attempts=-1)


class TestBackoffStrategy:
    """Tests for BackoffStrategy class."""

    def test_default_config(self) -> None:
        """Test strategy with default config."""
        strategy = BackoffStrategy()
        assert strategy.config == BackoffConfig()
        assert strategy.attempt == 0

    def test_custom_config(self) -> None:
        """Test strategy with custom config."""
        config = BackoffConfig(base=2.0, cap=30.0)
        strategy = BackoffStrategy(config)
        assert strategy.config == config

    def test_exponential_without_jitter(self) -> None:
        """Test exponential backoff without jitter."""
        config = BackoffConfig(base=1.0, multiplier=2.0, cap=60.0, jitter=False)
        strategy = BackoffStrategy(config)

        assert strategy.next_delay() == 1.0  # 1 * 2^0
        assert strategy.next_delay() == 2.0  # 1 * 2^1
        assert strategy.next_delay() == 4.0  # 1 * 2^2
        assert strategy.next_delay() == 8.0  # 1 * 2^3

    def test_cap_respected(self) -> None:
        """Test that cap is respected."""
        config = BackoffConfig(base=10.0, multiplier=2.0, cap=30.0, jitter=False)
        strategy = BackoffStrategy(config)

        assert strategy.next_delay() == 10.0  # 10 * 2^0
        assert strategy.next_delay() == 20.0  # 10 * 2^1
        assert strategy.next_delay() == 30.0  # 10 * 2^2 = 40, capped to 30
        assert strategy.next_delay() == 30.0  # Still capped

    def test_jitter_range(self) -> None:
        """Test that jitter produces values in expected range."""
        config = BackoffConfig(base=10.0, multiplier=2.0, cap=60.0, jitter=True)

        # Run multiple times to test randomness
        for _ in range(100):
            strategy = BackoffStrategy(config)
            delay = strategy.next_delay()
            # With full jitter, delay should be between 0 and base
            assert 0 <= delay <= 10.0

    def test_max_attempts(self) -> None:
        """Test max_attempts limit."""
        config = BackoffConfig(max_attempts=3, jitter=False)
        strategy = BackoffStrategy(config)

        strategy.next_delay()
        strategy.next_delay()
        strategy.next_delay()

        assert strategy.exhausted
        with pytest.raises(RuntimeError, match="Max attempts"):
            strategy.next_delay()

    def test_infinite_attempts(self) -> None:
        """Test infinite attempts (max_attempts=0)."""
        config = BackoffConfig(max_attempts=0, jitter=False)
        strategy = BackoffStrategy(config)

        # Should never be exhausted
        for _ in range(100):
            assert not strategy.exhausted
            strategy.next_delay()

    def test_reset(self) -> None:
        """Test manual reset."""
        config = BackoffConfig(jitter=False)
        strategy = BackoffStrategy(config)

        strategy.next_delay()
        strategy.next_delay()
        assert strategy.attempt == 2

        strategy.reset()
        assert strategy.attempt == 0
        assert strategy.next_delay() == 1.0  # Back to first attempt

    def test_success(self) -> None:
        """Test success recording."""
        strategy = BackoffStrategy()
        assert strategy._last_success is None

        strategy.success()
        assert strategy._last_success is not None

    def test_maybe_reset(self) -> None:
        """Test automatic reset after success duration."""
        config = BackoffConfig(reset_after=0.1, jitter=False)  # 100ms
        strategy = BackoffStrategy(config)

        strategy.next_delay()
        strategy.next_delay()
        assert strategy.attempt == 2

        strategy.success()

        # Not enough time passed
        assert not strategy.maybe_reset()
        assert strategy.attempt == 2

        # Wait for reset_after
        time.sleep(0.15)
        assert strategy.maybe_reset()
        assert strategy.attempt == 0

    def test_peek_delay(self) -> None:
        """Test peek_delay does not increment counter."""
        config = BackoffConfig(jitter=False)
        strategy = BackoffStrategy(config)

        # Peek should not change attempt counter
        peek1 = strategy.peek_delay()
        peek2 = strategy.peek_delay()
        assert peek1 == peek2
        assert strategy.attempt == 0

        # After actual next_delay, peek should return new value
        strategy.next_delay()
        peek3 = strategy.peek_delay()
        assert peek3 > peek1

    def test_repr(self) -> None:
        """Test string representation."""
        strategy = BackoffStrategy()
        repr_str = repr(strategy)
        assert "BackoffStrategy" in repr_str
        assert "attempt=0" in repr_str
        assert "exhausted=False" in repr_str
