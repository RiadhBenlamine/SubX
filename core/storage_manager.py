import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.db_models import Subdomain
from core.models import ProcessedResult

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///subx.db"


class StorageManager:
    """
    Async SQLite storage layer for SubX subdomain recon results.

    Lifecycle:
        storage = StorageManager()
        await storage.init()                               # create tables once
        new_count = await storage.save(processed, target) # upsert results
        await storage.close()                             # dispose engine

    All public methods raise RuntimeError if called before init().
    """

    def __init__(self, db_url: str = DATABASE_URL) -> None:
        self.engine: AsyncEngine = create_async_engine(db_url, echo=False, future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock   = asyncio.Lock()
        self._initialized = False

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

    async def init(self) -> None:
        """Create all tables if they don't exist. Safe to call on every run."""
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

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        await self.engine.dispose()
        logger.debug("[Storage] Engine disposed.")

    # ──────────────────────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────────────────────

    async def save(self, result: ProcessedResult, target: str) -> int:
        """
        Upsert all subdomains from a ProcessedResult.
            - New subdomains   → insert with first_seen = now
            - Known subdomains → update last_seen = now

        Returns:
            Number of newly inserted subdomains.
        """
        self._ensure_initialized()

        new_count = 0
        async with self._session() as session:
            async with session.begin():
                for plugin_name, subdomains in result.by_plugin.items():
                    new_count += await self._upsert_batch(
                        session, target, subdomains, plugin_name
                    )

        logger.debug("[Storage] Saved %d new subdomains for %s.", new_count, target)
        return new_count

    async def delete(self, target: str) -> int:
        """
        Delete all subdomain records for a target.

        Returns:
            Number of records deleted.
        """
        self._ensure_initialized()

        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    delete(Subdomain).where(Subdomain.target == target)
                )

        count = result.rowcount
        logger.debug("[Storage] Deleted %d records for %s.", count, target)
        return count

    # ──────────────────────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────────────────────

    async def get_all(self, target: str) -> list[Subdomain]:
        """All subdomains for a target, sorted alphabetically."""
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(Subdomain.target == target)
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_by_plugin(self, target: str, plugin_name: str) -> list[Subdomain]:
        """Subdomains discovered by a specific plugin for a target."""
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
        """Subdomains first seen after a given datetime, newest first."""
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
        """Total number of stored subdomains for a target."""
        self._ensure_initialized()

        async with self._session() as session:
            result = await session.execute(
                select(func.count()).where(Subdomain.target == target)
            )
            return result.scalar_one()

    async def get_targets_summary(self) -> list[dict]:
        """
        All tracked targets with subdomain count and last updated time.

        Returns:
            [{"target": str, "count": int, "last_updated": datetime | None}]
        """
        self._ensure_initialized()

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
                    "target":       row[0],
                    "count":        row[1],
                    "last_updated": (
                        datetime.fromisoformat(row[2])
                        if isinstance(row[2], str) else row[2]
                    ),
                }
                for row in result.all()
            ]

    async def raw_query(self, query: str) -> list[dict]:
        """
        Execute a raw SELECT query and return rows as dicts.

        Only SELECT statements are accepted — raises ValueError otherwise.
        Column names are taken from the result cursor description.

        Args:
            query: Raw SQL SELECT string.

        Returns:
            List of row dicts keyed by column name.

        Raises:
            ValueError: if the query is not a SELECT statement.
            SQLAlchemyError: on execution failure.
        """
        self._ensure_initialized()

        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("raw_query() only accepts SELECT statements.")

        async with self._session() as session:
            result = await session.execute(text(query))
            keys = list(result.keys())
            return [dict(zip(keys, row)) for row in result.fetchall()]

    async def export(self, target: str, output_path: str) -> int:
        """
        Export all subdomains for a target to a plain-text file (one per line).
        Parent directories are created automatically.

        Args:
            target:      Domain whose subdomains are exported.
            output_path: Destination file path.

        Returns:
            Number of subdomains written.
        """
        rows = await self.get_all(target)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(row.subdomain for row in rows) + "\n")

        logger.debug(
            "[Storage] Exported %d subdomains for %s → %s.",
            len(rows), target, output_path,
        )
        return len(rows)


    def _session(self) -> AsyncSession:
        return self._session_factory()

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "StorageManager not initialized — call `await storage.init()` first."
            )

    async def _upsert_batch(
        self,
        session:     AsyncSession,
        target:      str,
        subdomains:  list[str],
        plugin_name: str,
    ) -> int:
        """
        Upsert a batch of subdomains in exactly two queries:
            1. SELECT all existing (target, subdomain) matches
            2. INSERT new rows / UPDATE last_seen on existing rows

        Returns:
            Number of newly inserted subdomains.
        """
        if not subdomains:
            return 0

        now = datetime.now(tz=timezone.utc)

        result = await session.execute(
            select(Subdomain).where(
                Subdomain.target == target,
                Subdomain.subdomain.in_(subdomains),
            )
        )
        existing: dict[str, Subdomain] = {
            row.subdomain: row for row in result.scalars().all()
        }

        new_count = 0
        for subdomain in subdomains:
            if subdomain in existing:
                existing[subdomain].last_seen = now
                session.add(existing[subdomain])
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