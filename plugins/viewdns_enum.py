"""ViewDNS subdomain enumeration plugin."""
import aiohttp

from core.errors import PluginRateLimitError, PluginUnavailableError
from core.plugin import Plugin


_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5, sock_connect=5, sock_read=10)


class ViewDnsPlugin(Plugin):
    """Enumerates subdomains via ViewDNS API."""

    @property
    def required_keys(self) -> list[str]:
        return ["VIEWDNS_API"]

    async def run(self, domain: str) -> list[str]:
        subdomains = []

        try:
            async with self.session(timeout=_TIMEOUT) as session:
                first_page = await self._fetch_page(session, domain, page=1)
                if not first_page:
                    return []

                subdomains.extend(self._extract(first_page))
                total_pages = min(self._get_pagination(first_page), 20)

                for page in range(2, total_pages + 1):
                    data = await self._fetch_page(session, domain, page=page)
                    if data:
                        subdomains.extend(self._extract(data))

        except (PluginRateLimitError, PluginUnavailableError) as e:
            if isinstance(e, PluginRateLimitError):
                raise PluginRateLimitError(str(e), subdomains) from e
            raise

        return subdomains

    async def _fetch_page(
        self,
        session,
        domain: str,
        page: int,
    ) -> dict | None:
        url = (
            f"https://api.viewdns.info/subdomains/"
            f"?domain={domain}"
            f"&apikey={self.config['VIEWDNS_API']}"
            f"&output=json"
            f"&page={page}"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            return await resp.json()

    def _extract(self, json_data: dict) -> list[str]:
        """Pull subdomain names out of a response dict."""
        try:
            return [
                s["name"]
                for s in json_data["response"]["subdomains"]
                if s.get("name")
            ]
        except (KeyError, TypeError):
            self.logger.warning("Unexpected response structure.")
            return []

    @staticmethod
    def _get_pagination(json_data: dict) -> int:
        try:
            return int(json_data["query"]["total_pages"])
        except (KeyError, TypeError, ValueError):
            return 1
