"""Extended tests for TypedWebSocket covering typed.py paths.

Tests the import error path and create_typed_deserializer without pydantic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestTypedWebSocketImportError:
    """Test TypedWebSocket when pydantic is not available."""

    def test_typed_websocket_import_error(self) -> None:
        """Test TypedWebSocket raises ImportError without pydantic."""
        with patch.dict("sys.modules", {"pydantic": None}):
            from jetsocket.typed import TypedWebSocket

            with pytest.raises(ImportError, match=r"pydantic"):
                TypedWebSocket("ws://example.com/ws", MagicMock())

    def test_create_typed_deserializer_import_error(self) -> None:
        """Test create_typed_deserializer raises ImportError without pydantic."""
        from jetsocket.typed import create_typed_deserializer

        with (
            patch.dict("sys.modules", {"pydantic": None}),
            pytest.raises(ImportError, match=r"pydantic"),
        ):
            create_typed_deserializer(MagicMock())


class TestTypedWebSocketWithPydantic:
    """Test TypedWebSocket with pydantic available."""

    def test_init_creates_manager(self) -> None:
        """Test TypedWebSocket init creates a WebSocketManager."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg)
        assert ws._message_type is TestMsg
        assert ws._strict is True

    def test_init_non_strict(self) -> None:
        """Test TypedWebSocket with strict=False."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg, strict=False)
        assert ws._strict is False

    def test_deserializer_validates(self) -> None:
        """Test the internal deserializer validates JSON."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg)
        # Access the deserializer directly
        result = ws._deserializer(b'{"value": "hello"}')
        assert result.value == "hello"

    def test_serializer_with_model(self) -> None:
        """Test the internal serializer with a Pydantic model."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg)
        msg = TestMsg(value="test")
        result = ws._serializer(msg)
        assert b"test" in result

    def test_serializer_with_dict(self) -> None:
        """Test the internal serializer with a plain dict."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg)
        result = ws._serializer({"key": "val"})
        assert b"key" in result

    def test_message_type_property(self) -> None:
        """Test message_type property."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import TypedWebSocket

        class TestMsg(BaseModel):
            value: str

        ws = TypedWebSocket("ws://example.com/ws", TestMsg)
        assert ws.message_type is TestMsg

    def test_create_typed_deserializer(self) -> None:
        """Test create_typed_deserializer function."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import create_typed_deserializer

        class TestMsg(BaseModel):
            value: str

        deserializer, _error_count = create_typed_deserializer(TestMsg)
        result = deserializer(b'{"value": "test"}')
        assert result.value == "test"

    def test_create_typed_deserializer_strict_error(self) -> None:
        """Test strict deserializer raises on invalid data."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel, ValidationError

        from jetsocket.typed import create_typed_deserializer

        class TestMsg(BaseModel):
            value: int

        deserializer, _error_count = create_typed_deserializer(
            TestMsg, strict=True
        )
        with pytest.raises(ValidationError):
            deserializer(b'{"value": "not_an_int"}')

    def test_create_typed_deserializer_non_strict(self) -> None:
        """Test non-strict deserializer returns None on invalid data."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from jetsocket.typed import create_typed_deserializer

        class TestMsg(BaseModel):
            value: int

        deserializer, error_count = create_typed_deserializer(
            TestMsg, strict=False
        )
        result = deserializer(b'{"value": "not_an_int"}')
        assert result is None
        assert error_count() == 1
