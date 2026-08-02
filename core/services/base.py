"""Base service classes and database singleton provider."""
import logging
from abc import ABC

from core.storage_manager import StorageManager, normalize_db_url

# Module-level shared engine — initialized once, reused across all services.
# pylint: disable=invalid-name
_shared_storage: StorageManager | None = None


# pylint: disable=global-statement
def _get_storage() -> StorageManager:
    """Return or create the shared StorageManager singleton."""
    global _shared_storage
    expected_url = normalize_db_url()
    if _shared_storage is None or _shared_storage.db_url != expected_url:
        _shared_storage = StorageManager(expected_url)
    return _shared_storage


class Service(ABC):
    """Base service class providing shared database access and logging."""

    def __init__(self, storage: StorageManager | None = None) -> None:
        self._custom_storage = storage

    @property
    def logger(self) -> logging.Logger:
        """Automatic logger matching subclass classname."""
        return logging.getLogger(self.__class__.__name__)

    @property
    def storage(self) -> StorageManager:
        """Access the custom or shared StorageManager instance."""
        return self._custom_storage or _get_storage()

    async def _with_storage(self, fn):
        """Execute a function with an initialized shared storage context."""
        storage = self.storage
        await storage.init()
        try:
            return await fn(storage)
        finally:
            pass  # Don't dispose — singleton is reused across calls
