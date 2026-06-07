import logging
import asyncio
from shodan import Shodan
from shodan.exception import APIError as ShodanAPIError
from core.plugin import Plugin

logger = logging.getLogger(__name__)


class ShodanPlugin(Plugin):

    def __init__(self, config: dict):
        super().__init__(config)
        self._is_member: bool | None = None

    @property
    def required_keys(self) -> list[str]:
        return ["SHODAN_API"]

    async def run(self, domain: str):
        try:
            api = Shodan(self.config["SHODAN_API"])
        except Exception as e:
            logger.error("[Shodan] Failed to initialize API client: %s", e)
            return []

        is_member = await self._check_membership(api)
        page_cap = None if is_member else 10
        logger.info(
            "[Shodan] Plan: %s | page cap: %s",
            "member" if is_member else "free",
            page_cap or "unlimited"
        )

        subdomains = set()
        queries = [
            f"hostname:.{domain}",
            f"ssl.cert.subject.cn:.{domain}",
            f"ssl.cert.subject.alt_name:.{domain}",
        ]

        for query in queries:
            if len(subdomains) > 500 and query != f"hostname:.{domain}":
                logger.info("[Shodan] Skipping '%s', already have %d results", query, len(subdomains))
                continue

            try:
                results = await asyncio.to_thread(api.search, query, page=1)
                total = results.get("total", 0)

                if total == 0:
                    logger.info("[Shodan] Query '%s' -> no results, skipping.", query)
                    continue

                pages = max(1, (total + 99) // 100)
                if page_cap:
                    pages = min(pages, page_cap)

                logger.info("[Shodan] Query '%s' -> %d results (%d pages)", query, total, pages)

                self._extract(results, domain, subdomains)

                for page in range(2, pages + 1):
                    try:
                        page_results = await asyncio.to_thread(api.search, query, page=page)
                        self._extract(page_results, domain, subdomains)
                        logger.info(
                            "[Shodan] '%s' page %d/%d — %d unique subdomains so far",
                            query, page, pages, len(subdomains)
                        )
                    except ShodanAPIError as e:
                        if self._is_quota_error(e):
                            logger.warning(
                                "[Shodan] Quota exceeded on page %d of '%s', "
                                "returning %d subdomains collected so far.",
                                page, query, len(subdomains),
                            )
                            return list(subdomains)
                        logger.error("[Shodan] API error on page %d of '%s': %s", page, query, e)
                        break

            except ShodanAPIError as e:
                if self._is_quota_error(e):
                    logger.warning(
                        "[Shodan] Quota exceeded on query '%s', "
                        "returning %d subdomains collected so far.",
                        query, len(subdomains),
                    )
                    return list(subdomains)
                logger.error("[Shodan] Query '%s' failed: %s", query, e)
                continue
            except Exception as e:
                logger.error("[Shodan] Unexpected error on query '%s': %s", query, e)
                continue

        logger.info("[Shodan] Total unique subdomains: %d", len(subdomains))
        return list(subdomains)

    @staticmethod
    def _is_quota_error(error: ShodanAPIError) -> bool:
        """Check if a Shodan API error is quota/credit related."""
        msg = str(error).lower()
        return any(kw in msg for kw in ("quota", "credit", "limit", "upgrade", "insufficient"))

    async def _check_membership(self, api: Shodan) -> bool | None:
        if self._is_member is not None:
            return self._is_member

        try:
            info = await asyncio.to_thread(api.info)
            plan = info.get("plan", "")
            self._is_member = plan not in ("dev", "free", "")
        except Exception as e:
            logger.warning("[Shodan] Could not fetch account info, assuming free: %s", e)
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