"""Base classes and utility wrappers for subdomain discovery plugins, rate limiters, and clients."""
import asyncio
import logging
import socket
import time
from abc import ABC, abstractmethod

import aiohttp

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError

# Sensible default so plugins that don't specify a timeout can't hang indefinitely.
_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=5, sock_connect=5, sock_read=25)


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
        """Acquire a token from the bucket, sleeping if necessary until one becomes available.

        The lock is released *before* sleeping so that:
          - Other coroutines waiting on the same limiter are not starved.
          - ``asyncio.wait_for`` can cancel the sleep (and therefore the
            enclosing ``Plugin.run``) instead of blocking behind the lock.
        """
        while True:
            async with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                sleep_time = (1.0 - self.tokens) / self.rate
            # Sleep OUTSIDE the lock so other callers and cancellation can proceed
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
                    await resp.release()
                    raise PluginAuthError(
                        f"HTTP {resp.status} - Authentication/Authorization failure."
                    )
                if resp.status == 429:
                    await resp.release()
                    raise PluginRateLimitError(
                        "HTTP 429 - Rate limit exceeded."
                    )
                if resp.status >= 500:
                    await resp.release()
                    if attempt == attempts:
                        raise PluginUnavailableError(
                            f"HTTP {resp.status} - Source is temporarily unavailable."
                        )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue

                self.response = resp
                return resp
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                if isinstance(e, (asyncio.TimeoutError, socket.gaierror, TimeoutError)) or attempt == attempts:
                    raise PluginUnavailableError(
                        f"Connection / Timeout error: {e}"
                    ) from e
                await asyncio.sleep(backoff)
                backoff *= 2.0

        # Guard: all retry attempts exhausted without returning or raising.
        raise PluginUnavailableError("All retry attempts exhausted.")

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
        self.connector = aiohttp.TCPConnector(family=socket.AF_INET, limit=50)
        self.session = aiohttp.ClientSession(
            headers=headers, timeout=timeout, connector=self.connector
        )

    async def __aenter__(self):
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            if not self.connector.closed:
                await self.connector.close()
            await asyncio.sleep(0.25)

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
        self._tripped = False

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
    def tripped(self) -> bool:
        """Return True if this plugin's circuit breaker has been tripped."""
        return self._tripped

    def trip_circuit(self, reason: str = "") -> None:
        """Trip the circuit breaker so this plugin is skipped for subsequent domains."""
        if not self._tripped:
            self.logger.warning(
                "Circuit tripped — skipping future calls. %s", reason
            )
            self._tripped = True

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
        """Generate a new SafeClientSession wrapper configured for the plugin.

        If no explicit timeout is provided, a sensible default (30s total) is
        applied so that unresponsive endpoints cannot hang indefinitely.
        """
        return SafeClientSession(self, headers=headers, timeout=timeout or _DEFAULT_TIMEOUT)

    @abstractmethod
    async def run(self, domain: str) -> list[str]:
        """Run this plugin against the target domain and return discovered subdomains."""
