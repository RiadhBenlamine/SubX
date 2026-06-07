import asyncio
import logging

import aiohttp

from core.plugin import Plugin

logger = logging.getLogger(__name__)

_URL = "https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class AlienVaultPlugin(Plugin):
    """
    Enumerates subdomains via AlienVault OTX passive DNS.
    OTX returns all records in a single response (no pagination needed).
    Requires OTX_API key — register free at otx.alienvault.com.
    """

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
                async with session.get(_URL.format(domain=domain)) as response:
                    if response.status == 403:
                        logger.error("[AlienVault] Invalid or unauthorized API key.")
                        return []
                    if response.status == 404:
                        logger.warning("[AlienVault] Domain '%s' not found in OTX.", domain)
                        return []
                    if response.status != 200:
                        logger.warning("[AlienVault] Unexpected status %d for '%s'.", response.status, domain)
                        return []

                    data = await response.json()

        except asyncio.TimeoutError:
            logger.error("[AlienVault] Timeout for '%s'.", domain)
            return []
        except aiohttp.ClientError as e:
            logger.error("[AlienVault] Request error for '%s': %s", domain, e)
            return []

        subdomains = {
            record["hostname"].strip().lower()
            for record in data.get("passive_dns", [])
            if record.get("hostname", "").strip().lower().endswith(f".{domain}")
            or record.get("hostname", "").strip().lower() == domain
        }

        logger.info("[AlienVault] Found %d unique subdomains for '%s'.", len(subdomains), domain)
        return list(subdomains)