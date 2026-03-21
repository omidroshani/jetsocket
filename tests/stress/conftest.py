"""Shared fixtures for stress tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import websockets.server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

STRESS_PORT = 9851


@pytest.fixture
async def echo_server() -> AsyncIterator[str]:
    """Start an echo WebSocket server for stress testing."""

    async def echo_handler(
        websocket: websockets.server.ServerConnection,
    ) -> None:
        try:
            async for message in websocket:
                await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.server.serve(
        echo_handler, "127.0.0.1", STRESS_PORT
    ) as server:
        yield f"ws://127.0.0.1:{STRESS_PORT}"
        server.close()
