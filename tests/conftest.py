"""Top-level test configuration with session-scoped echo server.

The echo server starts once per test session and is shared across all tests.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import pytest
import websockets.server

if TYPE_CHECKING:
    from collections.abc import Generator

# Port for the session-scoped echo server
LIVE_SERVER_PORT = 9760


def _run_server(started: threading.Event, stop: threading.Event) -> None:
    """Run the echo WebSocket server in a background thread."""
    loop = asyncio.new_event_loop()

    async def echo_handler(ws: websockets.server.ServerConnection) -> None:
        try:
            async for message in ws:
                await ws.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass

    async def serve() -> None:
        async with websockets.server.serve(echo_handler, "127.0.0.1", LIVE_SERVER_PORT):
            started.set()
            # Wait until stop is signaled
            while not stop.is_set():
                await asyncio.sleep(0.1)

    loop.run_until_complete(serve())
    loop.close()


@pytest.fixture(scope="session")
def live_server_url() -> Generator[str, None, None]:
    """Session-scoped live echo WebSocket server.

    Starts a real WebSocket echo server on localhost that persists
    for the entire test session. Returns the ws:// URL.
    """
    started = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(target=_run_server, args=(started, stop), daemon=True)
    thread.start()
    started.wait(timeout=5.0)

    yield f"ws://127.0.0.1:{LIVE_SERVER_PORT}"

    stop.set()
    thread.join(timeout=5.0)
