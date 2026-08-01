"""Chaos subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginUnavailableError
from core.plugin import Plugin


class ChaosPlugin(Plugin):
    """Enumerates subdomains via ProjectDiscovery Chaos API."""

    BASE_URL = "https://dns.projectdiscovery.io/dns"

    @property
    def required_keys(self) -> list[str]:
        return ["CHAOS_API"]

    async def run(self, domain: str) -> list[str]:
        url = f"{self.BASE_URL}/{domain}/subdomains"
        headers = {"Authorization": self.config.get("CHAOS_API")}

        try:
            async with self.session(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as session, session.get(url) as resp:
                data = await resp.json()
                raw = data.get("subdomains") or []
                root = data.get("domain", domain)
                return [f"{sub}.{root}" for sub in raw if sub]
        except PluginUnavailableError as e:
            if "HTTP 404" in str(e):
                self.logger.warning("Domain %s not found in Chaos DB.", domain)
                return []
            raise
