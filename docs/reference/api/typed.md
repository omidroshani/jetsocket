# TypedWebSocket

WebSocket client with Pydantic message validation.

::: wsfabric.TypedWebSocket
    options:
      show_source: true
      members:
        - __init__
        - message_type
        - validation_errors

## Installation

TypedWebSocket requires Pydantic:

```bash
pip install wsfabric[pydantic]
# or
pip install pydantic
```

## Usage

```python
from pydantic import BaseModel
from wsfabric import TypedWebSocket

class TradeMessage(BaseModel):
    symbol: str
    price: float
    quantity: float

async with TypedWebSocket("wss://stream.example.com/ws", TradeMessage) as ws:
    async for trade in ws:  # trade: TradeMessage
        print(f"{trade.symbol}: ${trade.price:.2f}")
```

## Validation Modes

### Strict Mode (default)

Raises `ValidationError` on invalid messages:

```python
ws = TypedWebSocket("wss://example.com/ws", TradeMessage, strict=True)
```

### Non-Strict Mode

Skips invalid messages with a warning:

```python
ws = TypedWebSocket("wss://example.com/ws", TradeMessage, strict=False)

# Check error count
print(f"Validation errors: {ws.validation_errors}")
```

## Sending Typed Messages

Pydantic models are automatically serialized:

```python
class SubscribeRequest(BaseModel):
    method: str
    params: list[str]

request = SubscribeRequest(method="SUBSCRIBE", params=["btcusdt@trade"])
await ws.send(request)  # Serialized to JSON
```

## Field Aliases

Use `Field(alias=...)` for APIs with different naming conventions:

```python
from pydantic import BaseModel, Field

class BinanceTrade(BaseModel):
    event_type: str = Field(alias="e")
    symbol: str = Field(alias="s")
    price: str = Field(alias="p")
    quantity: str = Field(alias="q")
```

## Type Checking Benefits

With TypedWebSocket, your IDE provides:

- Autocomplete for message fields
- Type error detection
- Documentation on hover

```python
async for trade in ws:
    trade.symbol    # Autocomplete works
    trade.invalid   # Type error detected
```
