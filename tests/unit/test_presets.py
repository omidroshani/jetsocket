"""Tests for Presets."""

from __future__ import annotations

from wsfabric.backoff import BackoffConfig
from wsfabric.buffer import BufferConfig
from wsfabric.heartbeat import HeartbeatConfig
from wsfabric.manager import WebSocket
from wsfabric.presets import dashboard, llm_stream, minimal, trading


class TestPresetsTrading:
    """Tests for trading()."""

    def test_returns_websocket_manager(self) -> None:
        """Test that trading preset returns WebSocket."""
        ws = trading("wss://stream.binance.com/ws")

        assert isinstance(ws, WebSocket)
        assert ws.uri == "wss://stream.binance.com/ws"

    def test_default_reconnect(self) -> None:
        """Test trading preset has reconnect enabled."""
        ws = trading("wss://example.com/ws")

        assert ws._reconnect_enabled is True

    def test_default_backoff(self) -> None:
        """Test trading preset has fast backoff."""
        ws = trading("wss://example.com/ws")

        assert ws._backoff_config.base == 0.5
        assert ws._backoff_config.cap == 30.0
        assert ws._backoff_config.jitter is True
        assert ws._backoff_config.max_attempts == 0  # Infinite

    def test_default_heartbeat(self) -> None:
        """Test trading preset has aggressive heartbeat."""
        ws = trading("wss://example.com/ws")

        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 20.0
        assert ws._heartbeat_config.timeout == 10.0

    def test_default_buffer(self) -> None:
        """Test trading preset has large buffer with dedup."""
        ws = trading("wss://example.com/ws")

        assert ws._buffer_config is not None
        assert ws._buffer_config.capacity == 10_000
        assert ws._buffer_config.enable_dedup is True
        assert ws._buffer_config.dedup_window == 1000

    def test_default_max_connection_age(self) -> None:
        """Test trading preset has 24h connection rotation."""
        ws = trading("wss://example.com/ws")

        assert ws._max_connection_age == 85800.0  # 23h 50m

    def test_override_backoff(self) -> None:
        """Test overriding backoff config."""
        custom_backoff = BackoffConfig(base=2.0, cap=60.0)
        ws = trading("wss://example.com/ws", backoff=custom_backoff)

        assert ws._backoff_config.base == 2.0
        assert ws._backoff_config.cap == 60.0

    def test_override_max_connection_age(self) -> None:
        """Test overriding max connection age."""
        ws = trading("wss://example.com/ws", max_connection_age=43200.0)

        assert ws._max_connection_age == 43200.0


class TestPresetsLLMStream:
    """Tests for llm_stream()."""

    def test_returns_websocket_manager(self) -> None:
        """Test that llm_stream preset returns WebSocket."""
        ws = llm_stream("wss://api.openai.com/v1/realtime")

        assert isinstance(ws, WebSocket)

    def test_default_reconnect(self) -> None:
        """Test llm_stream preset has reconnect enabled."""
        ws = llm_stream("wss://example.com/ws")

        assert ws._reconnect_enabled is True

    def test_default_backoff_limited_retries(self) -> None:
        """Test llm_stream preset has limited retries."""
        ws = llm_stream("wss://example.com/ws")

        assert ws._backoff_config.max_attempts == 5
        assert ws._backoff_config.cap == 10.0

    def test_default_heartbeat(self) -> None:
        """Test llm_stream preset has longer heartbeat."""
        ws = llm_stream("wss://example.com/ws")

        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 30.0
        assert ws._heartbeat_config.timeout == 15.0

    def test_default_buffer_smaller(self) -> None:
        """Test llm_stream preset has smaller buffer."""
        ws = llm_stream("wss://example.com/ws")

        assert ws._buffer_config is not None
        assert ws._buffer_config.capacity == 500

    def test_default_large_message_size(self) -> None:
        """Test llm_stream preset has large max message size."""
        ws = llm_stream("wss://example.com/ws")

        # Access via transport config
        assert ws._transport_config.max_message_size == 128 * 1024 * 1024

    def test_compression_disabled(self) -> None:
        """Test llm_stream preset has compression disabled."""
        ws = llm_stream("wss://example.com/ws")

        assert ws._transport_config.compression is False

    def test_override_max_message_size(self) -> None:
        """Test overriding max message size."""
        ws = llm_stream(
            "wss://example.com/ws",
            max_message_size=256 * 1024 * 1024,
        )

        assert ws._transport_config.max_message_size == 256 * 1024 * 1024


class TestPresetsDashboard:
    """Tests for dashboard()."""

    def test_returns_websocket_manager(self) -> None:
        """Test that dashboard preset returns WebSocket."""
        ws = dashboard("wss://dashboard.example.com/ws")

        assert isinstance(ws, WebSocket)

    def test_default_reconnect(self) -> None:
        """Test dashboard preset has reconnect enabled."""
        ws = dashboard("wss://example.com/ws")

        assert ws._reconnect_enabled is True

    def test_default_backoff_relaxed(self) -> None:
        """Test dashboard preset has relaxed backoff."""
        ws = dashboard("wss://example.com/ws")

        assert ws._backoff_config.base == 2.0
        assert ws._backoff_config.cap == 60.0
        assert ws._backoff_config.max_attempts == 0  # Infinite

    def test_default_heartbeat(self) -> None:
        """Test dashboard preset has standard heartbeat."""
        ws = dashboard("wss://example.com/ws")

        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 30.0
        assert ws._heartbeat_config.timeout == 20.0

    def test_default_buffer_small(self) -> None:
        """Test dashboard preset has small buffer."""
        ws = dashboard("wss://example.com/ws")

        assert ws._buffer_config is not None
        assert ws._buffer_config.capacity == 100
        assert ws._buffer_config.overflow_policy == "drop_oldest"

    def test_override_buffer(self) -> None:
        """Test overriding buffer config."""
        custom_buffer = BufferConfig(capacity=50, overflow_policy="drop_newest")
        ws = dashboard("wss://example.com/ws", buffer=custom_buffer)

        assert ws._buffer_config.capacity == 50
        assert ws._buffer_config.overflow_policy == "drop_newest"


class TestPresetsMinimal:
    """Tests for minimal()."""

    def test_returns_websocket_manager(self) -> None:
        """Test that minimal preset returns WebSocket."""
        ws = minimal("wss://echo.websocket.org")

        assert isinstance(ws, WebSocket)

    def test_default_reconnect(self) -> None:
        """Test minimal preset has reconnect enabled."""
        ws = minimal("wss://example.com/ws")

        assert ws._reconnect_enabled is True

    def test_default_backoff(self) -> None:
        """Test minimal preset has basic backoff."""
        ws = minimal("wss://example.com/ws")

        assert ws._backoff_config.base == 1.0
        assert ws._backoff_config.cap == 30.0
        assert ws._backoff_config.max_attempts == 10

    def test_no_heartbeat(self) -> None:
        """Test minimal preset has no heartbeat."""
        ws = minimal("wss://example.com/ws")

        assert ws._heartbeat_config is None

    def test_no_buffer(self) -> None:
        """Test minimal preset has no buffer."""
        ws = minimal("wss://example.com/ws")

        assert ws._buffer_config is None

    def test_override_heartbeat(self) -> None:
        """Test adding heartbeat via override."""
        custom_heartbeat = HeartbeatConfig(interval=15.0, timeout=5.0)
        ws = minimal("wss://example.com/ws", heartbeat=custom_heartbeat)

        assert ws._heartbeat_config is not None
        assert ws._heartbeat_config.interval == 15.0


class TestPresetsIntegration:
    """Integration tests for presets."""

    def test_all_presets_create_valid_managers(self) -> None:
        """Test that all presets create valid WebSockets."""
        uri = "wss://example.com/ws"

        presets = [
            trading(uri),
            llm_stream(uri),
            dashboard(uri),
            minimal(uri),
        ]

        for ws in presets:
            assert isinstance(ws, WebSocket)
            assert ws.uri == uri

    def test_presets_have_different_configs(self) -> None:
        """Test that presets have different configurations."""
        uri = "wss://example.com/ws"

        ws_trading = trading(uri)
        ws_llm = llm_stream(uri)
        ws_dashboard = dashboard(uri)
        ws_minimal = minimal(uri)

        # Different backoff bases
        assert ws_trading._backoff_config.base != ws_dashboard._backoff_config.base

        # Different buffer sizes
        assert ws_trading._buffer_config is not None
        assert ws_llm._buffer_config is not None
        assert ws_trading._buffer_config.capacity != ws_llm._buffer_config.capacity

        # Minimal has no heartbeat
        assert ws_minimal._heartbeat_config is None
        assert ws_trading._heartbeat_config is not None

    def test_presets_can_be_composed(self) -> None:
        """Test that presets can be composed with overrides."""
        # Start with trading preset but use llm-like message size
        ws = trading(
            "wss://example.com/ws",
            max_message_size=128 * 1024 * 1024,
            compress=False,
        )

        # Should have trading backoff but llm-like message handling
        assert ws._backoff_config.base == 0.5  # Trading
        assert ws._transport_config.max_message_size == 128 * 1024 * 1024  # LLM
        assert ws._transport_config.compression is False  # LLM
