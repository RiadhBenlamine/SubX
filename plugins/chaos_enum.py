import aiohttp
from core.plugin import Plugin


class ChaosPlugin(Plugin):
    BASE_URL = "https://dns.projectdiscovery.io/dns"

    @property
    def required_keys(self) -> list[str]:
        return ["CHAOS_API"]

    async def run(self, domain: str) -> list[str]:
        url     = f"{self.BASE_URL}/{domain}/subdomains"
        headers = {"Authorization": self.config.get("CHAOS_API")}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 401:
                        self.logger.error("Invalid API key.")
                        return []
                    if resp.status == 404:
                        self.logger.warning("Domain %s not found in Chaos DB.", domain)
                        return []
                    if resp.status != 200:
                        self.logger.error("HTTP %d for %s", resp.status, domain)
                        return []

                    data = await resp.json()
                    raw  = data.get("subdomains") or []
                    root = data.get("domain", domain)

                    return [f"{sub}.{root}" for sub in raw if sub]

        except aiohttp.ClientError as e:
            self.logger.error("Request error: %s", e)
            return []