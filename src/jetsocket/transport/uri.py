"""WebSocket URI parsing and validation.

This module handles parsing of WebSocket URIs (ws:// and wss://) and
extracts all necessary components for establishing connections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True, slots=True)
class WebSocketURI:
    """Parsed WebSocket URI.

    Attributes:
        scheme: The URI scheme ("ws" or "wss").
        host: The hostname.
        port: The port number.
        path: The request path (defaults to "/").
        query: The query string (without leading "?").
        fragment: The fragment identifier (without leading "#").
        userinfo: Optional username:password component.
    """

    scheme: Literal["ws", "wss"]
    host: str
    port: int
    path: str
    query: str | None
    fragment: str | None
    userinfo: str | None

    @property
    def is_secure(self) -> bool:
        """Return True if this is a secure WebSocket connection (wss://)."""
        return self.scheme == "wss"

    @property
    def origin(self) -> str:
        """Return the origin for the Origin header.

        The origin uses https:// for wss:// and http:// for ws://.
        """
        http_scheme = "https" if self.is_secure else "http"
        default_port = 443 if self.is_secure else 80
        if self.port == default_port:
            return f"{http_scheme}://{self.host}"
        return f"{http_scheme}://{self.host}:{self.port}"

    @property
    def resource_name(self) -> str:
        """Return the resource name for the HTTP request line.

        This is the path with query string appended if present.
        """
        if self.query:
            return f"{self.path}?{self.query}"
        return self.path

    @property
    def host_header(self) -> str:
        """Return the value for the Host header.

        Includes port only if non-default.
        """
        default_port = 443 if self.is_secure else 80
        if self.port == default_port:
            return self.host
        return f"{self.host}:{self.port}"

    def with_path(self, path: str) -> WebSocketURI:
        """Return a new URI with a different path."""
        return WebSocketURI(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=path,
            query=self.query,
            fragment=self.fragment,
            userinfo=self.userinfo,
        )

    def with_query(self, query: str | None) -> WebSocketURI:
        """Return a new URI with a different query string."""
        return WebSocketURI(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.path,
            query=query,
            fragment=self.fragment,
            userinfo=self.userinfo,
        )

    @property
    def query_params(self) -> dict[str, list[str]]:
        """Parse query string into a dictionary."""
        if not self.query:
            return {}
        return parse_qs(self.query)

    def __str__(self) -> str:
        """Return the URI as a string."""
        uri = f"{self.scheme}://"
        if self.userinfo:
            uri += f"{self.userinfo}@"
        uri += self.host_header
        uri += self.resource_name
        if self.fragment:
            uri += f"#{self.fragment}"
        return uri


def parse_uri(uri: str) -> WebSocketURI:
    """Parse a WebSocket URI string.

    Args:
        uri: A WebSocket URI (ws:// or wss://).

    Returns:
        A parsed WebSocketURI object.

    Raises:
        ValueError: If the URI is invalid or has an unsupported scheme.

    Example:
        >>> uri = parse_uri("wss://example.com:8080/ws?token=abc")
        >>> uri.host
        'example.com'
        >>> uri.port
        8080
        >>> uri.is_secure
        True
    """
    parsed = urlparse(uri)

    # Validate scheme
    if parsed.scheme not in ("ws", "wss"):
        msg = f"Invalid WebSocket scheme: {parsed.scheme!r}. Must be 'ws' or 'wss'"
        raise ValueError(msg)

    scheme: Literal["ws", "wss"] = "wss" if parsed.scheme == "wss" else "ws"

    # Validate host
    if not parsed.hostname:
        msg = f"Missing host in URI: {uri}"
        raise ValueError(msg)

    host = parsed.hostname

    # Determine port (use parsed port or default based on scheme)
    port = parsed.port if parsed.port is not None else (443 if scheme == "wss" else 80)

    # Validate port range
    if not (0 < port <= 65535):
        msg = f"Invalid port: {port}"
        raise ValueError(msg)

    # Extract path (default to "/")
    path = parsed.path or "/"

    # Extract optional components
    query = parsed.query or None
    fragment = parsed.fragment or None

    # Extract userinfo (username:password)
    userinfo: str | None = None
    if parsed.username:
        if parsed.password:
            userinfo = f"{parsed.username}:{parsed.password}"
        else:
            userinfo = parsed.username

    return WebSocketURI(
        scheme=scheme,
        host=host,
        port=port,
        path=path,
        query=query,
        fragment=fragment,
        userinfo=userinfo,
    )
