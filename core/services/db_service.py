from datetime import datetime

from core.db_models import Subdomain
from core.storage_manager import StorageManager


class DbService:
    """Encapsulates all database query operations for the CLI."""

    async def get_summary(self) -> list[dict]:
        """Return a summary of all tracked target domains."""
        return await self._with_storage(lambda s: s.get_targets_summary())

    async def get_subdomains(
        self,
        domain: str,
        filter_plugin: str | None = None,
        new_since: datetime | None = None,
    ) -> list[Subdomain]:
        """Fetch subdomains for a domain with optional filters."""
        async def _query(storage: StorageManager) -> list[Subdomain]:
            if filter_plugin:
                return await storage.get_by_plugin(domain, filter_plugin)
            elif new_since:
                return await storage.get_new_since(domain, new_since)
            else:
                return await storage.get_all(domain)

        return await self._with_storage(_query)

    async def delete_domain(self, domain: str) -> int:
        """Delete all records for a domain. Returns the number of rows deleted."""
        async def _delete(storage: StorageManager) -> int:
            return await storage.delete(domain)

        return await self._with_storage(_delete)

    async def raw_query(self, query: str) -> list[dict]:
        """Run a raw SELECT query against the database."""
        async def _raw(storage: StorageManager) -> list[dict]:
            return await storage.raw_query(query)

        return await self._with_storage(_raw)

    async def _with_storage(self, fn):
        """Open storage, run fn, close storage — guarantees cleanup."""
        storage = StorageManager()
        await storage.init()
        try:
            return await fn(storage)
        finally:
            await storage.close()
