"""Transport layer for JetSocket.

This module provides the I/O abstractions for WebSocket connections,
with implementations for both async and sync usage patterns.
"""

from __future__ import annotations

from jetsocket.transport._async import AsyncTransport
from jetsocket.transport._sync import SyncTransport
from jetsocket.transport.base import BaseTransportConfig, create_default_ssl_context
from jetsocket.transport.uri import WebSocketURI, parse_uri

__all__ = [
    "AsyncTransport",
    "BaseTransportConfig",
    "SyncTransport",
    "WebSocketURI",
    "create_default_ssl_context",
    "parse_uri",
]
