"""urlscan.io subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
from core.plugin import Plugin

MAX_RATE_LIMIT_RETRIES = 3
MAX_PAGES = 50
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class UrlscanPlugin(Plugin):
    """Enumerates subdomains via urlscan.io API."""

    BASE_URL = "https://urlscan.io/api/v1"

    @property
    def required_keys(self) -> list[str]:
        return ["URLSCAN_API"]

    async def run(self, domain: str):  # pylint: disable=too-many-locals,too-many-branches
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
            async with self.session(headers=headers, timeout=_TIMEOUT) as session:
                page = 1
                while url and page <= MAX_PAGES:
                    try:
                        async with session.get(url, params=params) as response:
                            data = await response.json()
                    except PluginAuthError:
                        self.logger.warning(
                            "Unauthorized/Quota exhausted. Returning collected subdomains."
                        )
                        return list(subdomains)
                    except PluginRateLimitError as e:
                        raise PluginRateLimitError(str(e), list(subdomains)) from e
                    except PluginUnavailableError as e:
                        raise PluginRateLimitError(str(e), list(subdomains)) from e

                    results = data.get("results", [])
                    if not results:
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

                    self.logger.info(
                        "Page %d: Fetched %d subdomains so far...",
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
        except PluginRateLimitError:
            raise
        except Exception as e:
            raise PluginUnavailableError(f"Urlscan API connection issue: {e}") from e

        self.logger.info("Total subdomains found: %d", len(subdomains))
        return list(subdomains)
