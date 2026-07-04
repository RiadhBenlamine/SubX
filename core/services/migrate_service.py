from core.storage_manager import StorageManager


class MigrateService:
    """Handles database schema migrations."""

    async def migrate(self, backup: bool = True) -> list[str]:
        """Run the migration and return a list of added column names."""
        storage = StorageManager()
        await storage.init()
        try:
            return await storage.migrate(backup=backup)
        finally:
            await storage.close()
