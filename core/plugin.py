"""Base classes and utility wrappers for subdomain discovery plugins, rate limiters, and clients."""
import asyncio
import logging
import time
from abc import ABC, abstractmethod

import aiohttp

from core.errors import (PluginAuthError, PluginRateLimitError,
                         PluginUnavailableError)


# pylint: disable=too-few-public-methods
class TokenBucketRateLimiter:
    """A thread/async-safe token bucket rate limiter implementation."""

    def __init__(self, rate: float):
        self.rate = rate
        self.capacity = max(1.0, rate)
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token from the bucket, sleeping if necessary until one becomes available."""
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                sleep_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)


class SafeRequestContext:
    """Asynchronous context manager providing automated backoff and retry.

    Implements query retries for API queries.
    """

    def __init__(
        self,
        plugin: "Plugin",
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        **kwargs,
    ):
        self.plugin = plugin
        self.session = session
        self.method = method
        self.url = url
        self.kwargs = kwargs
        self.response = None

    async def __aenter__(self):
        if self.plugin.rate_limiter:
            await self.plugin.rate_limiter.acquire()

        attempts = 3
        backoff = 1.0

        for attempt in range(1, attempts + 1):
            try:
                resp = await self.session.request(self.method, self.url, **self.kwargs)
                if resp.status in (401, 403):
                    raise PluginAuthError(
                        f"HTTP {resp.status} - Authentication/Authorization failure."
                    )
                if resp.status == 429:
                    if attempt == attempts:
                        raise PluginRateLimitError(
                            f"HTTP 429 - Rate limit exceeded after {attempts} attempts."
                        )
                    retry_after = resp.headers.get("Retry-After") or resp.headers.get(
                        "X-RateLimit-Reset"
                    )
                    try:
                        sleep_time = int(retry_after) if retry_after else backoff
                    except ValueError:
                        sleep_time = backoff
                    await asyncio.sleep(sleep_time)
                    backoff *= 2.0
                    continue
                if resp.status >= 500:
                    if attempt == attempts:
                        raise PluginUnavailableError(
                            f"HTTP {resp.status} - Source is temporarily unavailable."
                        )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue

                self.response = resp
                return resp
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == attempts:
                    raise PluginUnavailableError(
                        f"Connection / Timeout error after {attempts} attempts: {e}"
                    ) from e
                await asyncio.sleep(backoff)
                backoff *= 2.0

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.response:
            await self.response.release()


class SafeClientSession:
    """Wrapped aiohttp ClientSession implementing rate-limiting and query retries."""

    def __init__(
        self,
        plugin: "Plugin",
        headers: dict | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
    ):
        self.plugin = plugin
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)

    async def __aenter__(self):
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.__aexit__(exc_type, exc_val, exc_tb)

    def request(self, method: str, url: str, **kwargs) -> SafeRequestContext:
        """Create a SafeRequestContext context manager wrapper for the HTTP query request."""
        return SafeRequestContext(self.plugin, self.session, method, url, **kwargs)

    def get(self, url: str, **kwargs) -> SafeRequestContext:
        """Generate a wrapped GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> SafeRequestContext:
        """Generate a wrapped POST request."""
        return self.request("POST", url, **kwargs)


class Plugin(ABC):
    """Abstract base class representing a passive subdomain enumeration engine source."""

    def __init__(self, config: dict):
        self.config = config

        rate_limits = config.get("rate_limits", {}) or {}
        limit = None
        if self.__class__.__name__ in rate_limits:
            limit = rate_limits[self.__class__.__name__]
        else:
            for key in self.required_keys:
                if key in rate_limits:
                    limit = rate_limits[key]
                    break

        self.rate_limiter = (
            TokenBucketRateLimiter(float(limit)) if limit is not None else None
        )

    @property
    def required_keys(self) -> list[str]:
        """A list of API credential keys required by this plugin."""
        return []

    @property
    def logger(self) -> logging.Logger:
        """Return a configured Logger instance corresponding to the subclass name."""
        return logging.getLogger(self.__class__.__name__)

    def is_configured(self) -> bool:
        """Return True if all credentials required by the plugin are loaded."""
        return all(
            self.config.get(key) not in (None, "") for key in self.required_keys
        )

    def session(
        self, headers: dict | None = None, timeout: aiohttp.ClientTimeout | None = None
    ) -> SafeClientSession:
        """Generate a new SafeClientSession wrapper configured for the plugin."""
        return SafeClientSession(self, headers=headers, timeout=timeout)

    @abstractmethod
    async def run(self, domain: str) -> list[str]:
        """Run this plugin against the target domain and return discovered subdomains."""
