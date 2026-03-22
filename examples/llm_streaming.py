"""Stream LLM responses via WebSocket.

This example demonstrates:
- Using the llm_stream preset for optimal settings
- Event-driven message handling
- Token-by-token streaming output
"""

from __future__ import annotations

import asyncio

from jetsocket.presets import llm_stream


async def stream_completion(uri: str, prompt: str) -> None:
    """Stream a completion from an LLM API.

    Args:
        uri: WebSocket URI of the LLM API.
        prompt: The prompt to send.
    """
    # Use LLM preset: quick retry, large messages, no compression
    ws = llm_stream(uri)

    @ws.on("connected")
    async def on_connected(event) -> None:
        # Send the prompt when connected
        await ws.send(
            {
                "type": "message",
                "role": "user",
                "content": prompt,
            }
        )

    @ws.on("message")
    async def on_message(event) -> None:
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
    async def on_error(event) -> None:
        print(f"\nConnection error: {event.message}")

    await ws.run()


async def main() -> None:
    """Run the streaming example."""
    # Replace with your actual LLM WebSocket endpoint
    uri = "wss://api.example.com/v1/stream"
    prompt = "Explain WebSockets in 3 sentences."

    print(f"Prompt: {prompt}\n")
    print("Response: ", end="")

    await stream_completion(uri, prompt)


if __name__ == "__main__":
    asyncio.run(main())
