# Installation

## Requirements

- Python 3.10 or higher
- No required dependencies (Cython-optimized C extension included)

## Install from PyPI

```bash
pip install jetsocket
```

## Optional Dependencies

JetSocket has optional dependencies for enhanced functionality:

### Pydantic Support

For typed messages with automatic validation:

```bash
pip install jetsocket[pydantic]
```

### All Optional Dependencies

```bash
pip install jetsocket[all]
```

## Development Installation

For development, clone the repository and install with dev dependencies:

```bash
git clone https://github.com/omidroshani/jetsocket.git
cd jetsocket
uv sync
make build   # Build Cython extension
```

Then run the examples:

```bash
# Binance trade streaming
uv run --extra pydantic python examples/binance_trades.py

# Sync price analysis
uv run python examples/sync_simple.py
```

See [Running Examples](../examples/index.md) for all available examples.

## Verify Installation

```python
import jetsocket
print(jetsocket.__version__)
```

## Platform Support

JetSocket supports:

- Linux (x86_64, aarch64)
- macOS (x86_64, arm64)
- Windows (x86_64)

Precompiled wheels are available for these platforms. On other platforms, a C compiler is needed to build from source.
