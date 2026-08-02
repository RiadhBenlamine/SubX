"""Shodan search subdomain enumeration plugin."""
import asyncio

from shodan import Shodan
from shodan.exception import APIError as ShodanAPIError

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
from core.plugin import Plugin


class ShodanPlugin(Plugin):
    """Enumerates subdomains via Shodan search API."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._is_member: bool | None = None

    @property
    def required_keys(self) -> list[str]:
        return ["SHODAN_API"]

    async def _search_shodan(self, api, query, page=1):
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        try:
            return await asyncio.to_thread(api.search, query, page=page)
        except ShodanAPIError as e:
            err_str = str(e).lower()
            if "invalid api key" in err_str or "unauthorized" in err_str or "403" in err_str:
                raise PluginAuthError(f"Shodan auth failure: {e}") from e
            if self._is_quota_error(e) or "429" in err_str:
                raise PluginRateLimitError(f"Shodan rate limit/quota: {e}") from e
            raise PluginUnavailableError(f"Shodan API error: {e}") from e
        except Exception as e:  # pylint: disable=broad-exception-caught
            raise PluginUnavailableError(f"Shodan connection error: {e}") from e

    async def run(self, domain: str):  # pylint: disable=too-many-locals
        if self.tripped:
            raise PluginRateLimitError("ShodanPlugin skipped — circuit tripped.")

        try:
            api = Shodan(self.config["SHODAN_API"], timeout=15)
        except Exception as e:  # pylint: disable=broad-exception-caught
            raise PluginAuthError(f"Failed to initialize Shodan API client: {e}") from e

        try:
            is_member = await self._check_membership(api)
        except ShodanAPIError as e:
            err_str = str(e).lower()
            if "invalid api key" in err_str or "unauthorized" in err_str or "403" in err_str:
                raise PluginAuthError(f"Shodan auth failure: {e}") from e
            raise PluginUnavailableError(f"Shodan API error checking membership: {e}") from e
        except Exception as e:  # pylint: disable=broad-exception-caught
            raise PluginUnavailableError(f"Shodan error checking membership: {e}") from e

        page_cap = None if is_member else 10
        self.logger.info(
            "Plan: %s | page cap: %s",
            "member" if is_member else "free",
            page_cap or "unlimited",
        )

        subdomains = set()
        queries = [
            f"hostname:.{domain}",
            f"ssl.cert.subject.cn:.{domain}",
            f"ssl.cert.subject.alt_name:.{domain}",
        ]

        for query in queries:
            if len(subdomains) > 500 and query != f"hostname:.{domain}":
                self.logger.info("Skipping '%s', already have %d results", query, len(subdomains))
                continue

            try:
                results = await self._search_shodan(api, query, page=1)
                total = results.get("total", 0)

                if total == 0:
                    self.logger.info("Query '%s' -> no results, skipping.", query)
                    continue

                pages = max(1, (total + 99) // 100)
                if page_cap:
                    pages = min(pages, page_cap)

                self.logger.info("Query '%s' -> %d results (%d pages)", query, total, pages)

                self._extract(results, domain, subdomains)

                for page in range(2, pages + 1):
                    try:
                        page_results = await self._search_shodan(api, query, page=page)
                        self._extract(page_results, domain, subdomains)
                        self.logger.info(
                            "'%s' page %d/%d — %d unique subdomains so far",
                            query, page, pages, len(subdomains),
                        )
                    except PluginRateLimitError as e:
                        raise PluginRateLimitError(str(e), list(subdomains)) from e

            except PluginRateLimitError as e:
                raise PluginRateLimitError(str(e), list(subdomains)) from e

        self.logger.info("Total unique subdomains: %d", len(subdomains))
        return list(subdomains)

    @staticmethod
    def _is_quota_error(error: ShodanAPIError) -> bool:
        """Check if a Shodan API error is quota/credit related."""
        msg = str(error).lower()
        return any(kw in msg for kw in ("quota", "credit", "limit", "upgrade", "insufficient"))

    async def _check_membership(self, api: Shodan) -> bool | None:
        if self._is_member is not None:
            return self._is_member

        if self.rate_limiter:
            await self.rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(api.info)
            plan = info.get("plan", "")
            self._is_member = plan not in ("dev", "free", "")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.warning("Could not fetch account info, assuming free: %s", e)
            self._is_member = False

        return self._is_member

    def _extract(self, results: dict, domain: str, subdomains: set) -> None:
        for match in results.get("matches", []):
            for hostname in match.get("hostnames", []):
                if hostname.endswith(f".{domain}") or hostname == domain:
                    subdomains.add(hostname)

            ssl = match.get("ssl", {})
            cn = ssl.get("cert", {}).get("subject", {}).get("CN", "")
            if cn.endswith(f".{domain}") or cn == domain:
                subdomains.add(cn)

            for san in ssl.get("cert", {}).get("subject_alt_name", []):
                if san.endswith(f".{domain}") or san == domain:
                    subdomains.add(san)
