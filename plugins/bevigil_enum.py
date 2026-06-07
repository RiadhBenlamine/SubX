import aiohttp
import logging
from core.plugin import Plugin

log = logging.getLogger(__name__)

class BevigilPlugin(Plugin):

    @property
    def required_keys(self) -> list[str]:
        return ["BEVIGIL_API"]

    async def run(self, domain: str) -> list[str]:
        api_url = f"http://osint.bevigil.com/api/{domain}/subdomains/"
        headers = {
            "X-Access-Token": self.config["BEVIGIL_API"],
        }

        subdomains = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        subdomains = data.get("subdomains", [])
                    else:
                        log.error(f"[BevigilPlugin] HTTP error: {resp.status}")

        except aiohttp.ClientError as e:
            log.error(f"[BevigilPlugin] Request error: {e}")

        return subdomains