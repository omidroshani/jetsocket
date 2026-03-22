"""I/O tests for WebSocket using the live echo server.

Covers manager paths that require a real WebSocket connection.
"""

from __future__ import annotations

import asyncio

from jetsocket.buffer import BufferConfig
from jetsocket.manager import WebSocket
from jetsocket.state import ConnectionState


class TestManagerIO:
    """Test WebSocket with a live server."""

    async def test_connect_and_close(self, live_server_url: str) -> None:
        """Test basic connect and close."""
        ws = WebSocket(live_server_url)
        await ws.connect()
        assert ws.is_connected
        assert ws.state == ConnectionState.CONNECTED
        await ws.close()
        assert not ws.is_connected

    async def test_send_recv(self, live_server_url: str) -> None:
        """Test send and receive."""
        async with WebSocket(live_server_url) as ws:
            await ws.send({"msg": "hello"})
            result = await ws.recv()
            assert result["msg"] == "hello"

    async def test_send_raw(self, live_server_url: str) -> None:
        """Test send_raw with bytes."""
        async with WebSocket(live_server_url) as ws:
            await ws.send_raw(b'{"raw": true}')
            result = await ws.recv()
            assert result["raw"] is True

    async def test_multiple_messages(self, live_server_url: str) -> None:
        """Test multiple message exchange."""
        async with WebSocket(live_server_url) as ws:
            for i in range(10):
                await ws.send({"i": i})
                result = await ws.recv()
                assert result["i"] == i

    async def test_stats_update(self, live_server_url: str) -> None:
        """Test stats update after messages."""
        async with WebSocket(live_server_url) as ws:
            await ws.send({"test": 1})
            await ws.recv()
            await ws.send({"test": 2})
            await ws.recv()

            stats = ws.stats()
            assert stats.messages_sent >= 2
            assert stats.messages_received >= 2
            assert stats.bytes_sent > 0
            assert stats.bytes_received > 0
            assert stats.state == ConnectionState.CONNECTED
            assert stats.uptime_seconds > 0

    async def test_context_manager(self, live_server_url: str) -> None:
        """Test async context manager auto-closes."""
        async with WebSocket(live_server_url) as ws:
            assert ws.is_connected
        assert not ws.is_connected

    async def test_event_handlers(self, live_server_url: str) -> None:
        """Test event handlers fire during lifecycle."""
        events: list[str] = []

        ws = WebSocket(live_server_url)

        @ws.on("connected")
        async def on_connected(event: object) -> None:
            events.append("connected")

        @ws.on("disconnected")
        async def on_disconnected(event: object) -> None:
            events.append("disconnected")

        await ws.connect()
        # Give event handler time to fire
        await asyncio.sleep(0.1)
        assert "connected" in events

        await ws.close()
        await asyncio.sleep(0.1)
        assert "disconnected" in events

    async def test_with_buffer(self, live_server_url: str) -> None:
        """Test with message buffer enabled."""
        ws = WebSocket(
            live_server_url,
            buffer=BufferConfig(capacity=100),
        )
        await ws.connect()
        try:
            await ws.send({"buffer": "test"})
            result = await ws.recv()
            assert result["buffer"] == "test"
        finally:
            await ws.close()

    async def test_with_compression_disabled(self, live_server_url: str) -> None:
        """Test with compression disabled."""
        ws = WebSocket(live_server_url, compress=False)
        await ws.connect()
        try:
            await ws.send({"no_compress": True})
            result = await ws.recv()
            assert result["no_compress"] is True
        finally:
            await ws.close()

    async def test_latency_ms_without_heartbeat(self, live_server_url: str) -> None:
        """Test latency_ms is None without heartbeat."""
        ws = WebSocket(live_server_url, heartbeat=None)
        await ws.connect()
        try:
            assert ws.latency_ms is None
        finally:
            await ws.close()


class TestSyncClientIO:
    """Test SyncWebSocket with a live server."""

    def test_connect_send_recv(self, live_server_url: str) -> None:
        """Test basic sync client usage."""
        from jetsocket.sync_client import SyncWebSocket

        client = SyncWebSocket(
            live_server_url,
            reconnect=False,
            connect_timeout=5.0,
        )
        client.connect()
        try:
            assert client.is_connected
            client.send({"sync": "test"})
            result = client.recv(timeout=5.0)
            assert result["sync"] == "test"
        finally:
            client.close()

    def test_stats(self, live_server_url: str) -> None:
        """Test sync client stats."""
        from jetsocket.sync_client import SyncWebSocket

        client = SyncWebSocket(
            live_server_url,
            reconnect=False,
            connect_timeout=5.0,
        )
        client.connect()
        try:
            client.send({"s": 1})
            client.recv(timeout=5.0)
            stats = client.stats()
            assert stats is not None
            assert stats.messages_sent >= 1
        finally:
            client.close()

    def test_multiple_messages(self, live_server_url: str) -> None:
        """Test sending and receiving multiple messages."""
        from jetsocket.sync_client import SyncWebSocket

        client = SyncWebSocket(
            live_server_url,
            reconnect=False,
            connect_timeout=5.0,
        )
        client.connect()
        try:
            for i in range(5):
                client.send({"i": i})
                result = client.recv(timeout=5.0)
                assert result["i"] == i
        finally:
            client.close()

    def test_context_manager(self, live_server_url: str) -> None:
        """Test sync client context manager."""
        from jetsocket.sync_client import SyncWebSocket

        with SyncWebSocket(
            live_server_url,
            reconnect=False,
            connect_timeout=5.0,
        ) as client:
            client.send({"ctx": True})
            result = client.recv(timeout=5.0)
            assert result["ctx"] is True
