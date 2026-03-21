"""Core types for WSFabric.

This module defines the fundamental types used throughout the library,
including WebSocket opcodes and frame representations.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class Opcode(enum.IntEnum):
    """WebSocket frame opcodes as defined in RFC 6455 Section 5.2.

    Data frames:
        - CONTINUATION (0x0): Continuation of a fragmented message
        - TEXT (0x1): Text frame (UTF-8 encoded)
        - BINARY (0x2): Binary frame

    Control frames:
        - CLOSE (0x8): Connection close
        - PING (0x9): Ping frame
        - PONG (0xA): Pong frame
    """

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    # 0x3-0x7 reserved for future non-control frames
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA
    # 0xB-0xF reserved for future control frames

    @property
    def is_control(self) -> bool:
        """Return True if this is a control frame opcode."""
        return self >= 0x8

    @property
    def is_data(self) -> bool:
        """Return True if this is a data frame opcode."""
        return self <= 0x2


@dataclass(frozen=True, slots=True)
class Frame:
    """A WebSocket frame.

    This represents a single frame as defined in RFC 6455 Section 5.2.
    Frames are immutable to ensure thread safety.

    Attributes:
        opcode: The frame opcode.
        payload: The frame payload as bytes.
        fin: True if this is the final fragment.
        rsv1: Reserved bit 1 (used for compression).
        rsv2: Reserved bit 2.
        rsv3: Reserved bit 3.
    """

    opcode: Opcode
    payload: bytes
    fin: bool = True
    rsv1: bool = False
    rsv2: bool = False
    rsv3: bool = False

    @property
    def is_control(self) -> bool:
        """Return True if this is a control frame."""
        return self.opcode.is_control

    @property
    def is_data(self) -> bool:
        """Return True if this is a data frame."""
        return self.opcode.is_data

    @property
    def is_text(self) -> bool:
        """Return True if this is a text frame."""
        return self.opcode == Opcode.TEXT

    @property
    def is_binary(self) -> bool:
        """Return True if this is a binary frame."""
        return self.opcode == Opcode.BINARY

    @property
    def is_close(self) -> bool:
        """Return True if this is a close frame."""
        return self.opcode == Opcode.CLOSE

    @property
    def is_ping(self) -> bool:
        """Return True if this is a ping frame."""
        return self.opcode == Opcode.PING

    @property
    def is_pong(self) -> bool:
        """Return True if this is a pong frame."""
        return self.opcode == Opcode.PONG

    def as_text(self) -> str:
        """Decode payload as UTF-8 text.

        Returns:
            The payload decoded as a UTF-8 string.

        Raises:
            UnicodeDecodeError: If the payload is not valid UTF-8.
        """
        return self.payload.decode("utf-8")

    @property
    def close_code(self) -> int | None:
        """Extract close code from a close frame payload.

        Returns:
            The close code as an integer, or None if no code is present.
        """
        if not self.is_close or len(self.payload) < 2:
            return None
        return int.from_bytes(self.payload[:2], "big")

    @property
    def close_reason(self) -> str:
        """Extract close reason from a close frame payload.

        Returns:
            The close reason as a string, or empty string if not present.
        """
        if not self.is_close or len(self.payload) <= 2:
            return ""
        return self.payload[2:].decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class CloseCode:
    """Standard WebSocket close codes as defined in RFC 6455 Section 7.4.1."""

    NORMAL = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    UNSUPPORTED_DATA = 1003
    NO_STATUS = 1005
    ABNORMAL = 1006
    INVALID_PAYLOAD = 1007
    POLICY_VIOLATION = 1008
    MESSAGE_TOO_BIG = 1009
    MANDATORY_EXTENSION = 1010
    INTERNAL_ERROR = 1011
    SERVICE_RESTART = 1012
    TRY_AGAIN_LATER = 1013
    BAD_GATEWAY = 1014
    TLS_HANDSHAKE = 1015
