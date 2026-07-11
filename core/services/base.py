from abc import ABC
import logging
from core.storage_manager import StorageManager

# Module-level shared engine — initialized once, reused across all services.
_shared_storage: StorageManager | None = None


def _get_storage() -> StorageManager:
    """Return or create the shared StorageManager singleton."""
    global _shared_storage
    if _shared_storage is None:
        _shared_storage = StorageManager()
    return _shared_storage


class Service(ABC):
    """Base service class providing shared database access and logging."""

    @property
    def logger(self) -> logging.Logger:
        """Automatic logger matching subclass classname."""
        return logging.getLogger(self.__class__.__name__)

    @property
    def storage(self) -> StorageManager:
        """Access the shared StorageManager singleton."""
        return _get_storage()

    async def _with_storage(self, fn):
        """Execute a function with an initialized shared storage context."""
        storage = self.storage
        await storage.init()
        try:
            return await fn(storage)
        finally:
            pass  # Don't dispose — singleton is reused across calls
