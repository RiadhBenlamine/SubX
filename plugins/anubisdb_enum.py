import json

import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class AnubisDbPlugin(Plugin):
    """Enumerates subdomains via AnubisDB (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://anubisdb.com/anubis/subdomains/{domain}"

        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.warning("HTTP %d for '%s'.", resp.status, domain)
                        return []
                    data = await resp.json()
        except (aiohttp.ClientError, json.JSONDecodeError, TimeoutError) as e:
            self.logger.error("Request failed for '%s': %s", domain, e)
            return []

        if not isinstance(data, list):
            self.logger.warning("Unexpected response type for '%s': %s", domain, type(data).__name__)
            return []

        self.logger.info("Found %d subdomains for '%s'.", len(data), domain)
        return data