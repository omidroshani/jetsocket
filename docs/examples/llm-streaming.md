# LLM Streaming

This example demonstrates how to stream responses from an LLM API using the LLM preset.

## Overview

- Connect to an LLM WebSocket API
- Use the `llm_stream` preset for optimal settings
- Handle token-by-token streaming
- Graceful error handling

## Prerequisites

```bash
pip install wsfabric
```

## Full Code

```python
"""Stream LLM responses via WebSocket."""

from __future__ import annotations

import asyncio
import json
import sys

from wsfabric.presets import llm_stream


async def stream_completion(prompt: str) -> None:
    """Stream a completion from the LLM API."""
    # Use LLM preset: quick retry, large messages, no compression
    ws = llm_stream("wss://api.example.com/v1/stream")

    @ws.on("connected")
    async def on_connected(event):
        # Send the prompt when connected
        await ws.send({
            "type": "message",
            "role": "user",
            "content": prompt,
        })

    @ws.on("message")
    async def on_message(event):
        msg = event.data

        if msg.get("type") == "content_block_delta":
            # Stream tokens to stdout
            delta = msg.get("delta", {})
            if text := delta.get("text"):
                print(text, end="", flush=True)

        elif msg.get("type") == "message_stop":
            # End of response
            print("\n")
            await ws.close()

        elif msg.get("type") == "error":
            print(f"\nError: {msg.get('error', {}).get('message')}")
            await ws.close()

    @ws.on("error")
    async def on_error(event):
        print(f"\nConnection error: {event.message}")

    await ws.run()


async def main() -> None:
    """Run the streaming example."""
    prompt = "Explain WebSockets in 3 sentences."
    print(f"Prompt: {prompt}\n")
    print("Response: ", end="")
    await stream_completion(prompt)


if __name__ == "__main__":
    asyncio.run(main())
```

## Key Concepts

### LLM Preset

The `llm_stream` preset is optimized for LLM APIs:

```python
from wsfabric.presets import llm_stream

ws = llm_stream("wss://api.example.com/v1/stream")
```

Settings:
- Quick retry with limited attempts (don't wait forever)
- Longer heartbeat interval (less overhead)
- Large max message size (128MB for long responses)
- Compression disabled (token streaming doesn't benefit)

### Token Streaming

LLM APIs typically send tokens one at a time:

```python
if text := delta.get("text"):
    print(text, end="", flush=True)  # Print without newline
```

### Event-Driven Pattern

Use events for clean handling of the streaming lifecycle:

```python
@ws.on("connected")
async def on_connected(event):
    await ws.send(request)

@ws.on("message")
async def on_message(event):
    process_token(event.data)
```

## Variations

### With Authentication

```python
from wsfabric.presets import llm_stream

ws = llm_stream(
    "wss://api.example.com/v1/stream",
    headers={"Authorization": f"Bearer {API_KEY}"},
)
```

### Custom Timeout

```python
from wsfabric.presets import llm_stream

ws = llm_stream(
    "wss://api.example.com/v1/stream",
    heartbeat=HeartbeatConfig(interval=60.0, timeout=30.0),
)
```

### Accumulate Full Response

```python
response_text = []

@ws.on("message")
async def on_message(event):
    if text := event.data.get("delta", {}).get("text"):
        response_text.append(text)

# After streaming
full_response = "".join(response_text)
```

## Error Handling

The LLM preset limits retries to prevent hanging on API failures:

```python
backoff=BackoffConfig(
    base=1.0,
    multiplier=2.0,
    cap=10.0,
    max_attempts=5,  # Don't retry forever
)
```

For critical applications, handle the final failure:

```python
@ws.on("error")
async def on_error(event):
    if "max retries exceeded" in str(event.error):
        # Fallback to REST API or notify user
        pass
```
