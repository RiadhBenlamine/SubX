"""VirusTotal relationship subdomain enumeration plugin."""
import aiohttp

from core.errors import (PluginAuthError, PluginRateLimitError,
                         PluginUnavailableError)
from core.plugin import Plugin

MAX_RATE_LIMIT_RETRIES = 3
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class VirustotalPlugin(Plugin):
    """Enumerates subdomains via VirusTotal relationships API."""

    BASE_URL = "https://www.virustotal.com/api/v3"

    @property
    def required_keys(self) -> list[str]:
        return ["VIRUSTOTAL_API"]

    async def run(self, domain: str):
        subdomains = []
        url = f"{self.BASE_URL}/domains/{domain}/relationships/subdomains?limit=40"
        headers = {"X-Apikey": self.config["VIRUSTOTAL_API"]}

        try:
            async with self.session(headers=headers, timeout=_TIMEOUT) as session:
                while url:
                    try:
                        async with session.get(url) as response:
                            data = await response.json()
                    except PluginAuthError:
                        self.logger.warning(
                            "Quota exhausted/Authentication failure. "
                            "Returning collected subdomains."
                        )
                        return subdomains
                    except PluginRateLimitError as e:
                        raise PluginRateLimitError(str(e), subdomains) from e
                    except PluginUnavailableError as e:
                        raise PluginRateLimitError(str(e), subdomains) from e

                    batch = [item["id"] for item in data.get("data", [])]
                    subdomains.extend(batch)
                    self.logger.info("Fetched %d subdomains so far...", len(subdomains))

                    url = data.get("links", {}).get("next")
        except PluginRateLimitError:
            raise
        except Exception as e:
            raise PluginUnavailableError(f"VirusTotal API connection issue: {e}") from e

        self.logger.info("Total subdomains found: %d", len(subdomains))
        return subdomains
