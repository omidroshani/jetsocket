"""Exception hierarchy for WSFabric.

All exceptions inherit from WSFabricError, which itself inherits from Exception.
This allows catching all library exceptions with a single except clause.
"""

from __future__ import annotations


class WSFabricError(Exception):
    """Base exception for all WSFabric errors."""


class ConnectionError(WSFabricError):
    """Raised when a connection cannot be established or is lost unexpectedly.

    This includes network errors, DNS resolution failures, and unexpected
    socket closures.
    """


class ProtocolError(WSFabricError):
    """Raised when the WebSocket protocol is violated.

    This includes invalid frames, unexpected opcodes, and other protocol-level
    issues defined in RFC 6455.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """Initialize protocol error.

        Args:
            message: Human-readable error description.
            code: Optional WebSocket close code (1000-4999).
        """
        super().__init__(message)
        self.code = code


class HandshakeError(WSFabricError):
    """Raised when the WebSocket handshake fails.

    This includes HTTP upgrade failures, invalid Sec-WebSocket-Accept,
    and extension negotiation failures.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize handshake error.

        Args:
            message: Human-readable error description.
            status_code: HTTP status code received (if any).
            headers: HTTP response headers (if any).
        """
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


class CloseError(WSFabricError):
    """Raised when the WebSocket connection is closed with an error code.

    Normal closures (code 1000) do not raise this exception.
    """

    def __init__(
        self,
        message: str,
        *,
        code: int,
        reason: str = "",
    ) -> None:
        """Initialize close error.

        Args:
            message: Human-readable error description.
            code: WebSocket close code (1000-4999).
            reason: Close reason from the server.
        """
        super().__init__(message)
        self.code = code
        self.reason = reason

    @property
    def is_normal(self) -> bool:
        """Return True if this is a normal closure (code 1000)."""
        return self.code == 1000

    @property
    def is_going_away(self) -> bool:
        """Return True if the server is going away (code 1001)."""
        return self.code == 1001


class TimeoutError(WSFabricError):
    """Raised when an operation times out.

    This includes connection timeouts, read timeouts, and heartbeat timeouts.
    """

    def __init__(
        self,
        message: str,
        *,
        timeout: float,
        operation: str = "unknown",
    ) -> None:
        """Initialize timeout error.

        Args:
            message: Human-readable error description.
            timeout: The timeout value in seconds.
            operation: The operation that timed out.
        """
        super().__init__(message)
        self.timeout = timeout
        self.operation = operation


class BufferOverflowError(WSFabricError):
    """Raised when the message buffer overflows and policy is 'error'."""

    def __init__(
        self,
        message: str,
        *,
        capacity: int,
        current_size: int,
    ) -> None:
        """Initialize buffer overflow error.

        Args:
            message: Human-readable error description.
            capacity: Maximum buffer capacity.
            current_size: Current number of messages in buffer.
        """
        super().__init__(message)
        self.capacity = capacity
        self.current_size = current_size


class InvalidStateError(WSFabricError):
    """Raised when an operation is attempted in an invalid connection state.

    For example, sending a message before connecting.
    """

    def __init__(
        self,
        message: str,
        *,
        current_state: str,
        required_states: list[str] | None = None,
    ) -> None:
        """Initialize invalid state error.

        Args:
            message: Human-readable error description.
            current_state: The current connection state.
            required_states: States in which the operation is valid.
        """
        super().__init__(message)
        self.current_state = current_state
        self.required_states = required_states or []


class PoolExhaustedError(WSFabricError):
    """Raised when connection pool has no available connections.

    This occurs when all connections are in use and the acquire timeout
    has been exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        max_connections: int,
        timeout: float,
    ) -> None:
        """Initialize pool exhausted error.

        Args:
            message: Human-readable error description.
            max_connections: Maximum connections configured for the pool.
            timeout: The acquire timeout that was exceeded.
        """
        super().__init__(message)
        self.max_connections = max_connections
        self.timeout = timeout


class PoolClosedError(WSFabricError):
    """Raised when operating on a closed pool.

    This occurs when attempting to acquire a connection from a pool
    that has already been closed.
    """
