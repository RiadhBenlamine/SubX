"""HackerTarget host search subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginRateLimitError
from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class HackerTargetPlugin(Plugin):
    """Enumerates subdomains via HackerTarget host search API (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://api.hackertarget.com/hostsearch/?q={domain}"

        async with self.session(timeout=_TIMEOUT) as session:
            async with session.get(url) as resp:
                data = await resp.text()

        if "API count exceeded" in data:
            raise PluginRateLimitError(f"HackerTarget rate limit: {data}")

        subdomains = [
            line.split(",")[0]
            for line in data.splitlines()
            if line.strip()
        ]

        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains
