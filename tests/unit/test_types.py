"""Tests for jetsocket.types module."""

from __future__ import annotations

import pytest

from jetsocket.types import CloseCode, Frame, Opcode


class TestOpcode:
    """Tests for Opcode enum."""

    def test_opcode_values(self) -> None:
        """Test opcode numeric values match RFC 6455."""
        assert Opcode.CONTINUATION == 0x0
        assert Opcode.TEXT == 0x1
        assert Opcode.BINARY == 0x2
        assert Opcode.CLOSE == 0x8
        assert Opcode.PING == 0x9
        assert Opcode.PONG == 0xA

    def test_is_control(self) -> None:
        """Test is_control property."""
        assert not Opcode.CONTINUATION.is_control
        assert not Opcode.TEXT.is_control
        assert not Opcode.BINARY.is_control
        assert Opcode.CLOSE.is_control
        assert Opcode.PING.is_control
        assert Opcode.PONG.is_control

    def test_is_data(self) -> None:
        """Test is_data property."""
        assert Opcode.CONTINUATION.is_data
        assert Opcode.TEXT.is_data
        assert Opcode.BINARY.is_data
        assert not Opcode.CLOSE.is_data
        assert not Opcode.PING.is_data
        assert not Opcode.PONG.is_data


class TestFrame:
    """Tests for Frame dataclass."""

    def test_frame_creation(self) -> None:
        """Test basic frame creation."""
        frame = Frame(opcode=Opcode.TEXT, payload=b"Hello")
        assert frame.opcode == Opcode.TEXT
        assert frame.payload == b"Hello"
        assert frame.fin is True
        assert frame.rsv1 is False

    def test_frame_immutable(self) -> None:
        """Test that frames are immutable."""
        frame = Frame(opcode=Opcode.TEXT, payload=b"Hello")
        with pytest.raises(AttributeError):
            frame.opcode = Opcode.BINARY  # type: ignore[misc]

    def test_is_text(self) -> None:
        """Test is_text property."""
        text_frame = Frame(opcode=Opcode.TEXT, payload=b"Hello")
        binary_frame = Frame(opcode=Opcode.BINARY, payload=b"\x00\x01")
        assert text_frame.is_text
        assert not binary_frame.is_text

    def test_is_binary(self) -> None:
        """Test is_binary property."""
        text_frame = Frame(opcode=Opcode.TEXT, payload=b"Hello")
        binary_frame = Frame(opcode=Opcode.BINARY, payload=b"\x00\x01")
        assert not text_frame.is_binary
        assert binary_frame.is_binary

    def test_is_control_frames(self) -> None:
        """Test is_close, is_ping, is_pong properties."""
        close_frame = Frame(opcode=Opcode.CLOSE, payload=b"\x03\xe8")
        ping_frame = Frame(opcode=Opcode.PING, payload=b"")
        pong_frame = Frame(opcode=Opcode.PONG, payload=b"")

        assert close_frame.is_close
        assert ping_frame.is_ping
        assert pong_frame.is_pong

    def test_as_text(self) -> None:
        """Test as_text method."""
        frame = Frame(opcode=Opcode.TEXT, payload=b"Hello, World!")
        assert frame.as_text() == "Hello, World!"

    def test_as_text_unicode(self) -> None:
        """Test as_text with unicode content."""
        frame = Frame(opcode=Opcode.TEXT, payload="Hello, 世界! 🌍".encode())
        assert frame.as_text() == "Hello, 世界! 🌍"

    def test_as_text_invalid_utf8(self) -> None:
        """Test as_text raises on invalid UTF-8."""
        frame = Frame(opcode=Opcode.TEXT, payload=b"\xff\xfe")
        with pytest.raises(UnicodeDecodeError):
            frame.as_text()

    def test_close_code(self) -> None:
        """Test close_code property."""
        # Normal close (code 1000)
        frame = Frame(opcode=Opcode.CLOSE, payload=b"\x03\xe8")
        assert frame.close_code == 1000

        # Going away (code 1001)
        frame = Frame(opcode=Opcode.CLOSE, payload=b"\x03\xe9")
        assert frame.close_code == 1001

        # No code
        frame = Frame(opcode=Opcode.CLOSE, payload=b"")
        assert frame.close_code is None

        # Non-close frame
        frame = Frame(opcode=Opcode.TEXT, payload=b"\x03\xe8")
        assert frame.close_code is None

    def test_close_reason(self) -> None:
        """Test close_reason property."""
        # With reason
        payload = b"\x03\xe8" + b"Normal closure"
        frame = Frame(opcode=Opcode.CLOSE, payload=payload)
        assert frame.close_reason == "Normal closure"

        # No reason
        frame = Frame(opcode=Opcode.CLOSE, payload=b"\x03\xe8")
        assert frame.close_reason == ""

        # Empty payload
        frame = Frame(opcode=Opcode.CLOSE, payload=b"")
        assert frame.close_reason == ""


class TestCloseCode:
    """Tests for CloseCode constants."""

    def test_standard_codes(self) -> None:
        """Test standard close code values."""
        assert CloseCode.NORMAL == 1000
        assert CloseCode.GOING_AWAY == 1001
        assert CloseCode.PROTOCOL_ERROR == 1002
        assert CloseCode.UNSUPPORTED_DATA == 1003
        assert CloseCode.INVALID_PAYLOAD == 1007
        assert CloseCode.POLICY_VIOLATION == 1008
        assert CloseCode.MESSAGE_TOO_BIG == 1009
        assert CloseCode.INTERNAL_ERROR == 1011
