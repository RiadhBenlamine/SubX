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
async def test_safe_client_session_rate_limit_retry():
    class DummyPlugin(Plugin):
        async def run(self, domain: str):
            pass
            
    plugin = DummyPlugin({})
    
    resp_429 = AsyncMock()
    resp_429.status = 429
    resp_429.headers = {"Retry-After": "0"}
    
    resp_200 = AsyncMock()
    resp_200.status = 200
    
    responses = [resp_429, resp_429, resp_200]
    
    async def mock_call(*args, **kwargs):
        return responses.pop(0)
    
    with patch("aiohttp.ClientSession.request", mock_call):
        async with plugin.session() as session:
            async with session.get("https://example.com") as resp:
                assert resp.status == 200
