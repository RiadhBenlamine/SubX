import logging
import asyncio
from datetime import datetime, timezone
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from core.db_models import Subdomain
from core.models import ProcessedResult

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///subx.db"


class StorageManager:
    """
    Async storage layer for persisting subdomain recon results.

    Responsibilities:
        - Create database and tables on first run
        - Save ProcessedResult from Processor into Subdomain table
        - Track first_seen / last_seen per subdomain per target
        - Query subdomains by target, plugin, or date range
        - Detect new subdomains since last save (diff)

    Usage:
        storage = StorageManager()
        await storage.init()
        await storage.save(processed_result)
    """

    def __init__(self, db_url: str = DATABASE_URL):
        self.engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """
        Create database and all tables if they don't exist.
        Safe to call on every run — no-op if already initialized.
        Uses a lock to prevent race conditions on concurrent init calls.
        """
        async with self._init_lock:
            if self._initialized:
                return
            try:
                async with self.engine.begin() as conn:
                    await conn.run_sync(SQLModel.metadata.create_all)
                self._initialized = True
                logger.debug("[Storage] Database ready.")
            except SQLAlchemyError as e:
                logger.error("[Storage] Failed to initialize database: %s", e)
                raise

    async def save(self, result: ProcessedResult) -> int:
        """
        Persist all subdomains from a ProcessedResult.
        For each subdomain:
            - If new: insert with first_seen = now
            - If exists: update last_seen = now

        Args:
            result: ProcessedResult from Processor

        Returns:
            Number of new subdomains inserted.
        """
        self._ensure_initialized()

        new_count = 0

        async with self._session() as session:
            async with session.begin():
                for plugin_name, subdomains in result.by_plugin.items():
                    inserted = await self._upsert_batch(
                        session=session,
                        target=result.target,
                        subdomains=subdomains,
                        plugin_name=plugin_name,
                    )
                    new_count += inserted

        logger.debug("[Storage] Saved %d new subdomains for %s.", new_count, result.target)
        return new_count

    async def get_all(self, target: str) -> list[Subdomain]:
        """
        Retrieve all subdomains for a given target, ordered alphabetically.
        """
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(Subdomain.target == target)
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_by_plugin(self, target: str, plugin_name: str) -> list[Subdomain]:
        """
        Retrieve subdomains found by a specific plugin for a target,
        ordered alphabetically.
        """
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.source_plugin == plugin_name,
                )
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_new_since(self, target: str, since: datetime) -> list[Subdomain]:
        """
        Retrieve subdomains first seen after a given datetime.
        Useful for diffing between runs.
        """
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.first_seen >= since,
                )
                .order_by(Subdomain.first_seen.desc())
            )
            return list(result.scalars().all())

    async def count(self, target: str) -> int:
        """Return total number of stored subdomains for a target."""
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(Subdomain).where(Subdomain.target == target)
            )
            return len(result.scalars().all())

    async def get_targets_summary(self) -> list[dict]:
        """
        Retrieve a list of all targets, their total subdomain counts,
        and the latest last_seen date.
        """
        self._ensure_initialized()
        from sqlalchemy import func

        async with self._session() as session:
            result = await session.execute(
                select(
                    Subdomain.target,
                    func.count(Subdomain.id).label("count"),
                    func.max(Subdomain.last_seen).label("last_updated"),
                ).group_by(Subdomain.target)
            )
            return [
                {
                    "target": row[0],
                    "count": row[1],
                    "last_updated": row[2],
                }
                for row in result.all()
            ]

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        await self.engine.dispose()
        logger.debug("[Storage] Engine disposed.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session(self) -> AsyncSession:
        """Return a new async session from the factory."""
        return self._session_factory()

    def _ensure_initialized(self) -> None:
        """Guard against calling storage methods before init()."""
        if not self._initialized:
            raise RuntimeError(
                "StorageManager not initialized. Call `await storage.init()` first."
            )

    async def _upsert_batch(
        self,
        session: AsyncSession,
        target: str,
        subdomains: list[str],
        plugin_name: str,
    ) -> int:
        """
        Upsert a batch of subdomains for a given plugin.
        Insert new ones, update last_seen on existing ones.

        Returns:
            Number of newly inserted subdomains.
        """
        new_count = 0
        now = datetime.now(tz=timezone.utc)

        for subdomain in subdomains:
            existing = await self._get_existing(session, target, subdomain)

            if existing:
                existing.last_seen = now
                session.add(existing)
            else:
                session.add(Subdomain(
                    target=target,
                    subdomain=subdomain,
                    source_plugin=plugin_name,
                    first_seen=now,
                    last_seen=now,
                ))
                new_count += 1

        return new_count

    @staticmethod
    async def _get_existing(
        session: AsyncSession,
        target: str,
        subdomain: str,
    ) -> Subdomain | None:
        """Look up an existing Subdomain record by target + subdomain."""
        result = await session.execute(
            select(Subdomain).where(
                Subdomain.target == target,
                Subdomain.subdomain == subdomain,
            )
        )
        return result.scalars().first()