"""Type-safe WebSocket with Pydantic support for WSFabric.

This module provides TypedWebSocket, a WebSocketManager subclass that
automatically validates incoming messages using Pydantic models.
"""

from __future__ import annotations

import json
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

from wsfabric.manager import WebSocket

if TYPE_CHECKING:
    from pydantic import BaseModel  # type: ignore[import-not-found]

# Type variable for Pydantic models
T = TypeVar("T", bound="BaseModel")

logger = logging.getLogger(__name__)


class TypedWebSocket(WebSocket[T], Generic[T]):
    """WebSocket with typed messages via Pydantic.

    Provides automatic serialization/deserialization of messages
    using Pydantic models. Messages are validated on receive and
    serialized on send.

    Example:
        >>> from pydantic import BaseModel
        >>>
        >>> class TradeMessage(BaseModel):
        ...     symbol: str
        ...     price: float
        ...     quantity: float
        >>>
        >>> async with TypedWebSocket(
        ...     "wss://stream.example.com/ws", TradeMessage
        ... ) as ws:
        ...     async for trade in ws:  # trade is TradeMessage
        ...         print(f"{trade.symbol}: {trade.price}")

    Args:
        uri: WebSocket URI.
        message_type: Pydantic model class for incoming messages.
        strict: If True, raise ValidationError on invalid messages.
            If False, skip invalid messages with warning.
        **kwargs: Additional kwargs passed to WebSocketManager.

    Raises:
        ImportError: If pydantic is not installed.
    """

    def __init__(
        self,
        uri: str,
        message_type: type[T],
        *,
        strict: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize typed WebSocket.

        Args:
            uri: WebSocket URI.
            message_type: Pydantic model class for incoming messages.
            strict: If True, raise ValidationError on invalid messages.
            **kwargs: Additional kwargs passed to WebSocketManager.

        Raises:
            ImportError: If pydantic is not installed.
        """
        try:
            from pydantic import BaseModel  # noqa: PLC0415
        except ImportError as e:
            raise ImportError(
                "pydantic is required for TypedWebSocket. "
                "Install it with: pip install pydantic"
            ) from e

        self._message_type = message_type
        self._strict = strict
        self._validation_errors = 0

        # Set up deserializer
        def deserializer(data: bytes) -> T:
            return message_type.model_validate_json(data)  # type: ignore[no-any-return]

        # Set up serializer
        def serializer(msg: Any) -> bytes:
            if isinstance(msg, BaseModel):
                return msg.model_dump_json().encode("utf-8")  # type: ignore[no-any-return]
            # Allow raw dict/Any for flexibility
            return json.dumps(msg).encode("utf-8")

        super().__init__(
            uri,
            deserializer=deserializer,
            serializer=serializer,
            **kwargs,
        )

    @property
    def message_type(self) -> type[T]:
        """Get the message type class."""
        return self._message_type

    @property
    def strict(self) -> bool:
        """Check if strict mode is enabled."""
        return self._strict

    @property
    def validation_errors(self) -> int:
        """Get the count of validation errors (non-strict mode only)."""
        return self._validation_errors


def create_typed_deserializer(
    message_type: type[T],
    strict: bool = True,
) -> tuple[Any, int]:
    """Create a typed deserializer function.

    This is a utility function for creating custom deserializers
    that work with TypedWebSocket patterns.

    Args:
        message_type: Pydantic model class.
        strict: If True, raise on validation errors.

    Returns:
        A tuple of (deserializer function, error count ref).

    Raises:
        ImportError: If pydantic is not installed.
    """
    try:
        from pydantic import ValidationError  # noqa: PLC0415
    except ImportError as e:
        raise ImportError(
            "pydantic is required. Install it with: pip install pydantic"
        ) from e

    error_count = 0

    def deserializer(data: bytes) -> T:
        nonlocal error_count
        try:
            return message_type.model_validate_json(data)  # type: ignore[no-any-return]
        except ValidationError:
            error_count += 1
            if strict:
                raise
            logger.warning(
                "Message validation failed for %s: %s",
                message_type.__name__,
                data[:100],
            )
            raise

    return deserializer, error_count
