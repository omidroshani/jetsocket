"""Integration tests for OpenAI Realtime WebSocket API."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from wsfabric.transport import AsyncTransport, BaseTransportConfig

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_WS = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"


@pytest.mark.llm
@pytest.mark.integration
@pytest.mark.skipif(not OPENAI_API_KEY, reason="OPENAI_API_KEY not set")
class TestOpenAIRealtime:
    """Test against OpenAI Realtime WebSocket API."""

    async def test_connect_with_auth(self) -> None:
        """Connect to OpenAI Realtime API with API key."""
        config = BaseTransportConfig(
            connect_timeout=15.0,
            read_timeout=15.0,
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1",
            },
        )
        transport = AsyncTransport(config)

        await transport.connect(OPENAI_WS)
        try:
            # Should receive session.created event
            frame = await asyncio.wait_for(transport.recv(), timeout=15.0)
            data = json.loads(frame.payload)
            assert data.get("type") == "session.created"
        finally:
            await transport.close()
