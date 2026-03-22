"""Heartbeat management for JetSocket.

This module provides automatic ping/pong handling to detect dead connections
and measure latency. Supports both WebSocket-level pings and application-level
heartbeats.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class HeartbeatConfig:
    """Configuration for heartbeat behavior.

    Args:
        interval: Seconds between ping frames.
        timeout: Seconds to wait for pong before considering connection dead.
        payload: Custom payload for ping frames.
        use_ws_ping: If True, use WebSocket-level PING frames (RFC 6455).
        application_ping: Custom function to generate application-level ping.
        pong_matcher: Custom function to detect application-level pong responses.
    """

    interval: float = 30.0
    timeout: float = 10.0
    payload: bytes = b""
    use_ws_ping: bool = True
    application_ping: Callable[[], bytes | str | dict[str, Any]] | None = None
    pong_matcher: Callable[[Any], bool] | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.interval <= 0:
            msg = f"interval must be positive, got {self.interval}"
            raise ValueError(msg)
        if self.timeout <= 0:
            msg = f"timeout must be positive, got {self.timeout}"
            raise ValueError(msg)
        if self.timeout >= self.interval:
            msg = (
                f"timeout ({self.timeout}) must be less than interval ({self.interval})"
            )
            raise ValueError(msg)
        if self.application_ping is not None and self.use_ws_ping:
            msg = "cannot use both use_ws_ping=True and application_ping"
            raise ValueError(msg)


# Type alias for the ping sender callback
SendPingFunc = Callable[[bytes], Awaitable[None]]
OnTimeoutFunc = Callable[[], Awaitable[None]]


class HeartbeatManager:
    """Manages heartbeat lifecycle with latency tracking.

    Runs as a background task, sending periodic pings and monitoring
    for pong responses. If a pong is not received within the timeout,
    the on_timeout callback is invoked.

    Example:
        >>> async def send_ping(payload: bytes) -> None:
        ...     await transport.ping(payload)
        >>>
        >>> async def handle_timeout() -> None:
        ...     await transport.close()
        >>>
        >>> heartbeat = HeartbeatManager(config)
        >>> await heartbeat.start(send_ping, handle_timeout)
        >>> # When pong received:
        >>> latency = heartbeat.on_pong(payload)
    """

    def __init__(self, config: HeartbeatConfig) -> None:
        """Initialize heartbeat manager.

        Args:
            config: Heartbeat configuration.
        """
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_ping_time: float | None = None
        self._last_latency: float | None = None
        self._latency_samples: deque[float] = deque(maxlen=10)
        self._pong_event: asyncio.Event | None = None
        self._pending_payload: bytes | None = None

    @property
    def config(self) -> HeartbeatConfig:
        """Get the heartbeat configuration."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Return True if heartbeat is active."""
        return self._running and self._task is not None and not self._task.done()

    @property
    def latency_ms(self) -> float | None:
        """Get the last measured round-trip latency in milliseconds."""
        return self._last_latency

    @property
    def latency_avg_ms(self) -> float | None:
        """Get the rolling average latency in milliseconds.

        Uses the last 10 samples for the average.
        """
        if not self._latency_samples:
            return None
        return sum(self._latency_samples) / len(self._latency_samples)

    async def start(self, send_ping: SendPingFunc, on_timeout: OnTimeoutFunc) -> None:
        """Start the heartbeat background task.

        Args:
            send_ping: Async callback to send a ping frame.
            on_timeout: Async callback invoked when pong times out.
        """
        if self._running:
            return

        self._running = True
        self._pong_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._heartbeat_loop(send_ping, on_timeout),
            name="jetsocket-heartbeat",
        )

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        self._running = False
        if self._pong_event is not None:
            self._pong_event.set()  # Unblock any waiting

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        self._pong_event = None
        self._pending_payload = None

    def on_pong(self, payload: bytes) -> float | None:
        """Handle a received pong frame.

        Args:
            payload: The pong payload (should match sent ping).

        Returns:
            Round-trip latency in milliseconds, or None if no matching ping.
        """
        if self._last_ping_time is None:
            return None

        # Check payload matches if we have a pending one
        if self._pending_payload is not None and payload != self._pending_payload:
            return None

        latency_ms = (time.monotonic() - self._last_ping_time) * 1000
        self._last_latency = latency_ms
        self._latency_samples.append(latency_ms)
        self._last_ping_time = None
        self._pending_payload = None

        if self._pong_event is not None:
            self._pong_event.set()

        return latency_ms

    def on_application_message(self, data: Any) -> bool:
        """Check if a message is an application-level pong.

        Args:
            data: The deserialized message data.

        Returns:
            True if the message was a pong (and was handled).
        """
        if self._config.pong_matcher is None:
            return False

        if self._config.pong_matcher(data):
            # Treat as pong
            if self._last_ping_time is not None:
                latency_ms = (time.monotonic() - self._last_ping_time) * 1000
                self._last_latency = latency_ms
                self._latency_samples.append(latency_ms)
                self._last_ping_time = None

                if self._pong_event is not None:
                    self._pong_event.set()
            return True

        return False

    def reset(self) -> None:
        """Reset latency tracking state.

        Called on reconnection to clear stale data.
        """
        self._last_ping_time = None
        self._last_latency = None
        self._latency_samples.clear()
        self._pending_payload = None

    async def _heartbeat_loop(
        self, send_ping: SendPingFunc, on_timeout: OnTimeoutFunc
    ) -> None:
        """Main heartbeat loop.

        Args:
            send_ping: Callback to send ping.
            on_timeout: Callback when pong times out.
        """
        while self._running:
            try:
                # Wait for interval
                await asyncio.sleep(self._config.interval)

                if not self._running:
                    break

                # Clear event for this ping cycle
                if self._pong_event is not None:
                    self._pong_event.clear()

                # Send ping
                payload = self._config.payload
                self._pending_payload = payload
                self._last_ping_time = time.monotonic()
                await send_ping(payload)

                # Wait for pong with timeout
                if self._pong_event is not None:
                    try:
                        await asyncio.wait_for(
                            self._pong_event.wait(), timeout=self._config.timeout
                        )
                    except asyncio.TimeoutError:
                        # Pong not received in time
                        if self._running:
                            await on_timeout()
                            break

            except asyncio.CancelledError:
                break
            except Exception:
                # Unexpected error in heartbeat loop
                # Log would go here; for now just continue
                pass
