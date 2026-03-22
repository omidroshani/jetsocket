"""I/O tests for AsyncTransport using the live echo server.

Covers async transport I/O paths that require a real WebSocket server.
"""

from __future__ import annotations

import pytest

from jetsocket.transport import AsyncTransport, BaseTransportConfig


class TestAsyncTransportIO:
    """Test AsyncTransport I/O paths with a live server."""

    async def test_connect_send_recv(self, live_server_url: str) -> None:
        """Test basic connect, send, receive."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            assert transport.is_connected
            await transport.send("Hello!")
            frame = await transport.recv()
            assert frame.payload == b"Hello!"
        finally:
            await transport.close()

    async def test_send_binary(self, live_server_url: str) -> None:
        """Test binary send/recv."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            await transport.send(b"\x00\x01\x02", binary=True)
            frame = await transport.recv()
            assert frame.payload == b"\x00\x01\x02"
        finally:
            await transport.close()

    async def test_send_text_explicit(self, live_server_url: str) -> None:
        """Test explicit text send."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            await transport.send("text msg", binary=False)
            frame = await transport.recv()
            assert frame.payload == b"text msg"
        finally:
            await transport.close()

    async def test_send_explicit_binary(self, live_server_url: str) -> None:
        """Test send with explicit binary=True."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            await transport.send(b"\xaa\xbb", binary=True)
            frame = await transport.recv()
            assert frame.payload == b"\xaa\xbb"
        finally:
            await transport.close()

    async def test_multiple_messages(self, live_server_url: str) -> None:
        """Test multiple message exchange."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            for i in range(20):
                await transport.send(f"msg-{i}")
                frame = await transport.recv()
                assert frame.payload.decode("utf-8") == f"msg-{i}"
        finally:
            await transport.close()

    async def test_properties_when_connected(self, live_server_url: str) -> None:
        """Test property accessors when connected."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            assert transport.uri is not None
            assert transport.is_connected is True
            assert transport.close_code is None
            assert transport.close_reason == ""
        finally:
            await transport.close()

    async def test_large_message(self, live_server_url: str) -> None:
        """Test large message round-trip."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            payload = "x" * 100_000
            await transport.send(payload)
            frame = await transport.recv()
            assert len(frame.payload) == 100_000
        finally:
            await transport.close()

    async def test_close_graceful(self, live_server_url: str) -> None:
        """Test graceful close."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        await transport.send("test")
        await transport.recv()
        await transport.close()
        assert not transport.is_connected

    async def test_close_clears_state(self, live_server_url: str) -> None:
        """Test close clears internal state."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        await transport.close()
        assert transport._asyncio_transport is None
        assert transport._protocol is None
        assert transport._parser is None
        assert transport._deflater is None

    async def test_context_manager(self, live_server_url: str) -> None:
        """Test async context manager."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        async with AsyncTransport(config) as transport:
            await transport.connect(live_server_url)
            await transport.send("ctx-test")
            frame = await transport.recv()
            assert frame.payload == b"ctx-test"

    async def test_already_connected_raises(self, live_server_url: str) -> None:
        """Test connecting when already connected raises."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            with pytest.raises(Exception, match=r"already connected"):
                await transport.connect(live_server_url)
        finally:
            await transport.close()


class TestAsyncTransportCompression:
    """Test compression integration with live server."""

    async def test_compression_config(self, live_server_url: str) -> None:
        """Test that compression config is passed through."""
        config = BaseTransportConfig(
            connect_timeout=5.0,
            read_timeout=5.0,
            compression=True,
            compression_threshold=64,
        )
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            # Server may or may not support compression
            # Just verify the transport works either way
            await transport.send("compression-test " * 20)
            frame = await transport.recv()
            assert b"compression-test" in frame.payload
        finally:
            await transport.close()

    async def test_no_compression(self, live_server_url: str) -> None:
        """Test with compression disabled."""
        config = BaseTransportConfig(
            connect_timeout=5.0,
            read_timeout=5.0,
            compression=False,
        )
        transport = AsyncTransport(config)
        await transport.connect(live_server_url)
        try:
            assert transport._deflater is None
            await transport.send("no-compress")
            frame = await transport.recv()
            assert frame.payload == b"no-compress"
        finally:
            await transport.close()
