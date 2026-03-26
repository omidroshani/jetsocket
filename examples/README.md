# Examples

Runnable examples demonstrating JetSocket features with live WebSocket APIs.

## Prerequisites

Install JetSocket with development dependencies:

```bash
uv sync
make build   # Build Cython extension
```

## Running Examples

### Binance Trade Streaming

Stream real-time BTC and ETH trades using multiplexing and Pydantic models.

```bash
uv run --extra pydantic python examples/binance_trades.py
```

Requires: `pydantic` (installed automatically via `--extra pydantic`)

### Multi-Symbol Dashboard

Live terminal dashboard tracking 5 crypto pairs with color-coded price changes.

```bash
uv run python examples/multi_symbol_dashboard.py
```

### Sync Price Analysis

Synchronous client that fetches prices and calculates statistics. Runs and exits automatically.

```bash
uv run python examples/sync_simple.py
```

### LLM Streaming (OpenAI)

Stream a response from OpenAI's Responses API via WebSocket.

```bash
OPENAI_API_KEY="sk-..." uv run python examples/llm_streaming.py
```

Requires: `OPENAI_API_KEY` environment variable with a valid OpenAI API key.

## Notes

- All Binance examples connect to public market data streams (no API key needed)
- Press `Ctrl+C` to stop any long-running example
- Examples use the `/ws` endpoint with dynamic `SUBSCRIBE` for multiplexing
- The sync example uses `/stream?streams=` combined endpoint for multi-symbol data
