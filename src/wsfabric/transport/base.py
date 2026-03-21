"""Base transport protocol for WSFabric.

This module defines the abstract interface that all transports must implement,
ensuring consistency between async and sync implementations.
"""

from __future__ import annotations

import ssl
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from wsfabric.types import Frame


@runtime_checkable
class TransportProtocol(Protocol):
    """Protocol defining the transport interface.

    This protocol is used for type checking to ensure both async and sync
    transports provide the same core functionality.
    """

    @property
    def is_connected(self) -> bool:
        """Return True if the transport is currently connected."""
        ...

    @property
    def is_closing(self) -> bool:
        """Return True if the transport is in the process of closing."""
        ...


class BaseTransportConfig:
    """Configuration shared by all transports.

    Attributes:
        connect_timeout: Timeout for establishing connection in seconds.
        read_timeout: Timeout for read operations in seconds.
        write_timeout: Timeout for write operations in seconds.
        max_frame_size: Maximum size of a single frame in bytes.
        max_message_size: Maximum size of an assembled message in bytes.
        ssl_context: Optional SSL context for secure connections.
        extra_headers: Additional headers to send during handshake.
        subprotocols: List of subprotocols to request.
        compression: Whether to request permessage-deflate compression.
        origin: Origin header value for the handshake.
    """

    __slots__ = (
        "compression",
        "connect_timeout",
        "extra_headers",
        "max_frame_size",
        "max_message_size",
        "origin",
        "read_timeout",
        "ssl_context",
        "subprotocols",
        "write_timeout",
    )

    def __init__(
        self,
        *,
        connect_timeout: float = 10.0,
        read_timeout: float | None = None,
        write_timeout: float | None = None,
        max_frame_size: int = 16 * 1024 * 1024,
        max_message_size: int = 64 * 1024 * 1024,
        ssl_context: ssl.SSLContext | None = None,
        extra_headers: dict[str, str] | None = None,
        subprotocols: list[str] | None = None,
        compression: bool = True,
        origin: str | None = None,
    ) -> None:
        """Initialize transport configuration.

        Args:
            connect_timeout: Timeout for establishing connection.
            read_timeout: Timeout for read operations (None = no timeout).
            write_timeout: Timeout for write operations (None = no timeout).
            max_frame_size: Maximum size of a single frame.
            max_message_size: Maximum size of an assembled message.
            ssl_context: SSL context for secure connections.
            extra_headers: Additional headers for handshake.
            subprotocols: List of subprotocols to request.
            compression: Whether to request compression.
            origin: Origin header value.
        """
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.max_frame_size = max_frame_size
        self.max_message_size = max_message_size
        self.ssl_context = ssl_context
        self.extra_headers = extra_headers or {}
        self.subprotocols = subprotocols or []
        self.compression = compression
        self.origin = origin


def create_default_ssl_context(*, verify: bool = True) -> ssl.SSLContext:
    """Create a default SSL context for secure WebSocket connections.

    Args:
        verify: Whether to verify server certificates.

    Returns:
        A configured SSL context.
    """
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


class AbstractTransport(ABC):
    """Abstract base class for WebSocket transports.

    This class defines the interface that both async and sync transports
    must implement. It handles common setup and provides shared utilities.
    """

    def __init__(self, config: BaseTransportConfig | None = None) -> None:
        """Initialize the transport.

        Args:
            config: Transport configuration. Uses defaults if not provided.
        """
        self._config = config or BaseTransportConfig()
        self._connected = False
        self._closing = False
        self._subprotocol: str | None = None
        self._extensions: list[str] = []

    @property
    def config(self) -> BaseTransportConfig:
        """Return the transport configuration."""
        return self._config

    @property
    def is_connected(self) -> bool:
        """Return True if the transport is currently connected."""
        return self._connected

    @property
    def is_closing(self) -> bool:
        """Return True if the transport is in the process of closing."""
        return self._closing

    @property
    def subprotocol(self) -> str | None:
        """Return the negotiated subprotocol, if any."""
        return self._subprotocol

    @property
    def extensions(self) -> list[str]:
        """Return the negotiated extensions."""
        return self._extensions.copy()

    @abstractmethod
    def _send_frame(self, frame: Frame) -> None:
        """Send a frame over the transport.

        Args:
            frame: The frame to send.
        """
        ...

    @abstractmethod
    def _recv_frame(self) -> Frame:
        """Receive a frame from the transport.

        Returns:
            The received frame.
        """
        ...
