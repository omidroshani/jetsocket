# WebSocket with `message_type`

WebSocket client with Pydantic message validation via the `message_type` parameter.

::: wsfabric.typed.TypedWebSocket
    options:
      show_source: true
      members:
        - __init__
        - message_type
        - validation_errors

## Installation

Typed messages require Pydantic:

```bash
pip install wsfabric[pydantic]
# or
pip install pydantic
```

## Usage

```python
from pydantic import BaseModel
from wsfabric import WebSocket

class TradeMessage(BaseModel):
    symbol: str
    price: float
    quantity: float

async with WebSocket("wss://stream.example.com/ws", message_type=TradeMessage) as ws:
    async for trade in ws:  # trade: TradeMessage
        print(f"{trade.symbol}: ${trade.price:.2f}")
```

## Validation Modes

### Strict Mode (default)

Raises `ValidationError` on invalid messages:

```python
ws = WebSocket("wss://example.com/ws", message_type=TradeMessage, strict=True)
```

### Non-Strict Mode

Skips invalid messages with a warning:

```python
ws = WebSocket("wss://example.com/ws", message_type=TradeMessage, strict=False)

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

With `WebSocket(message_type=...)`, your IDE provides:

- Autocomplete for message fields
- Type error detection
- Documentation on hover

```python
async for trade in ws:
    trade.symbol    # Autocomplete works
    trade.invalid   # Type error detected
```
