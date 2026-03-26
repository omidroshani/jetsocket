# LLM Streaming

Stream responses from OpenAI via WebSocket using the Responses API.

## Run It

```bash
OPENAI_API_KEY="sk-..." uv run python examples/llm_streaming.py
```

Requires an [OpenAI API key](https://platform.openai.com/api-keys).

## Overview

- Connect to OpenAI's Responses API WebSocket endpoint
- Use the `llm_stream` preset for optimal settings
- Handle token-by-token streaming
- Graceful error handling

## Full Code

```python
"""Stream LLM responses via WebSocket using OpenAI Responses API."""

from __future__ import annotations

import asyncio
import os
import ssl

from jetsocket.presets import llm_stream


async def stream_completion(prompt: str, model: str = "gpt-4o-mini") -> None:
    """Stream a completion from OpenAI via WebSocket."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is required")
        return

    uri = "wss://api.openai.com/v1/responses"

    # Use LLM preset with auth headers
    ws = llm_stream(
        uri,
        extra_headers={
            "Authorization": f"Bearer {api_key}",
        },
        ssl_context=ssl.create_default_context(),
    )

    @ws.on("connected")
    async def on_connected(event: object) -> None:
        """Send prompt when connected."""
        await ws.send(
            {
                "type": "response.create",
                "model": model,
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            }
                        ],
                    }
                ],
            }
        )

    @ws.on("message")
    async def on_message(event: object) -> None:
        """Handle streaming response events."""
        msg = event.data
        msg_type = msg.get("type", "")

        if msg_type == "response.output_text.delta":
            # Stream tokens to stdout
            print(msg.get("delta", ""), end="", flush=True)

        elif msg_type == "response.completed":
            # End of response
            print("\n")
            await ws.close()

        elif msg_type == "error":
            print(f"\nError: {msg.get('error', {}).get('message')}")
            await ws.close()

    @ws.on("error")
    async def on_error(event: object) -> None:
        """Handle connection errors."""
        print(f"\nConnection error: {event}")

    await ws.connect()
    await ws.run()


async def main() -> None:
    """Run the streaming example."""
    prompt = "Explain WebSockets in 3 sentences."

    print(f"Prompt: {prompt}\n")
    print("Response: ", end="", flush=True)

    await stream_completion(prompt)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
```

## Key Concepts

### OpenAI Responses API WebSocket

OpenAI provides a WebSocket endpoint at `wss://api.openai.com/v1/responses` for streaming text responses. This is simpler and lower-latency than the Realtime API for text-only use cases.

The protocol flow:

1. Connect with `Authorization` header
2. Send `response.create` with your prompt
3. Receive `response.output_text.delta` events with streaming tokens
4. Receive `response.completed` when done

### LLM Preset

The `llm_stream` preset is optimized for LLM APIs:

```python
from jetsocket.presets import llm_stream

ws = llm_stream("wss://api.openai.com/v1/responses", extra_headers={...})
```

Settings:

- Quick retry with limited attempts (5 max — don't wait forever)
- Large max message size (128MB for long responses)
- Compression disabled (token streaming doesn't benefit)
- Small buffer (LLM streams are sequential)

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

### Accumulate Full Response

```python
response_text = []

@ws.on("message")
async def on_message(event):
    msg = event.data
    if msg.get("type") == "response.output_text.delta":
        response_text.append(msg.get("delta", ""))

# After streaming
full_response = "".join(response_text)
```

### Different Model

```python
await stream_completion("Write a haiku about Python", model="gpt-4o")
```
