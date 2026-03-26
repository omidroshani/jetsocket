"""Stream LLM responses via WebSocket using OpenAI Responses API.

This example demonstrates:
- Using the llm_stream preset for optimal settings
- Event-driven message handling
- Token-by-token streaming output
- OpenAI Responses API WebSocket mode

Requires OPENAI_API_KEY environment variable.
"""

from __future__ import annotations

import asyncio
import os
import ssl

from jetsocket.presets import llm_stream


async def stream_completion(prompt: str, model: str = "gpt-4o-mini") -> None:
    """Stream a completion from OpenAI via WebSocket.

    Args:
        prompt: The prompt to send.
        model: The model to use.
    """
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
        msg = event.data  # type: ignore[attr-defined]
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
