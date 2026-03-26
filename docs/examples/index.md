# Running Examples

JetSocket ships with runnable examples in the [`examples/`](https://github.com/omidroshani/jetsocket/tree/main/examples) directory.

## Setup

Clone the repo and build the Cython extension:

```bash
git clone https://github.com/omidroshani/jetsocket.git
cd jetsocket
uv sync
make build
```

## Quick Reference

| Example | Command | Requires |
|---------|---------|----------|
| [Binance Trades](binance-trades.md) | `uv run --extra pydantic python examples/binance_trades.py` | `pydantic` |
| [Multi-Symbol Dashboard](multi-symbol-dashboard.md) | `uv run python examples/multi_symbol_dashboard.py` | - |
| [Sync Price Analysis](sync-scripting.md) | `uv run python examples/sync_simple.py` | - |
| [LLM Streaming](llm-streaming.md) | `OPENAI_API_KEY="sk-..." uv run python examples/llm_streaming.py` | OpenAI API key |

## Notes

- **Binance examples** connect to public market data streams — no API key needed
- **LLM example** requires an `OPENAI_API_KEY` environment variable
- Press ++ctrl+c++ to stop any long-running example
- All Binance examples use the `/ws` endpoint with dynamic `SUBSCRIBE` messages
- The sync example uses the `/stream?streams=` combined endpoint
