"""crt.sh CT search subdomain enumeration plugin."""
import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class CrtshPlugin(Plugin):
    """Enumerates subdomains via crt.sh certificate transparency logs (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://crt.sh/json?q={domain}"
        subdomains = []

        try:
            async with self.session(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    try:
                        entries = await resp.json(content_type=None)
                    except Exception:
                        self.logger.warning("crt.sh returned non-JSON response for '%s'.", domain)
                        return []
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict) and (name := entry.get("common_name")):
                                subdomains.append(name)
        except Exception as e:
            self.logger.warning("crt.sh fetch failed for '%s': %s", domain, e)
            return []

        return subdomains
