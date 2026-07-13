"""AnubisDB subdomain enumeration plugin."""
import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class AnubisDbPlugin(Plugin):
    """Enumerates subdomains via AnubisDB (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://anubisdb.com/anubis/subdomains/{domain}"

        async with self.session(timeout=_TIMEOUT) as session:
            async with session.get(url) as resp:
                data = await resp.json()

        if not isinstance(data, list):
            self.logger.warning(
                "Unexpected response type for '%s': %s",
                domain,
                type(data).__name__,
            )
            return []

        self.logger.info("Found %d subdomains for '%s'.", len(data), domain)
        return data
