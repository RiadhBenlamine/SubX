"""Service layer for database operations."""
from datetime import datetime

from core.db_models import Subdomain
from core.services.base import Service


class DbService(Service):
    """Encapsulates all database query operations for the CLI."""

    async def get_summary(self) -> list[dict]:
        """Return a summary of all tracked target domains."""
        return await self._with_storage(lambda s: s.get_targets_summary())

    async def get_subdomains(
        self,
        domain: str,
        filter_plugin: str | None = None,
        new_since: datetime | None = None,
        filter_tech: str | None = None,
    ) -> list[Subdomain]:
        """Fetch subdomains for a domain with optional filters."""
        async def _query(storage) -> list[Subdomain]:
            if filter_plugin:
                return await storage.get_by_plugin(domain, filter_plugin)
            if filter_tech:
                return await storage.get_by_tech(domain, filter_tech)
            if new_since:
                return await storage.get_new_since(domain, new_since)
            return await storage.get_all(domain)

        return await self._with_storage(_query)

    async def delete_domain(self, domain: str) -> int:
        """Delete all records for a domain. Returns the number of rows deleted."""
        async def _delete(storage) -> int:
            return await storage.delete(domain)

        return await self._with_storage(_delete)

    async def raw_query(self, query: str) -> list[dict]:
        """Run a raw SELECT query against the database."""
        async def _raw(storage) -> list[dict]:
            return await storage.raw_query(query)

        return await self._with_storage(_raw)
