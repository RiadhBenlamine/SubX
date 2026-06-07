import json
import logging
from core.plugin import Plugin
import aiohttp

logger = logging.getLogger(__name__)

class AnubisDbPlugin(Plugin):
    api_url = 'https://anubisdb.com/anubis/subdomains/'

    async def run(self, domain: str) -> list[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url + domain) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                    else:
                        logger.error(f"[AnubisDB] Error: Different status code {resp.status}")
        except (aiohttp.ClientError, json.decoder.JSONDecodeError) as e :
            print(e)
            logger.error(f"[AnubisDB] Error: {e}")
            return []
        return data