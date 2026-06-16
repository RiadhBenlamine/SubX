from core.plugin import Plugin
import aiohttp

class CrtshPlugin(Plugin):

    async def run(self, domain : str) -> list[str]:
        api_url = f"https://crt.sh/json?q={domain}"
        subdomains = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        entries = resp.json()
                        for entry in entries:
                            subdomains.append(entry["common_name"])
                    else:
                        self.logger.warning(f"Getting different status code, {resp.status}")

        except (KeyError, aiohttp.ClientError, aiohttp.ClientTimeout) as e:
            self.logger.error(f"Error: {e}")
        return subdomains