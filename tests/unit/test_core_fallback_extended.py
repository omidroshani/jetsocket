"""Extended tests for the pure-Python fallback module.

Tests the fallback RingBuffer, Deflater, handshake parsing,
frame validation, and utility functions directly.
"""

from __future__ import annotations

import pytest

from wsfabric._core import (
    Deflater,
    Frame,
    FrameParser,
    Handshake,
    Opcode,
    OverflowPolicy,
    RingBuffer,
    apply_mask,
    generate_key,
    parse_deflate_params,
    validate_accept,
    validate_utf8,
)


class TestFallbackRingBuffer:
    """Tests for the pure-Python RingBuffer."""

    def test_push_pop_basic(self) -> None:
        """Test basic push and pop."""
        buf = RingBuffer(5, "drop_oldest")
        buf.push("a")
        buf.push("b")
        assert buf.pop() == "a"
        assert buf.pop() == "b"
        assert buf.pop() is None

    def test_drop_oldest_policy(self) -> None:
        """Test drop_oldest overflow policy."""
        buf = RingBuffer(3, "drop_oldest")
        for i in range(5):
            buf.push(i)
        assert len(buf) == 3
        assert buf.pop() == 2  # oldest (0, 1) were dropped
        assert buf.total_dropped == 2

    def test_drop_newest_policy(self) -> None:
        """Test drop_newest overflow policy."""
        buf = RingBuffer(3, "drop_newest")
        for i in range(5):
            buf.push(i)
        assert len(buf) == 3
        # Newest (3, 4) should have been rejected
        assert buf.pop() == 0
        assert buf.total_dropped == 2

    def test_error_policy(self) -> None:
        """Test error overflow policy raises."""
        buf = RingBuffer(2, "error")
        buf.push("a")
        buf.push("b")
        with pytest.raises(Exception):
            buf.push("c")

    def test_drain(self) -> None:
        """Test draining all items."""
        buf = RingBuffer(10, "drop_oldest")
        for i in range(5):
            buf.push(i)
        items = buf.drain()
        assert items == [0, 1, 2, 3, 4]
        assert len(buf) == 0

    def test_drain_with_sequences(self) -> None:
        """Test draining with sequence IDs."""
        buf = RingBuffer(10, "drop_oldest")
        buf.push("a", "seq-1")
        buf.push("b", "seq-2")
        items = buf.drain_with_sequences()
        assert len(items) == 2
        assert items[0] == ("a", "seq-1")
        assert items[1] == ("b", "seq-2")

    def test_peek(self) -> None:
        """Test peeking without removing."""
        buf = RingBuffer(5, "drop_oldest")
        buf.push("x")
        assert buf.peek() == "x"
        assert len(buf) == 1  # Not removed

    def test_clear(self) -> None:
        """Test clearing the buffer."""
        buf = RingBuffer(5, "drop_oldest")
        for i in range(5):
            buf.push(i)
        buf.clear()
        assert len(buf) == 0
        assert buf.is_empty

    def test_properties(self) -> None:
        """Test buffer properties."""
        buf = RingBuffer(10, "drop_oldest")
        assert buf.capacity == 10
        assert buf.is_empty
        assert not buf.is_full
        buf.push("a")
        assert not buf.is_empty
        assert buf.fill_ratio == pytest.approx(0.1)

    def test_reset_dropped_counter(self) -> None:
        """Test resetting the dropped counter."""
        buf = RingBuffer(2, "drop_oldest")
        for i in range(5):
            buf.push(i)
        assert buf.total_dropped == 3
        buf.reset_dropped_counter()
        assert buf.total_dropped == 0

    def test_len_and_bool(self) -> None:
        """Test __len__ and __bool__."""
        buf = RingBuffer(5, "drop_oldest")
        assert len(buf) == 0
        assert not buf
        buf.push("x")
        assert len(buf) == 1
        assert buf

    def test_wraparound(self) -> None:
        """Test circular buffer wraparound."""
        buf = RingBuffer(3, "drop_oldest")
        buf.push(1)
        buf.push(2)
        buf.push(3)
        buf.pop()  # Remove 1
        buf.push(4)  # Should wrap around
        assert buf.drain() == [2, 3, 4]

    def test_repr(self) -> None:
        """Test RingBuffer repr."""
        buf = RingBuffer(5, "drop_oldest")
        r = repr(buf)
        assert "5" in r or "RingBuffer" in r or "ring" in r.lower()


class TestFallbackFrameParser:
    """Tests for fallback frame parser edge cases."""

    def test_rsv2_rejected(self) -> None:
        """Test RSV2 bit causes error."""
        parser = FrameParser()
        data = bytes([0xA1, 0x05]) + b"Hello"  # RSV2 set
        with pytest.raises(ValueError, match=r"[Rr]eserved"):
            parser.feed(data)

    def test_rsv3_rejected(self) -> None:
        """Test RSV3 bit causes error."""
        parser = FrameParser()
        data = bytes([0x91, 0x05]) + b"Hello"  # RSV3 set
        with pytest.raises(ValueError, match=r"[Rr]eserved"):
            parser.feed(data)

    def test_control_frame_too_large(self) -> None:
        """Test control frame > 125 bytes rejected."""
        parser = FrameParser()
        import struct

        header = bytes([0x89, 0x7E]) + struct.pack(">H", 130)
        payload = b"\x00" * 130
        with pytest.raises(ValueError, match=r"[Cc]ontrol"):
            parser.feed(header + payload)

    def test_fragmented_control_rejected(self) -> None:
        """Test fragmented control frame rejected."""
        parser = FrameParser()
        data = bytes([0x09, 0x05]) + b"Hello"  # Ping with FIN=0
        with pytest.raises(ValueError, match=r"[Ff]ragment"):
            parser.feed(data)

    def test_invalid_opcode(self) -> None:
        """Test invalid opcode rejected."""
        parser = FrameParser()
        data = bytes([0x83, 0x01, 0x00])  # Opcode 3
        with pytest.raises(ValueError, match=r"[Oo]pcode|[Ii]nvalid"):
            parser.feed(data)

    def test_max_frame_size(self) -> None:
        """Test frame size limit."""
        parser = FrameParser(max_frame_size=100)
        import struct

        header = bytes([0x81, 0x7E]) + struct.pack(">H", 200)
        payload = b"\x00" * 200
        with pytest.raises(ValueError, match=r"[Tt]oo [Ll]arge|[Ff]rame"):
            parser.feed(header + payload)

    def test_extended_length_16bit(self) -> None:
        """Test 16-bit extended length parsing."""
        parser = FrameParser()
        import struct

        payload = b"x" * 200
        header = bytes([0x81, 0x7E]) + struct.pack(">H", 200)
        frames, _consumed = parser.feed(header + payload)
        assert len(frames) == 1
        assert len(frames[0].payload) == 200

    def test_encode_with_rsv1(self) -> None:
        """Test encoding with RSV1 flag."""
        parser = FrameParser()
        encoded = parser.encode(Opcode.TEXT, b"test", mask=False, fin=True, rsv1=True)
        assert encoded[0] & 0x40, "RSV1 bit not set"

    def test_reset(self) -> None:
        """Test parser reset."""
        parser = FrameParser()
        parser.feed(bytes([0x81]))  # Incomplete
        parser.reset()
        data = bytes([0x81, 0x02]) + b"OK"
        frames, _ = parser.feed(data)
        assert len(frames) == 1

    def test_masked_frame_parsing(self) -> None:
        """Test parsing a masked frame."""
        parser = FrameParser()
        mask = bytes([0x37, 0xFA, 0x21, 0x3D])
        payload = b"Hello"
        masked_payload = apply_mask(payload, mask)
        data = bytes([0x81, 0x85]) + mask + masked_payload
        frames, _ = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].payload == payload


class TestFallbackHandshake:
    """Tests for fallback handshake parsing."""

    def _build_valid_response(self, key: str) -> bytes:
        """Build a valid 101 response for the given key."""
        import base64
        import hashlib

        guid = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        sha1 = hashlib.sha1()
        sha1.update(key.encode("ascii"))
        sha1.update(guid)
        accept = base64.b64encode(sha1.digest()).decode("ascii")

        return (
            f"HTTP/1.1 101 Switching Protocols\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            f"\r\n"
        ).encode()

    def test_successful_handshake(self) -> None:
        """Test successful handshake parsing."""
        hs = Handshake("example.com", "/ws")
        response = self._build_valid_response(hs.key)
        result = hs.parse_response(response)
        assert result.status == 101
        assert result.subprotocol is None

    def test_handshake_with_subprotocol(self) -> None:
        """Test handshake with subprotocol."""
        hs = Handshake("example.com", "/ws", subprotocols=["graphql-ws"])
        response = self._build_valid_response(hs.key)
        # Add subprotocol header
        response = response.replace(
            b"\r\n\r\n",
            b"\r\nSec-WebSocket-Protocol: graphql-ws\r\n\r\n",
        )
        result = hs.parse_response(response)
        assert result.subprotocol == "graphql-ws"

    def test_handshake_with_extensions(self) -> None:
        """Test handshake with extensions."""
        hs = Handshake("example.com", "/ws", extensions=["permessage-deflate"])
        response = self._build_valid_response(hs.key)
        response = response.replace(
            b"\r\n\r\n",
            b"\r\nSec-WebSocket-Extensions: permessage-deflate\r\n\r\n",
        )
        result = hs.parse_response(response)
        assert len(result.extensions) > 0

    def test_non_101_rejected(self) -> None:
        """Test non-101 response rejected."""
        hs = Handshake("example.com", "/ws")
        response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"
        with pytest.raises(ValueError, match=r"403"):
            hs.parse_response(response)

    def test_invalid_accept(self) -> None:
        """Test invalid accept value rejected."""
        hs = Handshake("example.com", "/ws")
        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: WRONG\r\n"
            b"\r\n"
        )
        with pytest.raises(ValueError):
            hs.parse_response(response)

    def test_missing_upgrade(self) -> None:
        """Test missing Upgrade header."""
        hs = Handshake("example.com", "/ws")
        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: test\r\n"
            b"\r\n"
        )
        with pytest.raises(ValueError):
            hs.parse_response(response)

    def test_trailing_frame_data_handled(self) -> None:
        """Test response with binary WebSocket data after headers."""
        hs = Handshake("example.com", "/ws")
        response = self._build_valid_response(hs.key)
        # Append binary WebSocket frame data (invalid UTF-8)
        response += bytes([0x81, 0x05, 0xFF, 0xFE, 0xFD, 0xFC, 0xFB])
        # Should NOT raise — parser should only decode header section
        result = hs.parse_response(response)
        assert result.status == 101

    def test_build_request_with_origin(self) -> None:
        """Test request building with origin."""
        hs = Handshake("example.com", "/ws", origin="https://example.com")
        request = hs.build_request().decode("utf-8")
        assert "Origin: https://example.com" in request

    def test_build_request_with_extra_headers(self) -> None:
        """Test request building with extra headers."""
        hs = Handshake(
            "example.com",
            "/ws",
            extra_headers=[("Authorization", "Bearer token")],
        )
        request = hs.build_request().decode("utf-8")
        assert "Authorization: Bearer token" in request


class TestFallbackDeflater:
    """Tests for fallback Deflater not covered by test_compress.py."""

    def test_compress_decompress_multiple(self) -> None:
        """Test multiple compress/decompress with context preservation."""
        d = Deflater()
        msgs = [b"msg1", b"msg2", b"msg3"]
        for msg in msgs:
            c = d.compress(msg)
            dc = d.decompress(c)
            assert dc == msg

    def test_no_context_takeover_resets(self) -> None:
        """Test that no_context_takeover creates fresh compressor each time."""
        d = Deflater(client_no_context_takeover=True, server_no_context_takeover=True)
        msg = b"test message data"
        c1 = d.compress(msg)
        dc1 = d.decompress(c1)
        assert dc1 == msg

        c2 = d.compress(msg)
        dc2 = d.decompress(c2)
        assert dc2 == msg

    def test_reset_compressor(self) -> None:
        """Test explicit compressor reset."""
        d = Deflater()
        d.compress(b"data")
        d.reset_compressor()
        c = d.compress(b"more data")
        d.reset_decompressor()
        dc = d.decompress(c)
        assert dc == b"more data"

    def test_window_bits_validation(self) -> None:
        """Test window bits range validation."""
        with pytest.raises(ValueError):
            Deflater(client_max_window_bits=8)
        with pytest.raises(ValueError):
            Deflater(server_max_window_bits=16)

    def test_properties(self) -> None:
        """Test Deflater properties."""
        d = Deflater(
            client_no_context_takeover=True,
            server_no_context_takeover=False,
            client_max_window_bits=12,
            server_max_window_bits=14,
        )
        assert d.client_no_context_takeover is True
        assert d.server_no_context_takeover is False
        assert d.client_max_window_bits == 12
        assert d.server_max_window_bits == 14

    def test_repr(self) -> None:
        """Test string representation."""
        d = Deflater()
        assert "Deflater" in repr(d)


class TestFallbackParseDeflateParams:
    """Tests for fallback parse_deflate_params."""

    def test_basic(self) -> None:
        """Test basic parsing."""
        cnct, snct, cmwb, smwb = parse_deflate_params("permessage-deflate")
        assert cnct is False
        assert snct is False
        assert cmwb == 15
        assert smwb == 15

    def test_all_params(self) -> None:
        """Test all parameters."""
        cnct, snct, cmwb, smwb = parse_deflate_params(
            "permessage-deflate; client_no_context_takeover; "
            "server_no_context_takeover; client_max_window_bits=10; "
            "server_max_window_bits=12"
        )
        assert cnct is True
        assert snct is True
        assert cmwb == 10
        assert smwb == 12


class TestFallbackValidateUtf8:
    """Tests for fallback validate_utf8."""

    def test_valid(self) -> None:
        """Test valid UTF-8."""
        assert validate_utf8(b"Hello") is True
        assert validate_utf8(b"") is True

    def test_invalid(self) -> None:
        """Test invalid UTF-8."""
        assert validate_utf8(bytes([0xFF, 0xFE])) is False


class TestFallbackApplyMask:
    """Tests for fallback apply_mask."""

    def test_roundtrip(self) -> None:
        """Test mask/unmask roundtrip."""
        data = b"Hello, World!"
        mask = (0x37, 0xFA, 0x21, 0x3D)
        masked = apply_mask(data, mask)
        assert masked != data
        unmasked = apply_mask(masked, mask)
        assert unmasked == data

    def test_bytes_mask(self) -> None:
        """Test mask as bytes."""
        data = b"test"
        mask = bytes([0x12, 0x34, 0x56, 0x78])
        result = apply_mask(data, mask)
        assert len(result) == 4

    def test_empty(self) -> None:
        """Test empty data."""
        assert apply_mask(b"", (0, 0, 0, 0)) == b""


class TestFallbackMisc:
    """Tests for fallback miscellaneous functions."""

    def test_generate_key(self) -> None:
        """Test key generation."""
        key = generate_key()
        import base64

        decoded = base64.b64decode(key)
        assert len(decoded) == 16

    def test_validate_accept_correct(self) -> None:
        """Test correct accept validation."""
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        assert validate_accept(key, accept) is True

    def test_validate_accept_wrong(self) -> None:
        """Test wrong accept validation."""
        assert validate_accept("key", "wrong") is False

    def test_overflow_policy_values(self) -> None:
        """Test OverflowPolicy enum values."""
        assert OverflowPolicy.DropOldest == 0
        assert OverflowPolicy.DropNewest == 1
        assert OverflowPolicy.Error == 2

    def test_opcode_properties(self) -> None:
        """Test Opcode properties."""
        assert Opcode.TEXT.is_data_frame
        assert not Opcode.TEXT.is_control_frame
        assert Opcode.PING.is_control_frame
        assert not Opcode.PING.is_data_frame

    def test_frame_repr(self) -> None:
        """Test Frame repr."""
        f = Frame(opcode=Opcode.TEXT, payload=b"hi")
        assert "TEXT" in repr(f)

    def test_frame_as_text(self) -> None:
        """Test Frame as_text."""
        f = Frame(opcode=Opcode.TEXT, payload=b"hello")
        assert f.as_text() == "hello"

    def test_frame_payload_len(self) -> None:
        """Test Frame payload_len."""
        f = Frame(opcode=Opcode.TEXT, payload=b"hello")
        assert f.payload_len == 5
