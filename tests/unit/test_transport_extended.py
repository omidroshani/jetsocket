"""Extended tests for transport layer covering uncovered paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jetsocket.exceptions import ConnectionError as WsConnectionError
from jetsocket.transport import AsyncTransport, BaseTransportConfig, SyncTransport
from jetsocket.types import Frame, Opcode


class TestAsyncTransportProperties:
    """Test AsyncTransport property accessors."""

    def test_uri_none_when_not_connected(self) -> None:
        """Test uri is None when not connected."""
        t = AsyncTransport()
        assert t.uri is None

    def test_close_code_none_when_not_connected(self) -> None:
        """Test close_code is None before close."""
        t = AsyncTransport()
        assert t.close_code is None

    def test_close_reason_empty_when_not_connected(self) -> None:
        """Test close_reason is empty before close."""
        t = AsyncTransport()
        assert t.close_reason == ""


class TestSyncTransportProperties:
    """Test SyncTransport property accessors."""

    def test_uri_none_when_not_connected(self) -> None:
        """Test uri is None when not connected."""
        t = SyncTransport()
        assert t.uri is None

    def test_close_code_none_when_not_connected(self) -> None:
        """Test close_code is None before close."""
        t = SyncTransport()
        assert t.close_code is None

    def test_close_reason_empty_when_not_connected(self) -> None:
        """Test close_reason is empty before close."""
        t = SyncTransport()
        assert t.close_reason == ""


class TestAsyncTransportSendErrors:
    """Test AsyncTransport send error paths."""

    async def test_send_when_not_connected_raises(self) -> None:
        """Test send raises when not connected."""
        t = AsyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.send(b"test")

    async def test_send_frame_when_not_connected_raises(self) -> None:
        """Test send_frame raises when not connected."""
        t = AsyncTransport()
        frame = Frame(opcode=Opcode.TEXT, payload=b"test")
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.send_frame(frame)

    async def test_recv_when_not_connected_raises(self) -> None:
        """Test recv raises when not connected."""
        t = AsyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.recv()

    async def test_send_binary_when_not_connected_raises(self) -> None:
        """Test send binary raises when not connected."""
        t = AsyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.send(b"test", binary=True)


class TestSyncTransportSendErrors:
    """Test SyncTransport send error paths."""

    def test_send_when_not_connected_raises(self) -> None:
        """Test send raises when not connected."""
        t = SyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            t.send(b"test")

    def test_send_frame_when_not_connected_raises(self) -> None:
        """Test send_frame raises when not connected."""
        t = SyncTransport()
        frame = Frame(opcode=Opcode.TEXT, payload=b"test")
        with pytest.raises((WsConnectionError, ConnectionError)):
            t.send_frame(frame)

    def test_recv_when_not_connected_raises(self) -> None:
        """Test recv raises when not connected."""
        t = SyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            t.recv()


class TestAsyncTransportDNS:
    """Test AsyncTransport DNS resolution edge cases."""

    async def test_dns_gaierror_raises_connection_error(self) -> None:
        """Test DNS resolution failure raises ConnectionError."""
        t = AsyncTransport(BaseTransportConfig(connect_timeout=5.0))
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.connect("ws://this-host-does-not-exist-12345.invalid/ws")

    async def test_connect_already_connected_raises(self) -> None:
        """Test connecting when already connected raises."""
        t = AsyncTransport()
        t._connected = True
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t.connect("ws://example.com/ws")


class TestAsyncTransportClose:
    """Test AsyncTransport close and cleanup."""

    async def test_close_transport_clears_state(self) -> None:
        """Test _close_transport clears all internal state."""
        t = AsyncTransport()
        t._asyncio_transport = MagicMock()
        t._asyncio_transport.close = MagicMock()
        t._protocol = MagicMock()
        t._parser = MagicMock()
        t._deflater = MagicMock()

        await t._close_transport()

        assert t._asyncio_transport is None
        assert t._protocol is None
        assert t._parser is None
        assert t._deflater is None

    async def test_close_when_not_connected(self) -> None:
        """Test close is safe when not connected."""
        t = AsyncTransport()
        await t.close()  # Should not raise

    async def test_context_manager(self) -> None:
        """Test async context manager."""
        async with AsyncTransport() as t:
            assert t is not None


class TestSyncTransportClose:
    """Test SyncTransport close and cleanup."""

    def test_close_socket_clears_state(self) -> None:
        """Test _close_socket clears internal state."""
        t = SyncTransport()
        t._socket = MagicMock()
        t._parser = MagicMock()
        t._deflater = MagicMock()
        t._selector = MagicMock()

        t._close_socket()

        assert t._socket is None
        assert t._parser is None
        assert t._deflater is None
        assert t._selector is None

    def test_context_manager(self) -> None:
        """Test sync context manager."""
        with SyncTransport() as t:
            assert t is not None


class TestBaseTransportConfig:
    """Test BaseTransportConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BaseTransportConfig()
        assert config.connect_timeout == 10.0
        assert config.read_timeout is None
        assert config.write_timeout is None
        assert config.max_frame_size == 16 * 1024 * 1024
        assert config.max_message_size == 64 * 1024 * 1024
        assert config.compression is True
        assert config.compression_threshold == 128
        assert config.origin is None

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = BaseTransportConfig(
            connect_timeout=5.0,
            compression_threshold=256,
            compression=False,
            origin="https://example.com",
        )
        assert config.connect_timeout == 5.0
        assert config.compression_threshold == 256
        assert config.compression is False
        assert config.origin == "https://example.com"


class TestAsyncTransportHandshakeErrors:
    """Test handshake error paths."""

    async def test_handshake_not_initialized_raises(self) -> None:
        """Test handshake when not initialized raises."""
        t = AsyncTransport()
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t._perform_handshake()

    async def test_handshake_not_initialized_protocol_raises(self) -> None:
        """Test handshake when protocol is not initialized raises."""
        t = AsyncTransport()
        t._uri = MagicMock()
        t._protocol = None
        t._asyncio_transport = None
        with pytest.raises((WsConnectionError, ConnectionError)):
            await t._perform_handshake()
