# Typed Messages

WSFabric supports type-safe message handling with Pydantic models.

## Installation

Pydantic is an optional dependency:

```bash
pip install wsfabric[pydantic]
# or
pip install pydantic
```

## TypedWebSocket

TypedWebSocket provides automatic validation and type hints:

```python
from pydantic import BaseModel
from wsfabric import TypedWebSocket

class TradeMessage(BaseModel):
    symbol: str
    price: float
    quantity: float

async with TypedWebSocket("wss://stream.example.com/ws", TradeMessage) as ws:
    async for trade in ws:  # trade: TradeMessage
        print(f"{trade.symbol}: ${trade.price:.2f} x {trade.quantity}")
```

## Defining Message Types

Use Pydantic models to define your message schemas:

```python
from pydantic import BaseModel, Field
from datetime import datetime

class OrderUpdate(BaseModel):
    order_id: str = Field(alias="orderId")
    status: str
    filled_qty: float = Field(alias="filledQty")
    timestamp: datetime
```

## Field Aliases

Many APIs use different naming conventions. Use `Field(alias=...)`:

```python
class BinanceTrade(BaseModel):
    event_type: str = Field(alias="e")
    event_time: int = Field(alias="E")
    symbol: str = Field(alias="s")
    trade_id: int = Field(alias="t")
    price: str = Field(alias="p")
    quantity: str = Field(alias="q")
```

## Nested Models

Complex message structures work automatically:

```python
class MarketData(BaseModel):
    bid: PriceLevel
    ask: PriceLevel
    last_trade: TradeInfo

class PriceLevel(BaseModel):
    price: float
    quantity: float

class TradeInfo(BaseModel):
    price: float
    quantity: float
    timestamp: int
```

## Validation Modes

### Strict Mode (default)

Raises `ValidationError` on invalid messages:

```python
ws = TypedWebSocket("wss://example.com/ws", TradeMessage, strict=True)
```

### Non-Strict Mode

Logs warnings and skips invalid messages:

```python
ws = TypedWebSocket("wss://example.com/ws", TradeMessage, strict=False)

# Check validation error count
print(f"Validation errors: {ws.validation_errors}")
```

## Sending Typed Messages

You can send Pydantic models directly:

```python
class SubscribeRequest(BaseModel):
    method: str
    params: list[str]

request = SubscribeRequest(method="SUBSCRIBE", params=["btcusdt@trade"])
await ws.send(request)  # Automatically serialized to JSON
```

## Combining with Presets

```python
# Create a typed trading client
ws = TypedWebSocket(
    "wss://stream.binance.com/ws",
    TradeMessage,
    reconnect=True,
    heartbeat=HeartbeatConfig(interval=20.0),
    buffer=BufferConfig(capacity=10000),
)
```

## Full Example

```python
import asyncio
from pydantic import BaseModel, Field
from wsfabric import TypedWebSocket, HeartbeatConfig

class BinanceTrade(BaseModel):
    event_type: str = Field(alias="e")
    symbol: str = Field(alias="s")
    price: str = Field(alias="p")
    quantity: str = Field(alias="q")
    trade_time: int = Field(alias="T")
    is_buyer_maker: bool = Field(alias="m")

async def main():
    async with TypedWebSocket(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        BinanceTrade,
        heartbeat=HeartbeatConfig(interval=20.0),
    ) as ws:
        async for trade in ws:
            side = "SELL" if trade.is_buyer_maker else "BUY"
            print(f"{trade.symbol} {side}: {trade.price} x {trade.quantity}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Type Checking Benefits

With TypedWebSocket, your IDE provides:

- Autocomplete for message fields
- Type error detection
- Documentation on hover

```python
async for trade in ws:
    trade.symbol    # ✓ Autocomplete works
    trade.invalid   # ✗ Type error detected
```
