"""Integration tests for transport layer.

These tests use a real WebSocket server (via websockets library) to test
the transport implementations end-to-end.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import pytest
import websockets.server
from websockets.frames import CloseCode as WsCloseCode

from jetsocket.transport import AsyncTransport, BaseTransportConfig, SyncTransport
from jetsocket.types import Opcode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# Server port for tests
TEST_PORT = 9753


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

    async with websockets.server.serve(echo_handler, "127.0.0.1", TEST_PORT) as server:
        yield f"ws://127.0.0.1:{TEST_PORT}"
        server.close()


@pytest.fixture
async def ping_pong_server() -> AsyncIterator[str]:
    """Start a server that responds to pings."""

    async def handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        """Handle connection and respond to pings."""
        try:
            async for message in websocket:
                if message == "ping":
                    await websocket.send("pong")
                else:
                    await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(handler, "127.0.0.1", TEST_PORT + 1) as server:
        yield f"ws://127.0.0.1:{TEST_PORT + 1}"
        server.close()


@pytest.fixture
async def close_server() -> AsyncIterator[str]:
    """Start a server that closes the connection after receiving a message."""

    async def handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        """Close connection after first message."""
        try:
            await websocket.recv()
            await websocket.close(WsCloseCode.NORMAL_CLOSURE, "Bye")
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(handler, "127.0.0.1", TEST_PORT + 2) as server:
        yield f"ws://127.0.0.1:{TEST_PORT + 2}"
        server.close()


@pytest.mark.integration
class TestAsyncTransport:
    """Integration tests for AsyncTransport.

    Note: Compression is disabled in tests because permessage-deflate
    support is not yet implemented.
    """

    async def test_connect_and_close(self, echo_server: str) -> None:
        """Test basic connect and close."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)
        assert transport.is_connected
        await transport.close()
        assert not transport.is_connected

    async def test_send_receive_text(self, echo_server: str) -> None:
        """Test sending and receiving text messages."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)

        await transport.send("Hello, World!")
        frame = await transport.recv()

        assert frame.opcode == Opcode.TEXT
        assert frame.as_text() == "Hello, World!"

        await transport.close()

    async def test_send_receive_binary(self, echo_server: str) -> None:
        """Test sending and receiving binary messages."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)

        data = bytes(range(256))
        await transport.send(data, binary=True)
        frame = await transport.recv()

        assert frame.opcode == Opcode.BINARY
        assert frame.payload == data

        await transport.close()

    async def test_send_receive_unicode(self, echo_server: str) -> None:
        """Test sending and receiving unicode messages."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)

        message = "Hello, 世界! 🌍 مرحبا"
        await transport.send(message)
        frame = await transport.recv()

        assert frame.as_text() == message

        await transport.close()

    async def test_multiple_messages(self, echo_server: str) -> None:
        """Test sending and receiving multiple messages."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)

        messages = ["one", "two", "three", "four", "five"]
        for msg in messages:
            await transport.send(msg)

        for expected in messages:
            frame = await transport.recv()
            assert frame.as_text() == expected

        await transport.close()

    async def test_context_manager(self, echo_server: str) -> None:
        """Test async context manager."""
        async with AsyncTransport(BaseTransportConfig(compression=False)) as transport:
            await transport.connect(echo_server)
            await transport.send("test")
            frame = await transport.recv()
            assert frame.as_text() == "test"

        assert not transport.is_connected

    async def test_server_close(self, close_server: str) -> None:
        """Test handling server-initiated close."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(close_server)

        await transport.send("trigger close")

        # Reading should raise ConnectionError after server closes
        with pytest.raises(Exception):  # Could be ConnectionError or similar
            await transport.recv()

    async def test_ping(self, echo_server: str) -> None:
        """Test sending ping frames."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        await transport.connect(echo_server)

        # Should not raise
        await transport.ping(b"hello")
        await transport.ping()  # Empty payload

        await transport.close()

    async def test_config_applied(self, echo_server: str) -> None:
        """Test that configuration is applied."""
        config = BaseTransportConfig(
            connect_timeout=30.0,
            max_frame_size=1024 * 1024,
        )
        transport = AsyncTransport(config)
        await transport.connect(echo_server)

        assert transport.config.connect_timeout == 30.0
        assert transport.config.max_frame_size == 1024 * 1024

        await transport.close()


@pytest.mark.integration
class TestSyncTransport:
    """Integration tests for SyncTransport."""

    async def _wait_for_thread(
        self, thread: threading.Thread, timeout: float = 5.0
    ) -> None:
        """Wait for a thread to complete without blocking the event loop.

        This is necessary because thread.join() blocks the event loop, preventing
        the async websockets server from processing I/O.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while thread.is_alive():
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.01)  # Yield to event loop

    def _run_in_thread(self, server_url: str) -> None:
        """Helper to run sync transport in a thread."""
        transport = SyncTransport(BaseTransportConfig(compression=False))
        transport.connect(server_url)
        transport.send("Hello")
        frame = transport.recv()
        assert frame.as_text() == "Hello"
        transport.close()

    async def test_connect_and_close(self, echo_server: str) -> None:
        """Test basic connect and close in thread."""
        # Give server time to start
        await asyncio.sleep(0.1)

        # Run sync transport in thread
        thread = threading.Thread(target=self._run_in_thread, args=(echo_server,))
        thread.start()
        await self._wait_for_thread(thread)
        assert not thread.is_alive(), "Thread did not complete"

    async def test_context_manager(self, echo_server: str) -> None:
        """Test context manager in thread."""
        await asyncio.sleep(0.1)

        def run() -> None:
            with SyncTransport(BaseTransportConfig(compression=False)) as transport:
                transport.connect(echo_server)
                transport.send("test")
                frame = transport.recv()
                assert frame.as_text() == "test"

        thread = threading.Thread(target=run)
        thread.start()
        await self._wait_for_thread(thread)
        assert not thread.is_alive()

    async def test_send_receive_binary(self, echo_server: str) -> None:
        """Test binary send/receive in thread."""
        await asyncio.sleep(0.1)

        def run() -> None:
            transport = SyncTransport(BaseTransportConfig(compression=False))
            transport.connect(echo_server)
            data = bytes(range(256))
            transport.send(data, binary=True)
            frame = transport.recv()
            assert frame.payload == data
            transport.close()

        thread = threading.Thread(target=run)
        thread.start()
        await self._wait_for_thread(thread)
        assert not thread.is_alive()


@pytest.mark.integration
class TestTransportErrors:
    """Tests for transport error handling."""

    async def test_connect_refused(self) -> None:
        """Test connection refused error."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        with pytest.raises(Exception):  # ConnectionError
            await transport.connect("ws://127.0.0.1:59999")

    async def test_invalid_uri_scheme(self) -> None:
        """Test invalid URI scheme."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        with pytest.raises(ValueError, match="Invalid WebSocket scheme"):
            await transport.connect("http://example.com")

    async def test_send_when_not_connected(self) -> None:
        """Test sending when not connected."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        with pytest.raises(Exception):  # ConnectionError
            await transport.send("test")

    async def test_recv_when_not_connected(self) -> None:
        """Test receiving when not connected."""
        transport = AsyncTransport(BaseTransportConfig(compression=False))
        with pytest.raises(Exception):  # ConnectionError
            await transport.recv()
