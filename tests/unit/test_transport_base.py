"""Tests for jetsocket.transport.base module."""

from __future__ import annotations

import ssl

from jetsocket.transport.base import (
    BaseTransportConfig,
    create_default_ssl_context,
)


class TestBaseTransportConfig:
    """Tests for BaseTransportConfig class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = BaseTransportConfig()
        assert config.connect_timeout == 10.0
        assert config.read_timeout is None
        assert config.write_timeout is None
        assert config.max_frame_size == 16 * 1024 * 1024
        assert config.max_message_size == 64 * 1024 * 1024
        assert config.ssl_context is None
        assert config.extra_headers == {}
        assert config.subprotocols == []
        assert config.compression is True
        assert config.origin is None

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        ssl_ctx = ssl.create_default_context()
        config = BaseTransportConfig(
            connect_timeout=30.0,
            read_timeout=60.0,
            write_timeout=30.0,
            max_frame_size=1024 * 1024,
            max_message_size=10 * 1024 * 1024,
            ssl_context=ssl_ctx,
            extra_headers={"Authorization": "Bearer token"},
            subprotocols=["graphql-ws"],
            compression=False,
            origin="https://example.com",
        )
        assert config.connect_timeout == 30.0
        assert config.read_timeout == 60.0
        assert config.write_timeout == 30.0
        assert config.max_frame_size == 1024 * 1024
        assert config.max_message_size == 10 * 1024 * 1024
        assert config.ssl_context is ssl_ctx
        assert config.extra_headers == {"Authorization": "Bearer token"}
        assert config.subprotocols == ["graphql-ws"]
        assert config.compression is False
        assert config.origin == "https://example.com"

    def test_extra_headers_default_mutable(self) -> None:
        """Test that extra_headers defaults are not shared."""
        config1 = BaseTransportConfig()
        config2 = BaseTransportConfig()
        config1.extra_headers["test"] = "value"
        assert "test" not in config2.extra_headers

    def test_subprotocols_default_mutable(self) -> None:
        """Test that subprotocols defaults are not shared."""
        config1 = BaseTransportConfig()
        config2 = BaseTransportConfig()
        config1.subprotocols.append("test")
        assert "test" not in config2.subprotocols


class TestCreateDefaultSslContext:
    """Tests for create_default_ssl_context function."""

    def test_verify_enabled(self) -> None:
        """Test SSL context with verification enabled."""
        ctx = create_default_ssl_context(verify=True)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_verify_disabled(self) -> None:
        """Test SSL context with verification disabled."""
        ctx = create_default_ssl_context(verify=False)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE
