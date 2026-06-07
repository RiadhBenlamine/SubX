import logging
from core.plugin import Plugin

logger = logging.getLogger(__name__)


class CensysPlugin(Plugin):
    def __init__(self, config: dict):
        super().__init__(config)

    @property
    def required_keys(self) -> list[str]:
        return ["CENSYS_API"]

    async def run(self, domain: str):
        try:
            from censys_platform import SDK
        except ImportError:
            logger.warning("[Censys] censys-platform SDK not installed, skipping.")
            return []

        subdomains = set()

        try:
            async with SDK(
                personal_access_token=self.config["CENSYS_API"],
            ) as sdk:
                res = await sdk.global_data.search_async(search_query_input_body={
                    "fields": [
                        "host.name",
                    ],
                    "page_size": 100,
                    "query": f'host.name: *.{domain}',
                })

                # Extract subdomain strings from SDK response
                if isinstance(res, dict):
                    for hit in res.get("hits", []):
                        name = hit.get("host", {}).get("name")
                        if name and isinstance(name, str):
                            subdomains.add(name.strip().lower())
                elif hasattr(res, "hits"):
                    for hit in res.hits:
                        host = getattr(hit, "host", None)
                        if host:
                            name = getattr(host, "name", None)
                            if name and isinstance(name, str):
                                subdomains.add(name.strip().lower())

        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "rate" in err_str or "limit" in err_str or "403" in err_str or "429" in err_str:
                logger.warning("[Censys] Quota/rate limit exceeded, skipping: %s", e)
            else:
                logger.error("[Censys] API error, skipping: %s", e)
            return list(subdomains)

        logger.info("[Censys] Total unique subdomains: %d", len(subdomains))
        return list(subdomains)
