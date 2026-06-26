import aiohttp

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
            async with aiohttp.ClientSession(headers=headers, timeout=_TIMEOUT) as session:
                async with session.get(_URL.format(domain=domain)) as resp:
                    if resp.status == 403:
                        self.logger.error("Invalid or unauthorized API key.")
                        return []
                    if resp.status == 404:
                        self.logger.warning("Domain '%s' not found in OTX.", domain)
                        return []
                    if resp.status != 200:
                        self.logger.warning("HTTP %d for '%s'.", resp.status, domain)
                        return []
                    data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as e:
            self.logger.error("Request failed for '%s': %s", domain, e)
            return []

        subdomains = {
            record["hostname"].strip().lower()
            for record in data.get("passive_dns", [])
            if record.get("hostname", "").strip().lower().endswith(f".{domain}")
            or record.get("hostname", "").strip().lower() == domain
        }

        self.logger.info("Found %d unique subdomains for '%s'.", len(subdomains), domain)
        return list(subdomains)