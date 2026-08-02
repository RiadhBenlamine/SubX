"""BeVigil OSINT subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
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
            async with self.session(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()
        except (PluginAuthError, PluginRateLimitError, PluginUnavailableError):
            raise
        except Exception as e:
            raise PluginUnavailableError(f"BeVigil API error: {e}") from e

        subdomains = data.get("subdomains", []) if isinstance(data, dict) else []
        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains
