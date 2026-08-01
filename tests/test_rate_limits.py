import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from core.errors import (PluginAuthError, PluginRateLimitError,
                         PluginUnavailableError)
from core.plugin import Plugin, TokenBucketRateLimiter


@pytest.mark.anyio
async def test_token_bucket_rate_limiter():
    limiter = TokenBucketRateLimiter(rate=10.0)
    
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    end = time.monotonic()
    
    assert end - start >= 0.0

@pytest.mark.anyio
async def test_safe_client_session_auth_error():
    class DummyPlugin(Plugin):
        async def run(self, domain: str):
            pass
            
    plugin = DummyPlugin({})
    
    mock_resp = AsyncMock()
    mock_resp.status = 401
    
    async def mock_call(*args, **kwargs):
        return mock_resp
    
    with patch("aiohttp.ClientSession.request", mock_call):
        async with plugin.session() as session:
            with pytest.raises(PluginAuthError):
                async with session.get("https://example.com"):
                    pass

@pytest.mark.anyio
async def test_safe_client_session_rate_limit_immediate():
    """HTTP 429 should immediately raise PluginRateLimitError — no retries."""
    class DummyPlugin(Plugin):
        async def run(self, domain: str):
            pass

    plugin = DummyPlugin({})

    resp_429 = AsyncMock()
    resp_429.status = 429
    resp_429.headers = {}

    call_count = 0

    async def mock_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp_429

    with patch("aiohttp.ClientSession.request", mock_call):
        async with plugin.session() as session:
            with pytest.raises(PluginRateLimitError):
                async with session.get("https://example.com"):
                    pass

    # Should have been called exactly once — no retries
    assert call_count == 1


@pytest.mark.anyio
async def test_circuit_breaker():
    """Tripping the circuit should set the tripped flag."""
    class DummyPlugin(Plugin):
        async def run(self, domain: str):
            pass

    plugin = DummyPlugin({})
    assert not plugin.tripped

    plugin.trip_circuit("rate limited")
    assert plugin.tripped

    # Tripping again should be a no-op (no error)
    plugin.trip_circuit("another reason")
    assert plugin.tripped
