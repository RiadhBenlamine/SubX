"""crt.sh CT search subdomain enumeration plugin."""
import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class CrtshPlugin(Plugin):
    """Enumerates subdomains via crt.sh certificate transparency logs (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://crt.sh/json?q={domain}"
        subdomains = []

        async with self.session(timeout=_TIMEOUT) as session:
            async with session.get(url) as resp:
                entries = await resp.json()
                for entry in entries:
                    if name := entry.get("common_name"):
                        subdomains.append(name)

        return subdomains
