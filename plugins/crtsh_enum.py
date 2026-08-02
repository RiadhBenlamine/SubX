"""crt.sh CT search subdomain enumeration plugin."""
import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=7)


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
                            if isinstance(entry, dict):
                                if name := entry.get("common_name"):
                                    subdomains.append(name.strip())
                                if name_val := entry.get("name_value"):
                                    for sub in name_val.split("\n"):
                                        if sub_clean := sub.strip():
                                            subdomains.append(sub_clean)
        except Exception as e:
            self.logger.warning("crt.sh fetch failed for '%s': %s", domain, e)
            return []

        return subdomains
