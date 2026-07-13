"""Service layer for database schema migrations."""
from core.services.base import Service


class MigrateService(Service):
    """Handles database schema migrations."""

    async def migrate(self, backup: bool = True) -> list[str]:
        """Run the migration and return a list of added column names."""
        return await self._with_storage(lambda storage: storage.migrate(backup=backup))
