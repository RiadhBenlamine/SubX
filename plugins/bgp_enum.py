"""BGP certificate search subdomain enumeration plugin."""
import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=5, connect=2, sock_connect=2, sock_read=3)


class BgpPlugin(Plugin):
    """Enumerates subdomains via BGP.he.net certificate API (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://bgp.he.net/certs/api/list?domain={domain}"
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
        }

        subdomains = []
        try:
            async with self.session(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=headers) as resp:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        return []
                    if isinstance(data, dict):
                        for entry in data.get("domains", []):
                            if isinstance(entry, dict) and (name := entry.get("domain")):
                                subdomains.append(name)
        except Exception as e:
            self.logger.warning("BGP fetch failed for '%s': %s", domain, e)
            return []

        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains
