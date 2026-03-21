"""Tests for wsfabric._core_fallback module.

These tests verify the pure-Python fallback implementation matches
the expected behavior of the Rust core.
"""

from __future__ import annotations

import base64

import pytest

from wsfabric._core_fallback import (
    Frame,
    FrameParser,
    Handshake,
    Opcode,
    apply_mask,
    generate_key,
    validate_accept,
)


class TestMasking:
    """Tests for apply_mask function."""

    def test_mask_roundtrip(self) -> None:
        """Test that masking is reversible."""
        data = b"Hello, World!"
        mask = (0x37, 0xFA, 0x21, 0x3D)

        masked = apply_mask(data, mask)
        assert masked != data

        unmasked = apply_mask(masked, mask)
        assert unmasked == data

    def test_mask_empty(self) -> None:
        """Test masking empty data."""
        result = apply_mask(b"", (0x12, 0x34, 0x56, 0x78))
        assert result == b""

    def test_mask_various_lengths(self) -> None:
        """Test masking data of various lengths."""
        mask = (0xAA, 0xBB, 0xCC, 0xDD)

        for length in range(1, 20):
            data = bytes(range(length))
            masked = apply_mask(data, mask)
            unmasked = apply_mask(masked, mask)
            assert unmasked == data

    def test_mask_bytes_key(self) -> None:
        """Test that mask accepts bytes key."""
        data = b"Test"
        mask_tuple = (0x12, 0x34, 0x56, 0x78)
        mask_bytes = bytes(mask_tuple)

        result1 = apply_mask(data, mask_tuple)
        result2 = apply_mask(data, mask_bytes)
        assert result1 == result2


class TestHandshake:
    """Tests for handshake functions."""

    def test_generate_key_format(self) -> None:
        """Test that generated key is valid base64."""
        key = generate_key()
        # Should be 24 chars (base64 of 16 bytes)
        assert len(key) == 24
        # Should be valid base64
        decoded = base64.b64decode(key)
        assert len(decoded) == 16

    def test_generate_key_unique(self) -> None:
        """Test that generated keys are unique."""
        keys = {generate_key() for _ in range(100)}
        assert len(keys) == 100

    def test_validate_accept_rfc_example(self) -> None:
        """Test validate_accept with RFC 6455 example."""
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        assert validate_accept(key, expected_accept)

    def test_validate_accept_invalid(self) -> None:
        """Test validate_accept rejects invalid accept."""
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        assert not validate_accept(key, "invalid")


class TestFrameParser:
    """Tests for FrameParser class."""

    def test_parse_simple_text_frame(self) -> None:
        """Test parsing a simple text frame."""
        parser = FrameParser()
        # Unmasked text frame with "Hello"
        frame_data = bytes([0x81, 0x05]) + b"Hello"

        frames, consumed = parser.feed(frame_data)
        assert consumed == 7
        assert len(frames) == 1
        assert frames[0].fin is True
        assert frames[0].opcode == Opcode.TEXT
        assert frames[0].payload == b"Hello"

    def test_parse_binary_frame(self) -> None:
        """Test parsing a binary frame."""
        parser = FrameParser()
        frame_data = bytes([0x82, 0x04, 0x00, 0x01, 0x02, 0x03])

        frames, _consumed = parser.feed(frame_data)
        assert len(frames) == 1
        assert frames[0].opcode == Opcode.BINARY
        assert frames[0].payload == bytes([0x00, 0x01, 0x02, 0x03])

    def test_parse_masked_frame(self) -> None:
        """Test parsing a masked frame."""
        parser = FrameParser()
        mask = bytes([0x37, 0xFA, 0x21, 0x3D])
        payload = b"Hello"
        masked_payload = apply_mask(payload, mask)

        frame_data = bytes([0x81, 0x85]) + mask + masked_payload

        frames, _consumed = parser.feed(frame_data)
        assert len(frames) == 1
        assert frames[0].payload == b"Hello"

    def test_parse_extended_length_16bit(self) -> None:
        """Test parsing frame with 16-bit length."""
        parser = FrameParser()
        payload = b"x" * 200
        frame_data = bytes([0x82, 126, 0x00, 200]) + payload

        frames, _consumed = parser.feed(frame_data)
        assert len(frames) == 1
        assert len(frames[0].payload) == 200

    def test_parse_partial_frame(self) -> None:
        """Test that partial frames are buffered."""
        parser = FrameParser()

        # Send header only
        frames, consumed = parser.feed(bytes([0x81, 0x05]))
        assert len(frames) == 0
        assert consumed == 0

        # Send rest of frame
        frames, consumed = parser.feed(b"Hello")
        assert len(frames) == 1
        assert frames[0].payload == b"Hello"

    def test_parse_multiple_frames(self) -> None:
        """Test parsing multiple frames at once."""
        parser = FrameParser()
        frame1 = bytes([0x81, 0x02]) + b"Hi"
        frame2 = bytes([0x81, 0x05]) + b"Hello"

        frames, _consumed = parser.feed(frame1 + frame2)
        assert len(frames) == 2
        assert frames[0].payload == b"Hi"
        assert frames[1].payload == b"Hello"

    def test_parse_control_frame_too_large(self) -> None:
        """Test that control frames > 125 bytes raise error."""
        parser = FrameParser()
        # Ping frame claiming 126 bytes
        frame_data = bytes([0x89, 126, 0x00, 126])

        with pytest.raises(ValueError, match="Control frame too large"):
            parser.feed(frame_data)

    def test_parse_fragmented_control_frame(self) -> None:
        """Test that fragmented control frames raise error."""
        parser = FrameParser()
        # Ping frame with FIN=0
        frame_data = bytes([0x09, 0x00])

        with pytest.raises(ValueError, match="Fragmented control frame"):
            parser.feed(frame_data)

    def test_encode_text_frame(self) -> None:
        """Test encoding a text frame."""
        parser = FrameParser()
        encoded = parser.encode(Opcode.TEXT, b"Hello", mask=False, fin=True)

        # Should be: FIN=1 + opcode=1, len=5, payload
        assert encoded[0] == 0x81
        assert encoded[1] == 0x05
        assert encoded[2:] == b"Hello"

    def test_encode_masked_frame(self) -> None:
        """Test encoding a masked frame."""
        parser = FrameParser()
        encoded = parser.encode(Opcode.TEXT, b"Hello", mask=True, fin=True)

        # Should be: FIN=1 + opcode=1, MASK=1 + len=5, mask key (4 bytes), masked payload
        assert encoded[0] == 0x81
        assert encoded[1] == 0x85  # MASK bit set
        assert len(encoded) == 2 + 4 + 5  # header + mask + payload

    def test_encode_close_frame(self) -> None:
        """Test encoding a close frame."""
        parser = FrameParser()
        encoded = parser.encode_close(1000, "Normal", mask=False)

        # Should be: FIN=1 + opcode=8, len, code (2 bytes), reason
        assert encoded[0] == 0x88
        assert encoded[2:4] == b"\x03\xe8"  # 1000 big-endian
        assert b"Normal" in encoded

    def test_encode_decode_roundtrip(self) -> None:
        """Test that encode/decode is reversible."""
        parser = FrameParser()
        original = b"Test message with unicode: \xc3\xa9"

        encoded = parser.encode(Opcode.TEXT, original, mask=True, fin=True)
        frames, _ = parser.feed(encoded)

        assert len(frames) == 1
        assert frames[0].payload == original

    def test_reset(self) -> None:
        """Test parser reset clears state."""
        parser = FrameParser()

        # Feed partial frame
        parser.feed(bytes([0x81, 0x05]))

        parser.reset()

        # Should start fresh
        frames, _consumed = parser.feed(bytes([0x81, 0x02]) + b"Hi")
        assert len(frames) == 1
        assert frames[0].payload == b"Hi"


class TestHandshakeClass:
    """Tests for Handshake class."""

    def test_build_request(self) -> None:
        """Test building HTTP upgrade request."""
        hs = Handshake("example.com", "/ws")
        request = hs.build_request()
        request_str = request.decode("utf-8")

        assert "GET /ws HTTP/1.1\r\n" in request_str
        assert "Host: example.com\r\n" in request_str
        assert "Upgrade: websocket\r\n" in request_str
        assert "Connection: Upgrade\r\n" in request_str
        assert "Sec-WebSocket-Key:" in request_str
        assert "Sec-WebSocket-Version: 13\r\n" in request_str
        assert request_str.endswith("\r\n\r\n")

    def test_build_request_with_options(self) -> None:
        """Test building request with optional headers."""
        hs = Handshake(
            "example.com",
            "/ws",
            origin="https://example.com",
            subprotocols=["graphql-ws", "graphql-transport-ws"],
            extensions=["permessage-deflate"],
            extra_headers=[("Authorization", "Bearer token")],
        )
        request = hs.build_request()
        request_str = request.decode("utf-8")

        assert "Origin: https://example.com\r\n" in request_str
        assert (
            "Sec-WebSocket-Protocol: graphql-ws, graphql-transport-ws\r\n"
            in request_str
        )
        assert "Sec-WebSocket-Extensions: permessage-deflate\r\n" in request_str
        assert "Authorization: Bearer token\r\n" in request_str

    def test_parse_response_success(self) -> None:
        """Test parsing successful handshake response."""
        # Use a known key for predictable accept value
        hs = Handshake("example.com", "/ws")
        # Override key for testing
        hs._key = "dGhlIHNhbXBsZSBub25jZQ=="

        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n"
            b"\r\n"
        )

        result = hs.parse_response(response)
        assert result.status == 101

    def test_parse_response_http_error(self) -> None:
        """Test parsing HTTP error response."""
        hs = Handshake("example.com", "/ws")
        response = b"HTTP/1.1 403 Forbidden\r\n\r\n"

        with pytest.raises(ValueError, match="HTTP 403"):
            hs.parse_response(response)

    def test_parse_response_invalid_accept(self) -> None:
        """Test parsing response with invalid accept."""
        hs = Handshake("example.com", "/ws")
        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: invalid\r\n"
            b"\r\n"
        )

        with pytest.raises(ValueError, match="Invalid Sec-WebSocket-Accept"):
            hs.parse_response(response)


class TestFrame:
    """Tests for Frame dataclass."""

    def test_frame_properties(self) -> None:
        """Test Frame property methods."""
        frame = Frame(opcode=Opcode.TEXT, payload=b"Hello")
        assert frame.payload_len == 5
        assert frame.as_text() == "Hello"

    def test_frame_repr(self) -> None:
        """Test Frame string representation."""
        frame = Frame(opcode=Opcode.BINARY, payload=b"\x00\x01\x02")
        repr_str = repr(frame)
        assert "BINARY" in repr_str
        assert "payload_len=3" in repr_str
