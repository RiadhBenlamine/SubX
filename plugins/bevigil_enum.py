"""BeVigil OSINT subdomain enumeration plugin."""
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

        async with self.session(timeout=_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

        subdomains = data.get("subdomains", [])
        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains
