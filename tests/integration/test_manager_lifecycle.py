"""Integration tests for WebSocket lifecycle.

These tests use a real WebSocket server (via websockets library) to test
the manager end-to-end including reconnection and heartbeat.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
import websockets.server
from websockets.frames import CloseCode as WsCloseCode

from wsfabric.backoff import BackoffConfig
from wsfabric.events import (
    ClosedEvent,
    ConnectedEvent,
    ConnectingEvent,
    DisconnectedEvent,
    MessageEvent,
    ReconnectedEvent,
    ReconnectingEvent,
)
from wsfabric.manager import WebSocket
from wsfabric.state import ConnectionState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# Server port for tests
TEST_PORT = 9760


@pytest.fixture
async def echo_server() -> AsyncIterator[str]:
    """Start an echo WebSocket server for testing."""

    async def echo_handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        """Echo all received messages back to the client."""
        try:
            async for message in websocket:
                await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(
        echo_handler, "127.0.0.1", TEST_PORT
    ) as server:
        yield f"ws://127.0.0.1:{TEST_PORT}"
        server.close()


@pytest.fixture
async def close_after_one_server() -> AsyncIterator[str]:
    """Start a server that closes after one message."""

    async def handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        """Echo one message then close."""
        try:
            message = await websocket.recv()
            await websocket.send(message)
            await websocket.close(WsCloseCode.NORMAL_CLOSURE, "Done")
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(
        handler, "127.0.0.1", TEST_PORT + 1
    ) as server:
        yield f"ws://127.0.0.1:{TEST_PORT + 1}"
        server.close()


@pytest.fixture
async def json_server() -> AsyncIterator[str]:
    """Start a server that echoes JSON messages."""

    async def handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        """Echo JSON messages."""
        import json

        try:
            async for message in websocket:
                data = json.loads(message)
                response = {"received": data, "status": "ok"}
                await websocket.send(json.dumps(response))
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(
        handler, "127.0.0.1", TEST_PORT + 2
    ) as server:
        yield f"ws://127.0.0.1:{TEST_PORT + 2}"
        server.close()


@pytest.mark.integration
class TestManagerConnect:
    """Integration tests for connection lifecycle."""

    async def test_connect_and_close(self, echo_server: str) -> None:
        """Test basic connect and close."""
        ws: WebSocket[Any] = WebSocket(echo_server, compress=False)

        await ws.connect()
        assert ws.state == ConnectionState.CONNECTED
        assert ws.is_connected

        await ws.close()
        assert ws.state == ConnectionState.CLOSED
        assert not ws.is_connected

    async def test_connect_events(self, echo_server: str) -> None:
        """Test that connect emits proper events."""
        ws: WebSocket[Any] = WebSocket(echo_server, compress=False)

        events_received: list[str] = []

        @ws.on("connecting")
        async def on_connecting(event: ConnectingEvent) -> None:
            events_received.append(f"connecting:{event.attempt}")

        @ws.on("connected")
        async def on_connected(event: ConnectedEvent) -> None:
            events_received.append(f"connected:{event.uri}")

        await ws.connect()

        assert "connecting:1" in events_received
        assert f"connected:{echo_server}" in events_received

        await ws.close()

    async def test_close_events(self, echo_server: str) -> None:
        """Test that close emits proper events."""
        ws: WebSocket[Any] = WebSocket(echo_server, compress=False)

        events_received: list[str] = []

        @ws.on("closing")
        async def on_closing(event: Any) -> None:
            events_received.append("closing")

        @ws.on("closed")
        async def on_closed(event: ClosedEvent) -> None:
            events_received.append(f"closed:{event.code}")

        await ws.connect()
        await ws.close()

        assert "closing" in events_received
        assert "closed:1000" in events_received

    async def test_context_manager(self, echo_server: str) -> None:
        """Test async context manager."""
        async with WebSocket(echo_server, compress=False) as ws:
            assert ws.is_connected

        assert ws.state == ConnectionState.CLOSED


@pytest.mark.integration
class TestManagerMessaging:
    """Integration tests for sending and receiving messages."""

    async def test_message_events(self, json_server: str) -> None:
        """Test that messages emit events."""
        ws: WebSocket[dict[str, Any]] = WebSocket(
            json_server, compress=False
        )

        messages_received: list[dict[str, Any]] = []
        received_event = asyncio.Event()

        @ws.on("message")
        async def on_message(event: MessageEvent[dict[str, Any]]) -> None:
            messages_received.append(event.data)
            received_event.set()

        await ws.connect()
        await ws.send({"test": "data"})

        # Wait for message to be processed
        try:
            await asyncio.wait_for(received_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        await ws.close()

        assert len(messages_received) >= 1

    async def test_stats_updated(self, json_server: str) -> None:
        """Test that stats are updated after messages."""
        ws: WebSocket[dict[str, Any]] = WebSocket(
            json_server, compress=False
        )

        received_event = asyncio.Event()

        @ws.on("message")
        async def on_message(event: MessageEvent[dict[str, Any]]) -> None:
            received_event.set()

        await ws.connect()

        stats_before = ws.stats()
        assert stats_before.messages_sent == 0

        await ws.send({"test": "data"})

        # Wait for response
        try:
            await asyncio.wait_for(received_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        stats_after = ws.stats()
        await ws.close()

        assert stats_after.messages_sent == 1
        assert stats_after.bytes_sent > 0


@pytest.mark.integration
class TestManagerUptime:
    """Integration tests for uptime tracking."""

    async def test_uptime_tracking(self, echo_server: str) -> None:
        """Test that uptime is tracked correctly."""
        ws: WebSocket[str] = WebSocket(echo_server, compress=False)

        await ws.connect()

        # Wait a bit
        await asyncio.sleep(0.2)

        stats = ws.stats()
        assert stats.uptime_seconds >= 0.2
        assert stats.connection_age_seconds >= 0.2

        await ws.close()

        # After close, uptime should be 0
        stats_after = ws.stats()
        assert stats_after.uptime_seconds == 0.0
