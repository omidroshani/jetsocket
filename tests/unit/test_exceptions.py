"""Tests for jetsocket.exceptions module."""

from __future__ import annotations

import pytest

from jetsocket.exceptions import (
    BufferOverflowError,
    CloseError,
    ConnectionError,
    HandshakeError,
    InvalidStateError,
    ProtocolError,
    TimeoutError,
    JetSocketError,
)


class TestExceptionHierarchy:
    """Tests for exception inheritance."""

    def test_all_inherit_from_base(self) -> None:
        """Test that all exceptions inherit from JetSocketError."""
        exceptions = [
            ConnectionError("test"),
            ProtocolError("test"),
            HandshakeError("test"),
            CloseError("test", code=1000),
            TimeoutError("test", timeout=5.0),
            BufferOverflowError("test", capacity=100, current_size=100),
            InvalidStateError("test", current_state="idle"),
        ]
        for exc in exceptions:
            assert isinstance(exc, JetSocketError)
            assert isinstance(exc, Exception)

    def test_catch_all_with_base(self) -> None:
        """Test that base exception catches all library exceptions."""
        with pytest.raises(JetSocketError):
            raise ConnectionError("connection failed")

        with pytest.raises(JetSocketError):
            raise ProtocolError("invalid frame")


class TestProtocolError:
    """Tests for ProtocolError."""

    def test_basic(self) -> None:
        """Test basic protocol error."""
        err = ProtocolError("Invalid opcode")
        assert str(err) == "Invalid opcode"
        assert err.code is None

    def test_with_code(self) -> None:
        """Test protocol error with code."""
        err = ProtocolError("Reserved bits set", code=1002)
        assert err.code == 1002


class TestHandshakeError:
    """Tests for HandshakeError."""

    def test_basic(self) -> None:
        """Test basic handshake error."""
        err = HandshakeError("Handshake failed")
        assert str(err) == "Handshake failed"
        assert err.status_code is None
        assert err.headers == {}

    def test_with_http_info(self) -> None:
        """Test handshake error with HTTP info."""
        err = HandshakeError(
            "HTTP 403 Forbidden",
            status_code=403,
            headers={"X-Error": "Auth required"},
        )
        assert err.status_code == 403
        assert err.headers == {"X-Error": "Auth required"}


class TestCloseError:
    """Tests for CloseError."""

    def test_basic(self) -> None:
        """Test basic close error."""
        err = CloseError("Connection closed", code=1001, reason="Going away")
        assert err.code == 1001
        assert err.reason == "Going away"

    def test_is_normal(self) -> None:
        """Test is_normal property."""
        normal = CloseError("Normal", code=1000)
        abnormal = CloseError("Error", code=1001)

        assert normal.is_normal
        assert not abnormal.is_normal

    def test_is_going_away(self) -> None:
        """Test is_going_away property."""
        going_away = CloseError("Going away", code=1001)
        other = CloseError("Error", code=1002)

        assert going_away.is_going_away
        assert not other.is_going_away


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_basic(self) -> None:
        """Test basic timeout error."""
        err = TimeoutError("Read timeout", timeout=30.0)
        assert err.timeout == 30.0
        assert err.operation == "unknown"

    def test_with_operation(self) -> None:
        """Test timeout error with operation."""
        err = TimeoutError("Connect timeout", timeout=10.0, operation="connect")
        assert err.timeout == 10.0
        assert err.operation == "connect"


class TestBufferOverflowError:
    """Tests for BufferOverflowError."""

    def test_basic(self) -> None:
        """Test buffer overflow error."""
        err = BufferOverflowError(
            "Buffer full",
            capacity=1000,
            current_size=1000,
        )
        assert err.capacity == 1000
        assert err.current_size == 1000


class TestInvalidStateError:
    """Tests for InvalidStateError."""

    def test_basic(self) -> None:
        """Test basic invalid state error."""
        err = InvalidStateError("Cannot send", current_state="disconnected")
        assert err.current_state == "disconnected"
        assert err.required_states == []

    def test_with_required_states(self) -> None:
        """Test invalid state error with required states."""
        err = InvalidStateError(
            "Cannot send",
            current_state="connecting",
            required_states=["connected"],
        )
        assert err.current_state == "connecting"
        assert err.required_states == ["connected"]
