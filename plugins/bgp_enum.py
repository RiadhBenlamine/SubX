import asyncio

import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=15)
_MAX_RETRIES = 3


class BgpPlugin(Plugin):
    """Enumerates subdomains via BGP.he.net certificate API (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://bgp.he.net/certs/api/list?domain={domain}"
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
        }

        await asyncio.sleep(1)
        subdomains = []

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
                        if resp.status != 200:
                            self.logger.warning("HTTP %d for '%s'.", resp.status, domain)
                            return subdomains
                        data = await resp.json()
                        for entry in data.get("domains", []):
                            if name := entry.get("domain"):
                                subdomains.append(name)
                        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
                        return subdomains
            except (aiohttp.ClientError, TimeoutError) as e:
                self.logger.warning(
                    "Attempt %d/%d failed for '%s': %s", attempt, _MAX_RETRIES, domain, e
                )
                await asyncio.sleep(2 ** (attempt - 1))

        return subdomains