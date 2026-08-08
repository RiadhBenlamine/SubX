"""AnubisDB subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=8, connect=3, sock_connect=3, sock_read=5)


class AnubisDbPlugin(Plugin):
    """Enumerates subdomains via AnubisDB (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://anubisdb.com/anubis/subdomains/{domain}"

        try:
            async with self.session(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
        except (PluginAuthError, PluginRateLimitError):
            raise
        except Exception as e:
            raise PluginUnavailableError(f"AnubisDB connection or parse error: {e}") from e

        if not isinstance(data, list):
            self.logger.warning(
                "Unexpected response type for '%s': %s",
                domain,
                type(data).__name__,
            )
            return []

        self.logger.info("Found %d subdomains for '%s'.", len(data), domain)
        return data
