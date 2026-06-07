import logging
import aiohttp
from core.plugin import Plugin

logger = logging.getLogger(__name__)

class HackerTargetPlugin(Plugin):
    api = "https://api.hackertarget.com/hostsearch/?q="


    async def run(self, domain: str) -> list[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{self.api}{domain}') as response:
                    if response.status == 200:
                        data = await response.text()
                        subdomains = [line.split(',')[0] for line in data.splitlines()]
                    logger.warning("[HackerTarget] Got different status code")

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("[HackerTarget] Connection error, skipping: %s", e)

        logger.info("[VT] Total subdomains found: %d", len(subdomains))
        return subdomains
