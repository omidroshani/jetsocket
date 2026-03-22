"""Security tests for frame injection prevention."""

from __future__ import annotations

import pytest

from jetsocket._core import FrameParser
from jetsocket._core import FrameParser  


@pytest.mark.security
class TestFrameInjection:
    """Verify client frames are always properly masked."""

    def test_client_frames_always_masked(self) -> None:
        """Verify encode with mask=True sets the mask bit."""
        parser = FrameParser()
        encoded = parser.encode(0x01, b"hello", True, True)
        # Second byte should have mask bit (0x80) set
        assert encoded[1] & 0x80 != 0, "Mask bit not set on client frame"

    def test_mask_key_is_random(self) -> None:
        """Verify mask keys differ across frames."""
        parser = FrameParser()
        frame1 = parser.encode(0x01, b"test", True, True)
        frame2 = parser.encode(0x01, b"test", True, True)
        # For small payloads, mask key is at bytes 2-5
        mask1 = frame1[2:6]
        mask2 = frame2[2:6]
        assert mask1 != mask2, "Mask keys should be random, not deterministic"

    def test_unmasked_server_frames_accepted(self) -> None:
        """Verify parser accepts unmasked frames (server-to-client)."""
        parser = FrameParser()
        # Unmasked text frame with "Hello"
        data = bytes([0x81, 0x05]) + b"Hello"
        frames, consumed = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].payload == b"Hello"
        assert consumed == 7

    def test_masked_payload_is_transformed(self) -> None:
        """Verify payload is actually masked, not sent in cleartext."""
        parser = FrameParser()
        payload = b"SECRET DATA"
        encoded = parser.encode(0x01, payload, True, True)
        # The raw payload should not appear in the encoded frame
        assert payload not in encoded, "Payload appears unmasked in frame"

    def test_mask_default_is_true(self) -> None:
        """Verify encode defaults to masking enabled."""
        parser = FrameParser()
        # Call with positional args only: opcode, payload
        encoded = parser.encode(0x01, b"test")
        assert encoded[1] & 0x80 != 0, "Default mask should be True"
