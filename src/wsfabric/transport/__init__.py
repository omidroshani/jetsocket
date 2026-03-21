"""Transport layer for WSFabric.

This module provides the I/O abstractions for WebSocket connections,
with implementations for both async and sync usage patterns.
"""

from __future__ import annotations

from wsfabric.transport._async import AsyncTransport
from wsfabric.transport._sync import SyncTransport
from wsfabric.transport.base import BaseTransportConfig, create_default_ssl_context
from wsfabric.transport.uri import WebSocketURI, parse_uri

__all__ = [
    "AsyncTransport",
    "BaseTransportConfig",
    "SyncTransport",
    "WebSocketURI",
    "create_default_ssl_context",
    "parse_uri",
]
