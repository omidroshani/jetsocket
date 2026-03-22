"""Pre-configured WebSocket profiles for WSFabric.

This module provides optimized presets for common use cases.

Usage:
    >>> from wsfabric.presets import trading
    >>> ws = trading("wss://stream.binance.com/ws")
"""

from __future__ import annotations

from typing import Any

from wsfabric.backoff import BackoffConfig
from wsfabric.buffer import BufferConfig
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.manager import WebSocket


def trading(uri: str, **overrides: Any) -> WebSocket[Any]:
    """Optimized for exchange WebSocket connections.

    Features:
    - Fast reconnect (0.5s base, 30s cap, infinite retries)
    - Aggressive heartbeat (20s interval)
    - Large message buffer (10K messages) with deduplication
    - Proactive reconnect before 24h exchange limit
    - Compression enabled

    Args:
        uri: WebSocket URI.
        **overrides: Override any default setting.

    Returns:
        Configured WebSocket.
    """
    defaults: dict[str, Any] = {
        "reconnect": True,
        "backoff": BackoffConfig(
            base=0.5, multiplier=2.0, cap=30.0, jitter=True,
            max_attempts=0, reset_after=60.0,
        ),
        "heartbeat": HeartbeatConfig(interval=20.0, timeout=10.0),
        "buffer": BufferConfig(
            capacity=10_000, overflow_policy="drop_oldest",
            enable_dedup=True, dedup_window=1000,
        ),
        "max_connection_age": 85800.0,
        "compress": True,
    }
    defaults.update(overrides)
    return WebSocket(uri, **defaults)


def llm_stream(uri: str, **overrides: Any) -> WebSocket[Any]:
    """Optimized for LLM streaming (large messages, low latency).

    Features:
    - Quick retry with 5 max attempts
    - Longer heartbeat (30s, less overhead)
    - Smaller buffer (500, sequential streaming)
    - Large max message size (128MB)
    - Compression disabled (token streaming doesn't benefit)

    Args:
        uri: WebSocket URI.
        **overrides: Override any default setting.

    Returns:
        Configured WebSocket.
    """
    defaults: dict[str, Any] = {
        "reconnect": True,
        "backoff": BackoffConfig(
            base=1.0, multiplier=2.0, cap=10.0, jitter=True,
            max_attempts=5, reset_after=30.0,
        ),
        "heartbeat": HeartbeatConfig(interval=30.0, timeout=15.0),
        "buffer": BufferConfig(capacity=500, overflow_policy="drop_oldest"),
        "max_message_size": 128 * 1024 * 1024,
        "compress": False,
    }
    defaults.update(overrides)
    return WebSocket(uri, **defaults)


def dashboard(uri: str, **overrides: Any) -> WebSocket[Any]:
    """Optimized for real-time dashboard feeds.

    Features:
    - Relaxed reconnect (2s base, 60s cap)
    - Standard heartbeat (30s)
    - Small buffer (100, latest data only)
    - Drop oldest on overflow

    Args:
        uri: WebSocket URI.
        **overrides: Override any default setting.

    Returns:
        Configured WebSocket.
    """
    defaults: dict[str, Any] = {
        "reconnect": True,
        "backoff": BackoffConfig(
            base=2.0, multiplier=2.0, cap=60.0, jitter=True,
            max_attempts=0, reset_after=120.0,
        ),
        "heartbeat": HeartbeatConfig(interval=30.0, timeout=20.0),
        "buffer": BufferConfig(capacity=100, overflow_policy="drop_oldest"),
    }
    defaults.update(overrides)
    return WebSocket(uri, **defaults)


def minimal(uri: str, **overrides: Any) -> WebSocket[Any]:
    """Minimal configuration with basic reconnect.

    Features:
    - Basic reconnect with 10 max attempts
    - No heartbeat
    - No buffer

    Args:
        uri: WebSocket URI.
        **overrides: Override any default setting.

    Returns:
        Configured WebSocket.
    """
    defaults: dict[str, Any] = {
        "reconnect": True,
        "backoff": BackoffConfig(
            base=1.0, multiplier=2.0, cap=30.0, jitter=True,
            max_attempts=10, reset_after=60.0,
        ),
        "heartbeat": None,
        "buffer": None,
    }
    defaults.update(overrides)
    return WebSocket(uri, **defaults)