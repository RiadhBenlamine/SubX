import aiohttp
import asyncio
import logging
from core.plugin import Plugin

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 3
MAX_PAGES = 50


class UrlscanPlugin(Plugin):
    BASE_URL = "https://urlscan.io/api/v1"

    @property
    def required_keys(self) -> list[str]:
        return ["URLSCAN_API"]

    async def run(self, domain: str):
        subdomains = set()
        headers = {
            "API-Key": self.config["URLSCAN_API"],
            "Content-Type": "application/json",
        }

        query = f"domain:{domain}"
        url = f"{self.BASE_URL}/search/"
        params = {
            "q": query,
            "size": 1000,
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                page = 1
                while url and page <= MAX_PAGES:
                    rate_limit_retries = 0

                    while True:
                        try:
                            async with session.get(url, params=params) as response:
                                if response.status in (401, 403):
                                    logger.warning(
                                        "[Urlscan] Unauthorized/Quota exhausted (HTTP %d). "
                                        "Returning %d subdomains collected so far.",
                                        response.status,
                                        len(subdomains),
                                    )
                                    return list(subdomains)

                                if response.status == 429:
                                    rate_limit_retries += 1
                                    if rate_limit_retries > MAX_RATE_LIMIT_RETRIES:
                                        logger.warning(
                                            "[Urlscan] Rate limited %d times, giving up. "
                                            "Returning %d subdomains collected so far.",
                                            rate_limit_retries,
                                            len(subdomains),
                                        )
                                        return list(subdomains)

                                    retry_after = int(response.headers.get("Retry-After", 60))
                                    logger.warning(
                                        "[Urlscan] Rate limited, sleeping %ds (attempt %d/%d)",
                                        retry_after,
                                        rate_limit_retries,
                                        MAX_RATE_LIMIT_RETRIES,
                                    )
                                    await asyncio.sleep(retry_after)
                                    continue

                                response.raise_for_status()
                                data = await response.json()

                                results = data.get("results", [])
                                if not results:
                                    url = None
                                    break

                                for item in results:
                                    page_data = item.get("page", {})
                                    if hostname := page_data.get("hostname"):
                                        subdomains.add(hostname.strip().lower())
                                    if dom := page_data.get("domain"):
                                        subdomains.add(dom.strip().lower())

                                    task_data = item.get("task", {})
                                    if task_dom := task_data.get("domain"):
                                        subdomains.add(task_dom.strip().lower())

                                logger.info(
                                    "[Urlscan] Page %d: Fetched %d subdomains so far...",
                                    page,
                                    len(subdomains),
                                )

                                has_more = data.get("has_more", False)
                                if has_more and len(results) > 0:
                                    last_result = results[-1]
                                    sort_val = last_result.get("sort")
                                    if sort_val:
                                        params["search_after"] = ",".join(str(s) for s in sort_val)
                                        page += 1
                                    else:
                                        url = None
                                else:
                                    url = None
                                break

                        except aiohttp.ClientResponseError as e:
                            logger.error(
                                "[Urlscan] HTTP error %d: %s — skipping.",
                                e.status,
                                e.message,
                            )
                            return list(subdomains)

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("[Urlscan] Connection error, skipping: %s", e)

        logger.info("[Urlscan] Total subdomains found: %d", len(subdomains))
        return list(subdomains)
