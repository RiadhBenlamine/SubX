import asyncio
import logging
import aiohttp
from core.plugin import Plugin

logger = logging.getLogger(__name__)


class BgpPlugin(Plugin):
    BASE_URL = "https://bgp.he.net/certs/api/list?domain="
    HEADERS  = {
        "accept":     "application/json, text/javascript, */*; q=0.01",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    async def run(self, domain: str) -> list[str]:
        await asyncio.sleep(1)
        subdomains = []
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                            self.BASE_URL + domain,
                            headers=self.HEADERS,
                            timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status != 200:
                            logger.error("[BgpPlugin] HTTP %d for %s", resp.status, domain)
                            return subdomains
                        data = await resp.json()
                        for entry in data.get("domains", []):
                            if name := entry.get("domain"):
                                subdomains.append(name)
                        return subdomains

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error("[BgpPlugin] Attempt %d failed (%s): %s", attempt + 1, type(e).__name__, e)
                await asyncio.sleep(2 ** attempt)  # backoff: 1s, 2s, 4s

        return subdomains