"""Censys search subdomain enumeration plugin."""
from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
from core.plugin import Plugin

try:
    from censys_platform import SDK
except ImportError:
    SDK = None


class CensysPlugin(Plugin):
    """Enumerates subdomains via Censys search API."""

    @property
    def required_keys(self) -> list[str]:
        return ["CENSYS_API"]

    async def run(self, domain: str) -> list[str]:
        if SDK is None:
            self.logger.warning("censys-platform SDK not installed, skipping.")
            return []

        subdomains = set()

        try:
            if self.rate_limiter:
                await self.rate_limiter.acquire()
            async with SDK(
                personal_access_token=self.config["CENSYS_API"],
            ) as sdk:
                res = await sdk.global_data.search_async(
                    search_query_input_body={
                        "fields": ["host.name"],
                        "page_size": 100,
                        "query": f"host.name: *.{domain}",
                    }
                )

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

        except Exception as e:  # pylint: disable=broad-exception-caught
            err_str = str(e).lower()
            is_auth_error = any(
                kw in err_str
                for kw in ("401", "unauthorized", "403", "invalid")
            )
            is_rate_limit = any(
                kw in err_str
                for kw in ("quota", "rate", "limit", "429")
            )

            if is_auth_error:
                raise PluginAuthError(f"Censys auth failure: {e}") from e
            if is_rate_limit:
                raise PluginRateLimitError(
                    f"Censys rate limit/quota exceeded: {e}",
                    list(subdomains),
                ) from e
            raise PluginUnavailableError(f"Censys API error: {e}") from e

        self.logger.info("Total unique subdomains: %d", len(subdomains))
        return list(subdomains)
