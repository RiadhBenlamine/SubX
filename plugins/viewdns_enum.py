import aiohttp

from core.plugin import Plugin


class ViewDnsPlugin(Plugin):

    @property
    def required_keys(self) -> list[str]:
        return ["VIEWDNS_API"]

    async def run(self, domain: str) -> list[str]:
        subdomains = []

        try:
            async with aiohttp.ClientSession() as session:
                first_page = await self._fetch_page(session, domain, page=1)
                if not first_page:
                    return []

                subdomains.extend(self._extract(first_page))
                total_pages = self._get_pagination(first_page)

                for page in range(2, total_pages + 1):
                    data = await self._fetch_page(session, domain, page=page)
                    if data:
                        subdomains.extend(self._extract(data))

        except aiohttp.ClientError as e:
            self.logger.error("Request error: %s", e)

        return subdomains

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
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
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 429:
                    self.logger.warning("API credit is over (HTTP 429).")
                    return None
                self.logger.error("HTTP %d on page %d", resp.status, page)
                return None
        except aiohttp.ClientError as e:
            self.logger.error("Failed to fetch page %d: %s", page, e)
            return None

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