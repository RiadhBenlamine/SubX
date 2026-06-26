import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class BevigilPlugin(Plugin):
    """Enumerates subdomains via BeVigil OSINT API."""

    @property
    def required_keys(self) -> list[str]:
        return ["BEVIGIL_API"]

    async def run(self, domain: str) -> list[str]:
        url = f"http://osint.bevigil.com/api/{domain}/subdomains/"
        headers = {"X-Access-Token": self.config["BEVIGIL_API"]}

        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        self.logger.warning("HTTP %d for '%s'.", resp.status, domain)
                        return []
                    data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as e:
            self.logger.error("Request failed for '%s': %s", domain, e)
            return []

        subdomains = data.get("subdomains", [])
        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains