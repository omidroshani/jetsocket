"""Security tests for WebSocket handshake."""

from __future__ import annotations

import base64

import pytest

from jetsocket._core import Handshake, generate_key, validate_accept
from jetsocket._core import (  
        Handshake,
        generate_key,
        validate_accept,
    )


@pytest.mark.security
class TestHandshakeSecurity:
    """Verify handshake security properties."""

    def test_key_uniqueness(self) -> None:
        """Verify generated keys are unique across 1000 calls."""
        keys = {generate_key() for _ in range(1000)}
        assert len(keys) == 1000, "Generated keys should be unique"

    def test_key_is_valid_base64(self) -> None:
        """Verify generated key is valid base64 of 16 random bytes."""
        key = generate_key()
        decoded = base64.b64decode(key)
        assert len(decoded) == 16

    def test_key_has_sufficient_entropy(self) -> None:
        """Verify key bytes have some randomness (not all zeros)."""
        keys_bytes = [base64.b64decode(generate_key()) for _ in range(10)]
        # All keys should be different
        unique = set(keys_bytes)
        assert len(unique) == 10

    def test_accept_validation_rejects_wrong_value(self) -> None:
        """Verify validate_accept rejects incorrect accept values."""
        key = generate_key()
        assert validate_accept(key, "wrong_accept_value") is False

    def test_accept_validation_accepts_correct_value(self) -> None:
        """Verify validate_accept accepts correct RFC 6455 value."""
        # RFC 6455 Section 4.2.2 example
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        assert validate_accept(key, expected_accept) is True

    def test_handshake_includes_required_headers(self) -> None:
        """Verify handshake request includes all required headers."""
        hs = Handshake("example.com", "/ws")
        request = hs.build_request().decode("utf-8")

        assert "GET /ws HTTP/1.1\r\n" in request
        assert "Host: example.com\r\n" in request
        assert "Upgrade: websocket\r\n" in request
        assert "Connection: Upgrade\r\n" in request
        assert "Sec-WebSocket-Key:" in request
        assert "Sec-WebSocket-Version: 13\r\n" in request

    def test_handshake_rejects_non_101_status(self) -> None:
        """Verify handshake rejects non-101 HTTP responses."""
        hs = Handshake("example.com", "/ws")
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        with pytest.raises(ValueError, match=r"200|HTTP"):
            hs.parse_response(response)

    def test_handshake_rejects_invalid_accept(self) -> None:
        """Verify handshake rejects invalid Sec-WebSocket-Accept."""
        hs = Handshake("example.com", "/ws")
        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: INVALID\r\n"
            b"\r\n"
        )
        with pytest.raises(ValueError, match=r"[Aa]ccept|[Ii]nvalid"):
            hs.parse_response(response)

    def test_handshake_rejects_missing_upgrade(self) -> None:
        """Verify handshake rejects response missing Upgrade header."""
        hs = Handshake("example.com", "/ws")
        response = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: test\r\n"
            b"\r\n"
        )
        with pytest.raises(ValueError):
            hs.parse_response(response)

    def test_handshake_rejects_truncated_response(self) -> None:
        """Verify handshake rejects incomplete responses."""
        hs = Handshake("example.com", "/ws")
        with pytest.raises(ValueError):
            hs.parse_response(b"HTTP/1.1 101")
