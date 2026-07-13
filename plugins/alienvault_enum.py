"""AlienVault passive DNS subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginUnavailableError
from core.plugin import Plugin

_URL = "https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class AlienVaultPlugin(Plugin):
    """Enumerates subdomains via AlienVault OTX passive DNS."""

    @property
    def required_keys(self) -> list[str]:
        return ["OTX_API"]

    async def run(self, domain: str) -> list[str]:
        headers = {
            "X-OTX-API-KEY": self.config["OTX_API"],
            "Content-Type": "application/json",
        }

        try:
            async with self.session(headers=headers, timeout=_TIMEOUT) as session:
                async with session.get(_URL.format(domain=domain)) as resp:
                    data = await resp.json()
        except PluginUnavailableError as e:
            if "HTTP 404" in str(e):
                self.logger.warning("Domain '%s' not found in OTX.", domain)
                return []
            raise

        subdomains = {
            record["hostname"].strip().lower()
            for record in data.get("passive_dns", [])
            if record.get("hostname", "").strip().lower().endswith(f".{domain}")
            or record.get("hostname", "").strip().lower() == domain
        }

        self.logger.info("Found %d unique subdomains for '%s'.", len(subdomains), domain)
        return list(subdomains)
