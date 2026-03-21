# WSFabric

Production-grade, resilient WebSocket library for Python with Rust-powered performance.

## Features

- **Rust-powered core** — Frame parsing, masking, and compression via PyO3
- **Automatic reconnection** — Exponential backoff with jitter
- **Heartbeat management** — Configurable ping/pong with timeout detection
- **Message buffering** — Ring buffer with replay-on-reconnect
- **Both async and sync** — Native asyncio and sync APIs
- **Full type safety** — Generics support, Pydantic integration
- **Zero dependencies** — Only stdlib required at runtime

## Installation

```bash
pip install wsfabric
```

Or with uv:

```bash
uv add wsfabric
```

## Quick Start

### Async

```python
from wsfabric import WebSocketManager

async def main():
    async with WebSocketManager("wss://example.com/ws") as ws:
        await ws.send({"type": "subscribe", "channel": "updates"})
        async for message in ws:
            print(message)
```

### Sync

```python
from wsfabric import WebSocketManager

ws = WebSocketManager("wss://example.com/ws")
ws.connect_sync()
ws.send_sync({"type": "hello"})
message = ws.recv_sync()
ws.close_sync()
```

## Development

### Setup

```bash
# Clone the repo
git clone https://github.com/omid/wsfabric
cd wsfabric

# Install uv if you haven't
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install deps
uv sync

# Build the Rust extension
uv run maturin develop
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/wsfabric --cov-report=term-missing

# Run only unit tests
uv run pytest tests/unit/
```

### Type Checking and Linting

```bash
# Type check
uv run mypy src/

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

### Building

```bash
# Build wheel
uv run maturin build --release

# Build for development (faster)
uv run maturin develop
```

## License

MIT
