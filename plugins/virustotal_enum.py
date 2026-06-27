import asyncio

import aiohttp

from core.plugin import Plugin

MAX_RATE_LIMIT_RETRIES = 3
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class VirustotalPlugin(Plugin):
    BASE_URL = "https://www.virustotal.com/api/v3"

    @property
    def required_keys(self) -> list[str]:
        return ["VIRUSTOTAL_API"]

    async def run(self, domain: str):
        subdomains = []
        url = f"{self.BASE_URL}/domains/{domain}/relationships/subdomains?limit=40"
        headers = {"X-Apikey": self.config["VIRUSTOTAL_API"]}

        try:
            async with aiohttp.ClientSession(headers=headers, timeout=_TIMEOUT) as session:
                while url:
                    rate_limit_retries = 0

                    while True:
                        try:
                            async with session.get(url) as response:

                                if response.status == 403:
                                    self.logger.warning(
                                        "Quota exhausted (HTTP 403), skipping. "
                                        "Returning %d subdomains collected so far.",
                                        len(subdomains),
                                    )
                                    return subdomains

                                if response.status == 429:
                                    rate_limit_retries += 1
                                    if rate_limit_retries > MAX_RATE_LIMIT_RETRIES:
                                        self.logger.warning(
                                            "Rate limited %d times, giving up. "
                                            "Returning %d subdomains collected so far.",
                                            rate_limit_retries,
                                            len(subdomains),
                                        )
                                        return subdomains

                                    retry_after = int(response.headers.get("Retry-After",
                                                      response.headers.get("X-RateLimit-Reset", 60)))
                                    self.logger.warning("Rate limited, sleeping %ds (attempt %d/%d)",
                                                   retry_after, rate_limit_retries, MAX_RATE_LIMIT_RETRIES)
                                    await asyncio.sleep(retry_after)
                                    continue

                                response.raise_for_status()
                                data = await response.json()

                                batch = [item["id"] for item in data.get("data", [])]
                                subdomains.extend(batch)
                                self.logger.info("Fetched %d subdomains so far...", len(subdomains))

                                url = data.get("links", {}).get("next")
                                break  # break inner retry loop, continue outer pagination loop

                        except aiohttp.ClientResponseError as e:
                            self.logger.error("HTTP error %d: %s — skipping.", e.status, e.message)
                            return subdomains

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.logger.error("Connection error, skipping: %s", e)

        self.logger.info("Total subdomains found: %d", len(subdomains))
        return subdomains