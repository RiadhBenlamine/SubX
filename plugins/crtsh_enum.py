import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class CrtshPlugin(Plugin):
    """Enumerates subdomains via crt.sh certificate transparency logs (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://crt.sh/json?q={domain}"
        subdomains = []

        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.warning("HTTP %d for %s", resp.status, domain)
                        return []
                    entries = await resp.json()
                    for entry in entries:
                        if name := entry.get("common_name"):
                            subdomains.append(name)
        except (aiohttp.ClientError, TimeoutError) as e:
            self.logger.error("Request failed for %s: %s", domain, e)

        return subdomains