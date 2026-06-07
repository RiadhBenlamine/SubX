import aiohttp
from core.plugin import Plugin

class ChaosPlugin(Plugin):
    api_url = "https://dns.projectdiscovery.io/dns/"

    def required_keys(self) -> list:
        return ["CHAOS_API"]

    async def run(self, domain: str) -> list[str]:
        headers = {"Authorization": self.config.get("CHAOS_API")}
        full_url = self.api_url + domain + "/subdomains"
        async with aiohttp.ClientSession(headers=headers) as session:
            pass
        return [""]