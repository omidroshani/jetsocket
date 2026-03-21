"""Pre-configured WebSocket profiles for WSFabric.

This module provides optimized presets for common use cases:
- Trading: Crypto exchanges, algorithmic trading
- LLM Streaming: Large language model API streaming
- Dashboard: Real-time dashboard feeds
"""

from __future__ import annotations

from typing import Any

from wsfabric.backoff import BackoffConfig
from wsfabric.buffer import BufferConfig
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.manager import WebSocketManager


class Presets:
    """Pre-configured WebSocket profiles for common use cases.

    These presets provide sensible defaults optimized for specific
    application types. All settings can be overridden via kwargs.

    Example:
        >>> ws = Presets.trading("wss://stream.binance.com/ws")
        >>> ws = Presets.llm_stream("wss://api.openai.com/v1/realtime")
        >>> ws = Presets.dashboard("wss://dashboard.example.com/ws")
    """

    @staticmethod
    def trading(uri: str, **overrides: Any) -> WebSocketManager[Any]:
        """Optimized for exchange WebSocket connections.

        Features:
        - Fast reconnect (0.5s base, 30s cap)
        - Aggressive heartbeat (20s interval)
        - Large message buffer (10K messages)
        - Proactive reconnect before 24h limit
        - Compression enabled
        - Deduplication enabled

        Args:
            uri: WebSocket URI.
            **overrides: Override any default setting.

        Returns:
            Configured WebSocketManager.

        Example:
            >>> ws = Presets.trading("wss://stream.binance.com/ws")
            >>> ws = Presets.trading(
            ...     "wss://stream.binance.com/ws",
            ...     max_connection_age=43200.0,  # 12h instead of 24h
            ... )
        """
        defaults: dict[str, Any] = {
            "reconnect": True,
            "backoff": BackoffConfig(
                base=0.5,
                multiplier=2.0,
                cap=30.0,
                jitter=True,
                max_attempts=0,  # Infinite retries
                reset_after=60.0,
            ),
            "heartbeat": HeartbeatConfig(
                interval=20.0,
                timeout=10.0,
            ),
            "buffer": BufferConfig(
                capacity=10_000,
                overflow_policy="drop_oldest",
                enable_dedup=True,
                dedup_window=1000,
            ),
            "max_connection_age": 85800.0,  # 23h 50m (before exchange 24h limit)
            "compress": True,
        }
        defaults.update(overrides)
        return WebSocketManager(uri, **defaults)

    @staticmethod
    def llm_stream(uri: str, **overrides: Any) -> WebSocketManager[Any]:
        """Optimized for LLM streaming (large messages, low latency).

        Features:
        - Quick retry with limited attempts (don't wait forever)
        - Longer heartbeat (less overhead)
        - Smaller buffer (LLM streams are sequential)
        - Large max message size (128MB for long responses)
        - Compression disabled (token-level streaming doesn't benefit)

        Args:
            uri: WebSocket URI.
            **overrides: Override any default setting.

        Returns:
            Configured WebSocketManager.

        Example:
            >>> ws = Presets.llm_stream("wss://api.openai.com/v1/realtime")
            >>> ws = Presets.llm_stream(
            ...     "wss://api.anthropic.com/v1/messages",
            ...     max_message_size=256 * 1024 * 1024,  # 256MB
            ... )
        """
        defaults: dict[str, Any] = {
            "reconnect": True,
            "backoff": BackoffConfig(
                base=1.0,
                multiplier=2.0,
                cap=10.0,
                jitter=True,
                max_attempts=5,  # Don't retry forever
                reset_after=30.0,
            ),
            "heartbeat": HeartbeatConfig(
                interval=30.0,
                timeout=15.0,
            ),
            "buffer": BufferConfig(
                capacity=500,
                overflow_policy="drop_oldest",
            ),
            "max_message_size": 128 * 1024 * 1024,  # 128MB
            "compress": False,  # Token streaming doesn't benefit
        }
        defaults.update(overrides)
        return WebSocketManager(uri, **defaults)

    @staticmethod
    def dashboard(uri: str, **overrides: Any) -> WebSocketManager[Any]:
        """Optimized for real-time dashboard feeds.

        Features:
        - Relaxed reconnect (2s base, 60s cap)
        - Standard heartbeat
        - Small buffer (dashboards show latest data)
        - Drop oldest on overflow (stale data is useless)

        Args:
            uri: WebSocket URI.
            **overrides: Override any default setting.

        Returns:
            Configured WebSocketManager.

        Example:
            >>> ws = Presets.dashboard("wss://dashboard.example.com/ws")
            >>> ws = Presets.dashboard(
            ...     "wss://dashboard.example.com/ws",
            ...     buffer=BufferConfig(capacity=50),  # Even smaller buffer
            ... )
        """
        defaults: dict[str, Any] = {
            "reconnect": True,
            "backoff": BackoffConfig(
                base=2.0,
                multiplier=2.0,
                cap=60.0,
                jitter=True,
                max_attempts=0,  # Infinite retries for dashboard
                reset_after=120.0,
            ),
            "heartbeat": HeartbeatConfig(
                interval=30.0,
                timeout=20.0,
            ),
            "buffer": BufferConfig(
                capacity=100,
                overflow_policy="drop_oldest",
            ),
        }
        defaults.update(overrides)
        return WebSocketManager(uri, **defaults)

    @staticmethod
    def minimal(uri: str, **overrides: Any) -> WebSocketManager[Any]:
        """Minimal configuration with basic reconnect.

        Features:
        - Basic reconnect enabled
        - No heartbeat (use if server doesn't support it)
        - No buffer
        - Default timeouts

        Args:
            uri: WebSocket URI.
            **overrides: Override any default setting.

        Returns:
            Configured WebSocketManager.

        Example:
            >>> ws = Presets.minimal("wss://echo.websocket.org")
        """
        defaults: dict[str, Any] = {
            "reconnect": True,
            "backoff": BackoffConfig(
                base=1.0,
                multiplier=2.0,
                cap=30.0,
                jitter=True,
                max_attempts=10,
                reset_after=60.0,
            ),
            "heartbeat": None,  # No heartbeat
            "buffer": None,  # No buffer
        }
        defaults.update(overrides)
        return WebSocketManager(uri, **defaults)
