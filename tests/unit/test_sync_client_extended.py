"""Extended tests for SyncWebSocketClient covering uncovered paths."""

from __future__ import annotations

from wsfabric.sync_client import SyncWebSocketClient


class TestSyncClientState:
    """Test SyncWebSocketClient state management."""

    def test_not_connected_by_default(self) -> None:
        """Test client is not connected by default."""
        client = SyncWebSocketClient("ws://example.com/ws")
        assert client.is_connected is False

    def test_close_when_not_connected_safe(self) -> None:
        """Test close is safe when not connected."""
        client = SyncWebSocketClient("ws://example.com/ws")
        client.close()  # Should not raise

    def test_close_idempotent(self) -> None:
        """Test close can be called multiple times."""
        client = SyncWebSocketClient("ws://example.com/ws")
        client.close()
        client.close()  # Should not raise


class TestSyncClientConfiguration:
    """Test SyncWebSocketClient configuration."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        client = SyncWebSocketClient("ws://example.com/ws")
        assert client._uri == "ws://example.com/ws"

    def test_custom_config(self) -> None:
        """Test custom configuration is passed through."""
        client = SyncWebSocketClient(
            "ws://example.com/ws",
            reconnect=False,
            compress=False,
            compression_threshold=512,
            connect_timeout=20.0,
        )
        assert client._manager_kwargs["reconnect"] is False
        assert client._manager_kwargs["compress"] is False
        assert client._manager_kwargs["compression_threshold"] == 512
        assert client._manager_kwargs["connect_timeout"] == 20.0


class TestSyncClientStats:
    """Test SyncWebSocketClient stats."""

    def test_stats_when_not_connected(self) -> None:
        """Test stats returns valid stats even when not connected."""
        client = SyncWebSocketClient("ws://example.com/ws")
        stats = client.stats()
        assert stats is not None
        assert stats.messages_sent == 0

    def test_latency_ms_when_not_connected(self) -> None:
        """Test latency_ms returns None when not connected."""
        client = SyncWebSocketClient("ws://example.com/ws")
        assert client.latency_ms is None
