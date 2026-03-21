# Installation

## Requirements

- Python 3.9 or higher
- No required dependencies (pure Python with optional Rust extensions)

## Install from PyPI

```bash
pip install wsfabric
```

## Optional Dependencies

WSFabric has optional dependencies for enhanced functionality:

### Pydantic Support

For typed messages with automatic validation:

```bash
pip install wsfabric[pydantic]
```

### All Optional Dependencies

```bash
pip install wsfabric[all]
```

## Development Installation

For development, clone the repository and install with dev dependencies:

```bash
git clone https://github.com/wsfabric/wsfabric.git
cd wsfabric
pip install -e ".[dev]"
```

## Verify Installation

```python
import wsfabric
print(wsfabric.__version__)
```

## Platform Support

WSFabric supports:

- Linux (x86_64, aarch64)
- macOS (x86_64, arm64)
- Windows (x86_64)

The Rust core is precompiled for these platforms. On other platforms, a pure-Python fallback is used automatically.
