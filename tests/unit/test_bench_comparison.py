"""Comparative benchmarks: JetSocket vs websockets vs websocket-client vs picows vs aiohttp.

Measures real WebSocket operations against a local echo server:
- Connection establishment time
- Message send/recv round-trip latency (small + large)
- Throughput (1000 messages)

Run with: make test-bench
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import pytest
import websockets.client
import websockets.server

BENCH_PORT = 9870
BENCH_URI = f"ws://127.0.0.1:{BENCH_PORT}"
SMALL_MSG = json.dumps({"symbol": "BTCUSDT", "price": "50000.00", "qty": "0.1"})
LARGE_MSG = json.dumps({"data": "x" * 10_000})
N_THROUGHPUT = 1000


# ---------------------------------------------------------------------------
# Echo server (module-scoped)
# ---------------------------------------------------------------------------


def _run_echo_server(started: threading.Event, stop: threading.Event) -> None:
    loop = asyncio.new_event_loop()

    async def handler(ws: websockets.server.ServerConnection) -> None:
        try:
            async for msg in ws:
                await ws.send(msg)
        except websockets.exceptions.ConnectionClosed:
            pass

    async def serve() -> None:
        async with websockets.server.serve(handler, "127.0.0.1", BENCH_PORT):
            started.set()
            while not stop.is_set():
                await asyncio.sleep(0.05)

    loop.run_until_complete(serve())
    loop.close()


@pytest.fixture(scope="module")
def echo_server() -> Any:
    """Module-scoped echo server."""
    started = threading.Event()
    stop = threading.Event()
    t = threading.Thread(target=_run_echo_server, args=(started, stop), daemon=True)
    t.start()
    started.wait(timeout=5.0)
    yield BENCH_URI
    stop.set()
    t.join(timeout=5.0)


def _new_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


# ===========================================================================
# CONNECTION BENCHMARKS
# ===========================================================================


@pytest.mark.benchmark(group="connect")
def test_jetsocket_connect(benchmark: Any, echo_server: str) -> None:
    """JetSocket connection time."""
    from jetsocket.transport import AsyncTransport, BaseTransportConfig

    config = BaseTransportConfig(connect_timeout=5.0)
    loop = _new_loop()

    async def run() -> None:
        t = AsyncTransport(config)
        await t.connect(echo_server)
        await t.close()

    try:
        benchmark(lambda: loop.run_until_complete(run()))
    finally:
        loop.close()


@pytest.mark.benchmark(group="connect")
def test_websockets_connect(benchmark: Any, echo_server: str) -> None:
    """websockets connection time."""
    loop = _new_loop()

    async def run() -> None:
        ws = await websockets.client.connect(echo_server)
        await ws.close()

    try:
        benchmark(lambda: loop.run_until_complete(run()))
    finally:
        loop.close()


@pytest.mark.benchmark(group="connect")
def test_websocket_client_connect(benchmark: Any, echo_server: str) -> None:
    """websocket-client connection time."""
    import websocket

    def run() -> None:
        ws = websocket.create_connection(echo_server, timeout=5)
        ws.close()

    benchmark(run)


@pytest.mark.benchmark(group="connect")
def test_picows_connect(benchmark: Any, echo_server: str) -> None:
    """picows connection time."""
    from picows import WSListener, ws_connect

    class Listener(WSListener):
        pass

    loop = _new_loop()

    async def run() -> None:
        transport, _ = await ws_connect(Listener, echo_server)
        transport.disconnect()

    try:
        benchmark(lambda: loop.run_until_complete(run()))
    finally:
        loop.close()


@pytest.mark.benchmark(group="connect")
def test_aiohttp_connect(benchmark: Any, echo_server: str) -> None:
    """aiohttp connection time."""
    import aiohttp

    loop = _new_loop()

    async def run() -> None:
        async with aiohttp.ClientSession() as session, session.ws_connect(echo_server) as ws:
            await ws.close()

    try:
        benchmark(lambda: loop.run_until_complete(run()))
    finally:
        loop.close()


# ===========================================================================
# ROUND-TRIP SMALL MESSAGE
# ===========================================================================


@pytest.mark.benchmark(group="roundtrip-small")
def test_jetsocket_rt_small(benchmark: Any, echo_server: str) -> None:
    """JetSocket small message round-trip."""
    from jetsocket.transport import AsyncTransport, BaseTransportConfig

    config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
    loop = _new_loop()
    transport = AsyncTransport(config)
    loop.run_until_complete(transport.connect(echo_server))

    async def rt() -> None:
        await transport.send(SMALL_MSG)
        await transport.recv()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(transport.close())
        loop.close()


@pytest.mark.benchmark(group="roundtrip-small")
def test_websockets_rt_small(benchmark: Any, echo_server: str) -> None:
    """websockets small message round-trip."""
    loop = _new_loop()
    ws = loop.run_until_complete(websockets.client.connect(echo_server))

    async def rt() -> None:
        await ws.send(SMALL_MSG)
        await ws.recv()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(ws.close())
        loop.close()


@pytest.mark.benchmark(group="roundtrip-small")
def test_websocket_client_rt_small(benchmark: Any, echo_server: str) -> None:
    """websocket-client small message round-trip."""
    import websocket

    ws = websocket.create_connection(echo_server, timeout=5)

    def rt() -> None:
        ws.send(SMALL_MSG)
        ws.recv()

    try:
        benchmark(rt)
    finally:
        ws.close()


@pytest.mark.benchmark(group="roundtrip-small")
def test_picows_rt_small(benchmark: Any, echo_server: str) -> None:
    """picows small message round-trip."""
    from picows import WSFrame, WSListener, WSMsgType, WSTransport, ws_connect

    received = asyncio.Event()

    class Listener(WSListener):
        def on_ws_frame(self, transport: WSTransport, frame: WSFrame) -> None:
            received.set()

    loop = _new_loop()
    transport_pw, _listener = loop.run_until_complete(
        ws_connect(Listener, echo_server)
    )

    async def rt() -> None:
        received.clear()
        transport_pw.send(WSMsgType.TEXT, SMALL_MSG.encode())
        await asyncio.wait_for(received.wait(), timeout=5.0)

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        transport_pw.disconnect()
        loop.close()


@pytest.mark.benchmark(group="roundtrip-small")
def test_aiohttp_rt_small(benchmark: Any, echo_server: str) -> None:
    """aiohttp small message round-trip."""
    import aiohttp

    loop = _new_loop()

    async def setup_and_run() -> tuple[Any, Any]:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(echo_server)
        return session, ws

    session, ws = loop.run_until_complete(setup_and_run())

    async def rt() -> None:
        await ws.send_str(SMALL_MSG)
        await ws.receive()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(ws.close())
        loop.run_until_complete(session.close())
        loop.close()


# ===========================================================================
# ROUND-TRIP LARGE MESSAGE (10KB)
# ===========================================================================


@pytest.mark.benchmark(group="roundtrip-large")
def test_jetsocket_rt_large(benchmark: Any, echo_server: str) -> None:
    """JetSocket large message (10KB) round-trip."""
    from jetsocket.transport import AsyncTransport, BaseTransportConfig

    config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
    loop = _new_loop()
    transport = AsyncTransport(config)
    loop.run_until_complete(transport.connect(echo_server))

    async def rt() -> None:
        await transport.send(LARGE_MSG)
        await transport.recv()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(transport.close())
        loop.close()


@pytest.mark.benchmark(group="roundtrip-large")
def test_websockets_rt_large(benchmark: Any, echo_server: str) -> None:
    """websockets large message (10KB) round-trip."""
    loop = _new_loop()
    ws = loop.run_until_complete(websockets.client.connect(echo_server))

    async def rt() -> None:
        await ws.send(LARGE_MSG)
        await ws.recv()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(ws.close())
        loop.close()


@pytest.mark.benchmark(group="roundtrip-large")
def test_websocket_client_rt_large(benchmark: Any, echo_server: str) -> None:
    """websocket-client large message (10KB) round-trip."""
    import websocket

    ws = websocket.create_connection(echo_server, timeout=5)

    def rt() -> None:
        ws.send(LARGE_MSG)
        ws.recv()

    try:
        benchmark(rt)
    finally:
        ws.close()


@pytest.mark.benchmark(group="roundtrip-large")
def test_picows_rt_large(benchmark: Any, echo_server: str) -> None:
    """picows large message (10KB) round-trip."""
    from picows import WSFrame, WSListener, WSMsgType, WSTransport, ws_connect

    received = asyncio.Event()

    class Listener(WSListener):
        def on_ws_frame(self, transport: WSTransport, frame: WSFrame) -> None:
            received.set()

    loop = _new_loop()
    transport_pw, _listener = loop.run_until_complete(
        ws_connect(Listener, echo_server)
    )

    async def rt() -> None:
        received.clear()
        transport_pw.send(WSMsgType.TEXT, LARGE_MSG.encode())
        await asyncio.wait_for(received.wait(), timeout=5.0)

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        transport_pw.disconnect()
        loop.close()


@pytest.mark.benchmark(group="roundtrip-large")
def test_aiohttp_rt_large(benchmark: Any, echo_server: str) -> None:
    """aiohttp large message (10KB) round-trip."""
    import aiohttp

    loop = _new_loop()

    async def setup_and_run() -> tuple[Any, Any]:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(echo_server)
        return session, ws

    session, ws = loop.run_until_complete(setup_and_run())

    async def rt() -> None:
        await ws.send_str(LARGE_MSG)
        await ws.receive()

    try:
        benchmark(lambda: loop.run_until_complete(rt()))
    finally:
        loop.run_until_complete(ws.close())
        loop.run_until_complete(session.close())
        loop.close()


# ===========================================================================
# THROUGHPUT (1000 messages)
# ===========================================================================


@pytest.mark.benchmark(group="throughput")
def test_jetsocket_throughput(benchmark: Any, echo_server: str) -> None:
    """JetSocket throughput (1000 messages)."""
    from jetsocket.transport import AsyncTransport, BaseTransportConfig

    config = BaseTransportConfig(connect_timeout=5.0, read_timeout=5.0)
    loop = _new_loop()
    transport = AsyncTransport(config)
    loop.run_until_complete(transport.connect(echo_server))

    async def burst() -> None:
        for i in range(N_THROUGHPUT):
            await transport.send(f"msg-{i}")
            await transport.recv()

    try:
        benchmark(lambda: loop.run_until_complete(burst()))
    finally:
        loop.run_until_complete(transport.close())
        loop.close()


@pytest.mark.benchmark(group="throughput")
def test_websockets_throughput(benchmark: Any, echo_server: str) -> None:
    """websockets throughput (1000 messages)."""
    loop = _new_loop()
    ws = loop.run_until_complete(websockets.client.connect(echo_server))

    async def burst() -> None:
        for i in range(N_THROUGHPUT):
            await ws.send(f"msg-{i}")
            await ws.recv()

    try:
        benchmark(lambda: loop.run_until_complete(burst()))
    finally:
        loop.run_until_complete(ws.close())
        loop.close()


@pytest.mark.benchmark(group="throughput")
def test_websocket_client_throughput(benchmark: Any, echo_server: str) -> None:
    """websocket-client throughput (1000 messages)."""
    import websocket

    ws = websocket.create_connection(echo_server, timeout=5)

    def burst() -> None:
        for i in range(N_THROUGHPUT):
            ws.send(f"msg-{i}")
            ws.recv()

    try:
        benchmark(burst)
    finally:
        ws.close()


@pytest.mark.benchmark(group="throughput")
def test_picows_throughput(benchmark: Any, echo_server: str) -> None:
    """picows throughput (1000 messages)."""
    from picows import WSFrame, WSListener, WSMsgType, WSTransport, ws_connect

    count = 0
    done = asyncio.Event()

    class Listener(WSListener):
        def on_ws_frame(self, transport: WSTransport, frame: WSFrame) -> None:
            nonlocal count
            count += 1
            if count >= N_THROUGHPUT:
                done.set()

    loop = _new_loop()
    transport_pw, _listener = loop.run_until_complete(
        ws_connect(Listener, echo_server)
    )

    async def burst() -> None:
        nonlocal count
        count = 0
        done.clear()
        for i in range(N_THROUGHPUT):
            transport_pw.send(WSMsgType.TEXT, f"msg-{i}".encode())
        await asyncio.wait_for(done.wait(), timeout=30.0)

    try:
        benchmark(lambda: loop.run_until_complete(burst()))
    finally:
        transport_pw.disconnect()
        loop.close()


@pytest.mark.benchmark(group="throughput")
def test_aiohttp_throughput(benchmark: Any, echo_server: str) -> None:
    """aiohttp throughput (1000 messages)."""
    import aiohttp

    loop = _new_loop()

    async def setup_and_run() -> tuple[Any, Any]:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(echo_server)
        return session, ws

    session, ws = loop.run_until_complete(setup_and_run())

    async def burst() -> None:
        for i in range(N_THROUGHPUT):
            await ws.send_str(f"msg-{i}")
            await ws.receive()

    try:
        benchmark(lambda: loop.run_until_complete(burst()))
    finally:
        loop.run_until_complete(ws.close())
        loop.run_until_complete(session.close())
        loop.close()
