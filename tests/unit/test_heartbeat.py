"""Tests for heartbeat management."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from jetsocket.heartbeat import HeartbeatConfig, HeartbeatManager


class TestHeartbeatConfig:
    """Tests for HeartbeatConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = HeartbeatConfig()
        assert config.interval == 30.0
        assert config.timeout == 10.0
        assert config.payload == b""
        assert config.use_ws_ping is True
        assert config.application_ping is None
        assert config.pong_matcher is None

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = HeartbeatConfig(
            interval=5.0,
            timeout=2.0,
            payload=b"ping",
        )
        assert config.interval == 5.0
        assert config.timeout == 2.0
        assert config.payload == b"ping"

    def test_immutability(self) -> None:
        """Test that config is frozen."""
        config = HeartbeatConfig()
        with pytest.raises(AttributeError):
            config.interval = 10.0  # type: ignore[misc]

    def test_invalid_interval(self) -> None:
        """Test validation of interval."""
        with pytest.raises(ValueError, match="interval must be positive"):
            HeartbeatConfig(interval=0)

        with pytest.raises(ValueError, match="interval must be positive"):
            HeartbeatConfig(interval=-1.0)

    def test_invalid_timeout(self) -> None:
        """Test validation of timeout."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            HeartbeatConfig(timeout=0)

        with pytest.raises(ValueError, match="timeout must be positive"):
            HeartbeatConfig(timeout=-1.0)

    def test_timeout_must_be_less_than_interval(self) -> None:
        """Test that timeout < interval."""
        with pytest.raises(ValueError, match=r"timeout.*must be less than interval"):
            HeartbeatConfig(interval=5.0, timeout=5.0)

        with pytest.raises(ValueError, match=r"timeout.*must be less than interval"):
            HeartbeatConfig(interval=5.0, timeout=10.0)

    def test_cannot_use_both_ws_ping_and_application_ping(self) -> None:
        """Test mutual exclusivity of ping modes."""

        def app_ping() -> bytes:
            return b"ping"

        with pytest.raises(ValueError, match="cannot use both"):
            HeartbeatConfig(use_ws_ping=True, application_ping=app_ping)

    def test_application_ping_allowed_when_ws_ping_disabled(self) -> None:
        """Test that application ping works when ws ping disabled."""

        def app_ping() -> dict[str, str]:
            return {"type": "ping"}

        config = HeartbeatConfig(use_ws_ping=False, application_ping=app_ping)
        assert config.application_ping is not None


class TestHeartbeatManager:
    """Tests for HeartbeatManager class."""

    def test_init(self) -> None:
        """Test initialization."""
        config = HeartbeatConfig(interval=5.0, timeout=2.0)
        manager = HeartbeatManager(config)

        assert manager.config is config
        assert manager.is_running is False
        assert manager.latency_ms is None
        assert manager.latency_avg_ms is None

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping heartbeat."""
        config = HeartbeatConfig(interval=0.1, timeout=0.05)
        manager = HeartbeatManager(config)

        ping_count = 0

        async def send_ping(payload: bytes) -> None:
            nonlocal ping_count
            ping_count += 1

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)
        assert manager.is_running is True

        await asyncio.sleep(0.01)  # Let task start
        await manager.stop()

        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_ignored(self) -> None:
        """Test that starting twice is a no-op."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        async def send_ping(payload: bytes) -> None:
            pass

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)
        task = manager._task

        await manager.start(send_ping, on_timeout)
        assert manager._task is task  # Same task

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """Test that stopping when not running is safe."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        # Should not raise
        await manager.stop()

    @pytest.mark.asyncio
    async def test_ping_pong_cycle(self) -> None:
        """Test ping/pong cycle with latency measurement."""
        config = HeartbeatConfig(interval=0.1, timeout=0.08)
        manager = HeartbeatManager(config)

        pings_sent: list[bytes] = []

        async def send_ping(payload: bytes) -> None:
            pings_sent.append(payload)
            # Simulate immediate pong
            await asyncio.sleep(0.01)
            manager.on_pong(payload)

        async def on_timeout() -> None:
            pytest.fail("Should not timeout")

        await manager.start(send_ping, on_timeout)

        # Wait for at least one ping cycle to complete
        await asyncio.sleep(0.3)
        await manager.stop()

        assert len(pings_sent) >= 1
        assert manager.latency_ms is not None
        assert manager.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_timeout_callback_called(self) -> None:
        """Test that timeout callback is called when pong not received."""
        config = HeartbeatConfig(interval=0.05, timeout=0.02)
        manager = HeartbeatManager(config)

        timeout_called = False

        async def send_ping(payload: bytes) -> None:
            # Don't send pong - simulate no response
            pass

        async def on_timeout() -> None:
            nonlocal timeout_called
            timeout_called = True

        await manager.start(send_ping, on_timeout)

        # Wait for timeout
        await asyncio.sleep(0.15)
        await manager.stop()

        assert timeout_called is True

    @pytest.mark.asyncio
    async def test_on_pong_returns_latency(self) -> None:
        """Test that on_pong returns measured latency."""
        config = HeartbeatConfig(interval=0.1, timeout=0.05)
        manager = HeartbeatManager(config)

        latency: float | None = None

        async def send_ping(payload: bytes) -> None:
            nonlocal latency
            await asyncio.sleep(0.01)  # Simulate network delay
            latency = manager.on_pong(payload)

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)
        await asyncio.sleep(0.15)
        await manager.stop()

        assert latency is not None
        assert latency >= 1.0  # At least 1ms (relaxed for slow CI)

    def test_on_pong_no_pending_ping(self) -> None:
        """Test on_pong when no ping was sent."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        result = manager.on_pong(b"")
        assert result is None

    @pytest.mark.asyncio
    async def test_on_pong_wrong_payload(self) -> None:
        """Test that mismatched payload is ignored."""
        config = HeartbeatConfig(interval=0.1, timeout=0.08, payload=b"test")
        manager = HeartbeatManager(config)

        timeout_called = False

        async def send_ping(payload: bytes) -> None:
            # Send pong with wrong payload
            await asyncio.sleep(0.01)
            result = manager.on_pong(b"wrong")
            assert result is None  # Should not match

        async def on_timeout() -> None:
            nonlocal timeout_called
            timeout_called = True

        await manager.start(send_ping, on_timeout)
        await asyncio.sleep(0.5)
        await manager.stop()

        # Should have timed out due to wrong payload
        assert timeout_called is True

    @pytest.mark.asyncio
    async def test_latency_average(self) -> None:
        """Test rolling average latency calculation."""
        config = HeartbeatConfig(interval=0.02, timeout=0.01)
        manager = HeartbeatManager(config)

        ping_count = 0

        async def send_ping(payload: bytes) -> None:
            nonlocal ping_count
            ping_count += 1
            await asyncio.sleep(0.005)  # ~5ms latency
            manager.on_pong(payload)

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)

        # Wait for multiple ping cycles
        await asyncio.sleep(0.15)
        await manager.stop()

        assert manager.latency_avg_ms is not None
        assert manager.latency_avg_ms > 0
        assert ping_count >= 2

    def test_reset(self) -> None:
        """Test resetting latency state."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        # Manually set some state
        manager._last_latency = 15.0
        manager._latency_samples.append(10.0)
        manager._latency_samples.append(20.0)
        manager._last_ping_time = 12345.0

        manager.reset()

        assert manager.latency_ms is None
        assert manager.latency_avg_ms is None
        assert manager._last_ping_time is None


class TestHeartbeatManagerApplicationPing:
    """Tests for application-level ping/pong."""

    @pytest.mark.asyncio
    async def test_application_pong_matcher(self) -> None:
        """Test application-level pong detection."""

        def pong_matcher(data: Any) -> bool:
            return isinstance(data, dict) and data.get("type") == "pong"

        config = HeartbeatConfig(
            interval=0.05,
            timeout=0.03,
            use_ws_ping=False,
            pong_matcher=pong_matcher,
        )
        manager = HeartbeatManager(config)

        async def send_ping(payload: bytes) -> None:
            # Simulate application pong
            await asyncio.sleep(0.005)
            result = manager.on_application_message({"type": "pong"})
            assert result is True

        async def on_timeout() -> None:
            pytest.fail("Should not timeout")

        await manager.start(send_ping, on_timeout)
        await asyncio.sleep(0.1)
        await manager.stop()

        assert manager.latency_ms is not None

    def test_on_application_message_no_matcher(self) -> None:
        """Test that messages are ignored without matcher."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        result = manager.on_application_message({"type": "pong"})
        assert result is False

    @pytest.mark.asyncio
    async def test_on_application_message_not_pong(self) -> None:
        """Test that non-pong messages are not matched."""

        def pong_matcher(data: Any) -> bool:
            return isinstance(data, dict) and data.get("type") == "pong"

        config = HeartbeatConfig(
            interval=1.0,
            timeout=0.5,
            use_ws_ping=False,
            pong_matcher=pong_matcher,
        )
        manager = HeartbeatManager(config)

        result = manager.on_application_message({"type": "message"})
        assert result is False


class TestHeartbeatManagerEdgeCases:
    """Edge case tests for HeartbeatManager."""

    @pytest.mark.asyncio
    async def test_stop_during_sleep(self) -> None:
        """Test stopping while sleeping."""
        config = HeartbeatConfig(interval=10.0, timeout=5.0)
        manager = HeartbeatManager(config)

        async def send_ping(payload: bytes) -> None:
            pass

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)
        assert manager.is_running is True

        # Stop immediately (while sleeping in interval)
        await asyncio.sleep(0.01)
        await manager.stop()

        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_stop_during_pong_wait(self) -> None:
        """Test stopping while waiting for pong."""
        config = HeartbeatConfig(interval=0.02, timeout=0.01)
        manager = HeartbeatManager(config)

        ping_sent_event = asyncio.Event()

        async def send_ping(payload: bytes) -> None:
            # Don't send pong - signal that ping was sent
            ping_sent_event.set()

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)

        # Wait for ping to be sent, then stop during pong wait
        await asyncio.sleep(0.03)  # Wait for first ping
        await manager.stop()

        assert manager.is_running is False

    def test_latency_samples_limited_to_10(self) -> None:
        """Test that latency samples are limited to 10."""
        config = HeartbeatConfig(interval=1.0, timeout=0.5)
        manager = HeartbeatManager(config)

        # Manually add samples
        for i in range(15):
            manager._latency_samples.append(float(i))

        assert len(manager._latency_samples) == 10
        # Should have last 10 (5-14)
        assert list(manager._latency_samples) == [
            5.0,
            6.0,
            7.0,
            8.0,
            9.0,
            10.0,
            11.0,
            12.0,
            13.0,
            14.0,
        ]

    @pytest.mark.asyncio
    async def test_custom_payload(self) -> None:
        """Test that custom payload is sent."""
        config = HeartbeatConfig(interval=0.05, timeout=0.03, payload=b"custom")
        manager = HeartbeatManager(config)

        received_payload: bytes | None = None

        async def send_ping(payload: bytes) -> None:
            nonlocal received_payload
            received_payload = payload
            manager.on_pong(payload)

        async def on_timeout() -> None:
            pass

        await manager.start(send_ping, on_timeout)
        await asyncio.sleep(0.1)
        await manager.stop()

        assert received_payload == b"custom"
