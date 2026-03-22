"""I/O tests for SyncTransport using the live echo server.

Covers the blocking I/O paths in transport/_sync.py that require
a real WebSocket server.
"""

from __future__ import annotations

import pytest

from jetsocket.transport import BaseTransportConfig, SyncTransport


class TestSyncTransportIO:
    """Test SyncTransport I/O paths with a live server."""

    def test_connect_send_recv(self, live_server_url: str) -> None:
        """Test basic connect, send, receive."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            assert transport.is_connected
            transport.send("Hello!")
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"Hello!"
        finally:
            transport.close()
        assert not transport.is_connected

    def test_send_binary(self, live_server_url: str) -> None:
        """Test binary send/recv."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            transport.send(b"\x00\x01\x02\x03", binary=True)
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"\x00\x01\x02\x03"
        finally:
            transport.close()

    def test_send_infers_text(self, live_server_url: str) -> None:
        """Test send infers text opcode from string."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            transport.send("text message")
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"text message"
        finally:
            transport.close()

    def test_send_infers_binary(self, live_server_url: str) -> None:
        """Test send infers binary opcode from bytes."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            transport.send(b"\xff\xfe", binary=None)
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"\xff\xfe"
        finally:
            transport.close()

    def test_send_explicit_binary_flag(self, live_server_url: str) -> None:
        """Test send with explicit binary=False."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            transport.send("text-explicit", binary=False)
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"text-explicit"
        finally:
            transport.close()

    def test_multiple_messages(self, live_server_url: str) -> None:
        """Test multiple message exchange."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            for i in range(20):
                transport.send(f"msg-{i}")
                frame = transport.recv(timeout=5.0)
                assert frame.payload.decode("utf-8") == f"msg-{i}"
        finally:
            transport.close()

    def test_properties_when_connected(self, live_server_url: str) -> None:
        """Test all property accessors when connected."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            assert transport.uri is not None
            assert transport.is_connected is True
            assert transport.close_code is None
            assert transport.close_reason == ""
        finally:
            transport.close()

    def test_large_message(self, live_server_url: str) -> None:
        """Test sending a large message."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            payload = "x" * 100_000
            transport.send(payload)
            frame = transport.recv(timeout=5.0)
            assert len(frame.payload) == 100_000
        finally:
            transport.close()

    def test_close_graceful(self, live_server_url: str) -> None:
        """Test graceful close."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        transport.send("test")
        transport.recv(timeout=5.0)
        transport.close()
        assert not transport.is_connected

    def test_close_idempotent(self, live_server_url: str) -> None:
        """Test close can be called multiple times."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        transport.close()
        transport.close()  # Should not raise

    def test_context_manager(self, live_server_url: str) -> None:
        """Test context manager auto-closes."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        with SyncTransport(config) as transport:
            transport.connect(live_server_url)
            transport.send("ctx")
            frame = transport.recv(timeout=5.0)
            assert frame.payload == b"ctx"

    def test_already_connected_raises(self, live_server_url: str) -> None:
        """Test connecting when already connected raises."""
        config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
        transport = SyncTransport(config)
        transport.connect(live_server_url)
        try:
            with pytest.raises(Exception, match=r"already connected"):
                transport.connect(live_server_url)
        finally:
            transport.close()
