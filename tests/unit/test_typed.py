"""Tests for TypedWebSocket."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestTypedWebSocketImport:
    """Tests for TypedWebSocket import behavior."""

    def test_import_without_pydantic_raises(self) -> None:
        """Test that importing without pydantic raises ImportError."""
        # Mock pydantic not being installed
        with patch.dict("sys.modules", {"pydantic": None}):
            # Force reimport
            import importlib

            from jetsocket import typed

            importlib.reload(typed)

            with pytest.raises(ImportError, match="pydantic is required"):
                typed.TypedWebSocket("wss://example.com/ws", MagicMock())


class TestTypedWebSocket:
    """Tests for TypedWebSocket."""

    def test_init(self) -> None:
        """Test basic initialization."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        assert ws.uri == "wss://example.com/ws"
        assert ws.message_type is TestMessage
        assert ws.strict is True
        assert ws.validation_errors == 0

    def test_init_non_strict(self) -> None:
        """Test initialization with strict=False."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage, strict=False)

        assert ws.strict is False

    def test_init_with_kwargs(self) -> None:
        """Test initialization with additional kwargs."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket(
            "wss://example.com/ws",
            TestMessage,
            reconnect=False,
            connect_timeout=5.0,
        )

        assert ws._reconnect_enabled is False

    def test_deserializer_validates_json(self) -> None:
        """Test that deserializer validates JSON against model."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str
            count: int

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        # Valid message
        result = ws._deserializer(b'{"value": "test", "count": 42}')
        assert result.value == "test"
        assert result.count == 42

    def test_deserializer_raises_on_invalid(self) -> None:
        """Test that deserializer raises ValidationError on invalid data."""
        pydantic = pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str
            count: int

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        # Invalid message (missing required field)
        with pytest.raises(pydantic.ValidationError):
            ws._deserializer(b'{"value": "test"}')

    def test_serializer_with_model(self) -> None:
        """Test that serializer works with Pydantic model."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str
            count: int

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        msg = TestMessage(value="test", count=42)
        result = ws._serializer(msg)

        assert b"test" in result
        assert b"42" in result

    def test_serializer_with_dict(self) -> None:
        """Test that serializer works with dict."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        result = ws._serializer({"value": "test", "count": 42})

        assert b"test" in result
        assert b"42" in result

    def test_message_type_property(self) -> None:
        """Test message_type property."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        assert ws.message_type is TestMessage


class TestTypedWebSocketWithNestedModels:
    """Tests for TypedWebSocket with nested Pydantic models."""

    def test_nested_model_deserialization(self) -> None:
        """Test deserializing nested models."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class InnerModel(BaseModel):
            value: str

        class OuterModel(BaseModel):
            inner: InnerModel
            count: int

        ws = TypedWebSocket("wss://example.com/ws", OuterModel)

        result = ws._deserializer(b'{"inner": {"value": "test"}, "count": 42}')

        assert result.inner.value == "test"
        assert result.count == 42

    def test_nested_model_serialization(self) -> None:
        """Test serializing nested models."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class InnerModel(BaseModel):
            value: str

        class OuterModel(BaseModel):
            inner: InnerModel
            count: int

        ws = TypedWebSocket("wss://example.com/ws", OuterModel)

        msg = OuterModel(inner=InnerModel(value="test"), count=42)
        result = ws._serializer(msg)

        assert b"test" in result
        assert b"42" in result


class TestTypedWebSocketWithAliases:
    """Tests for TypedWebSocket with field aliases."""

    def test_alias_deserialization(self) -> None:
        """Test deserializing with field aliases."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel, Field

        from jetsocket.typed import TypedWebSocket

        class TradeMessage(BaseModel):
            symbol: str = Field(alias="s")
            price: str = Field(alias="p")
            quantity: str = Field(alias="q")

        ws = TypedWebSocket("wss://example.com/ws", TradeMessage)

        result = ws._deserializer(b'{"s": "BTCUSDT", "p": "50000", "q": "0.5"}')

        assert result.symbol == "BTCUSDT"
        assert result.price == "50000"
        assert result.quantity == "0.5"


class TestTypedWebSocketIntegration:
    """Integration tests for TypedWebSocket."""

    def test_inherits_from_websocket_manager(self) -> None:
        """Test that TypedWebSocket inherits from WebSocketManager."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.manager import WebSocketManager
        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        assert isinstance(ws, WebSocketManager)

    def test_has_all_manager_methods(self) -> None:
        """Test that TypedWebSocket has all WebSocketManager methods."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMessage(BaseModel):
            value: str

        ws = TypedWebSocket("wss://example.com/ws", TestMessage)

        # Check for key methods
        assert hasattr(ws, "connect")
        assert hasattr(ws, "close")
        assert hasattr(ws, "send")
        assert hasattr(ws, "recv")
        assert hasattr(ws, "on")
        assert hasattr(ws, "stats")


class TestCreateTypedDeserializer:
    """Tests for create_typed_deserializer utility."""

    def test_create_deserializer(self) -> None:
        """Test creating a typed deserializer."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import create_typed_deserializer

        class TestMessage(BaseModel):
            value: str

        deserializer, _ = create_typed_deserializer(TestMessage)

        result = deserializer(b'{"value": "test"}')
        assert result.value == "test"

    def test_create_deserializer_import_error(self) -> None:
        """Test create_typed_deserializer raises ImportError without pydantic."""
        from jetsocket.typed import create_typed_deserializer

        with (
            patch.dict("sys.modules", {"pydantic": None}),
            pytest.raises(ImportError, match="pydantic is required"),
        ):
            create_typed_deserializer(MagicMock())
