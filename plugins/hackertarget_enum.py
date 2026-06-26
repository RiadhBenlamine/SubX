import aiohttp

from core.plugin import Plugin

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class HackerTargetPlugin(Plugin):
    """Enumerates subdomains via HackerTarget host search API (no auth)."""

    async def run(self, domain: str) -> list[str]:
        url = f"https://api.hackertarget.com/hostsearch/?q={domain}"
        subdomains = []

        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.warning("HTTP %d for '%s'.", resp.status, domain)
                        return []
                    data = await resp.text()

            if "API count exceeded" in data:
                self.logger.warning("API quota exceeded for '%s'.", domain)
                return []

            subdomains = [
                line.split(",")[0]
                for line in data.splitlines()
                if line.strip()
            ]
        except (aiohttp.ClientError, TimeoutError) as e:
            self.logger.error("Request failed for '%s': %s", domain, e)
            return []

        self.logger.info("Found %d subdomains for '%s'.", len(subdomains), domain)
        return subdomains
