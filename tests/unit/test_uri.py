"""Tests for wsfabric.transport.uri module."""

from __future__ import annotations

import pytest

from wsfabric.transport.uri import WebSocketURI, parse_uri


class TestParseUri:
    """Tests for parse_uri function."""

    def test_basic_ws(self) -> None:
        """Test parsing basic ws:// URI."""
        uri = parse_uri("ws://example.com/ws")
        assert uri.scheme == "ws"
        assert uri.host == "example.com"
        assert uri.port == 80
        assert uri.path == "/ws"
        assert uri.is_secure is False

    def test_basic_wss(self) -> None:
        """Test parsing basic wss:// URI."""
        uri = parse_uri("wss://example.com/ws")
        assert uri.scheme == "wss"
        assert uri.host == "example.com"
        assert uri.port == 443
        assert uri.path == "/ws"
        assert uri.is_secure is True

    def test_custom_port(self) -> None:
        """Test parsing URI with custom port."""
        uri = parse_uri("ws://example.com:8080/ws")
        assert uri.port == 8080

        uri = parse_uri("wss://example.com:9443/ws")
        assert uri.port == 9443

    def test_default_path(self) -> None:
        """Test that path defaults to / when not specified."""
        uri = parse_uri("ws://example.com")
        assert uri.path == "/"

    def test_query_string(self) -> None:
        """Test parsing URI with query string."""
        uri = parse_uri("wss://example.com/ws?token=abc&id=123")
        assert uri.query == "token=abc&id=123"
        assert uri.query_params == {"token": ["abc"], "id": ["123"]}

    def test_fragment(self) -> None:
        """Test parsing URI with fragment."""
        uri = parse_uri("ws://example.com/ws#section")
        assert uri.fragment == "section"

    def test_userinfo(self) -> None:
        """Test parsing URI with userinfo."""
        uri = parse_uri("ws://user:pass@example.com/ws")
        assert uri.userinfo == "user:pass"

        uri = parse_uri("ws://user@example.com/ws")
        assert uri.userinfo == "user"

    def test_invalid_scheme(self) -> None:
        """Test that invalid schemes raise ValueError."""
        with pytest.raises(ValueError, match="Invalid WebSocket scheme"):
            parse_uri("http://example.com/ws")

        with pytest.raises(ValueError, match="Invalid WebSocket scheme"):
            parse_uri("https://example.com/ws")

    def test_missing_host(self) -> None:
        """Test that missing host raises ValueError."""
        with pytest.raises(ValueError, match="Missing host"):
            parse_uri("ws:///path")

    def test_ipv4_host(self) -> None:
        """Test parsing URI with IPv4 host."""
        uri = parse_uri("ws://192.168.1.1:8080/ws")
        assert uri.host == "192.168.1.1"
        assert uri.port == 8080

    def test_localhost(self) -> None:
        """Test parsing localhost URI."""
        uri = parse_uri("ws://localhost:3000/ws")
        assert uri.host == "localhost"
        assert uri.port == 3000


class TestWebSocketURI:
    """Tests for WebSocketURI dataclass."""

    def test_origin_ws(self) -> None:
        """Test origin for ws:// URI."""
        uri = WebSocketURI(
            scheme="ws",
            host="example.com",
            port=80,
            path="/ws",
            query=None,
            fragment=None,
            userinfo=None,
        )
        assert uri.origin == "http://example.com"

    def test_origin_wss(self) -> None:
        """Test origin for wss:// URI."""
        uri = WebSocketURI(
            scheme="wss",
            host="example.com",
            port=443,
            path="/ws",
            query=None,
            fragment=None,
            userinfo=None,
        )
        assert uri.origin == "https://example.com"

    def test_origin_custom_port(self) -> None:
        """Test origin includes port when non-default."""
        uri = WebSocketURI(
            scheme="wss",
            host="example.com",
            port=8443,
            path="/ws",
            query=None,
            fragment=None,
            userinfo=None,
        )
        assert uri.origin == "https://example.com:8443"

    def test_resource_name(self) -> None:
        """Test resource_name property."""
        uri = WebSocketURI(
            scheme="wss",
            host="example.com",
            port=443,
            path="/ws",
            query="token=abc",
            fragment=None,
            userinfo=None,
        )
        assert uri.resource_name == "/ws?token=abc"

        uri = uri.with_query(None)
        assert uri.resource_name == "/ws"

    def test_host_header_default_port(self) -> None:
        """Test host_header excludes default port."""
        uri = parse_uri("wss://example.com/ws")
        assert uri.host_header == "example.com"

        uri = parse_uri("ws://example.com/ws")
        assert uri.host_header == "example.com"

    def test_host_header_custom_port(self) -> None:
        """Test host_header includes custom port."""
        uri = parse_uri("wss://example.com:8443/ws")
        assert uri.host_header == "example.com:8443"

    def test_with_path(self) -> None:
        """Test with_path creates new URI."""
        uri = parse_uri("wss://example.com/ws")
        new_uri = uri.with_path("/other")
        assert new_uri.path == "/other"
        assert uri.path == "/ws"  # Original unchanged

    def test_with_query(self) -> None:
        """Test with_query creates new URI."""
        uri = parse_uri("wss://example.com/ws")
        new_uri = uri.with_query("token=xyz")
        assert new_uri.query == "token=xyz"
        assert uri.query is None  # Original unchanged

    def test_str(self) -> None:
        """Test string representation."""
        uri = parse_uri("wss://example.com:8443/ws?token=abc")
        assert str(uri) == "wss://example.com:8443/ws?token=abc"

        uri = parse_uri("ws://user:pass@example.com/ws")
        assert str(uri) == "ws://user:pass@example.com/ws"

    def test_immutable(self) -> None:
        """Test that URI is immutable."""
        uri = parse_uri("wss://example.com/ws")
        with pytest.raises(AttributeError):
            uri.host = "other.com"  # type: ignore[misc]
