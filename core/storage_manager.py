import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, inspect, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.db_models import Subdomain
from core.models import ProcessedResult

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///subx.db"


class StorageManager:
    def __init__(self, db_url: str = DATABASE_URL) -> None:
        self.engine: AsyncEngine = create_async_engine(db_url, echo=False, future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def init(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            try:
                async with self.engine.begin() as conn:
                    await conn.run_sync(SQLModel.metadata.create_all)
                self._initialized = True
            except SQLAlchemyError as e:
                logger.error("Failed to initialize database: %s", e)
                raise

    async def close(self) -> None:
        await self.engine.dispose()

    async def update_httpx_results(
        self, target: str, results: list[dict]
    ) -> int:
        """Persist httpx liveness-probe results onto existing Subdomain rows.

        :param target: the scope these results belong to
        :param results: list of dicts, each with at least "subdomain" plus
            any of "alive", "status_code", "title"
        :return: number of rows updated
        """
        self._ensure_initialized()
        if not results:
            return 0

        updated = 0
        chunk_size = 450
        async with self._session() as session:
            async with session.begin():
                for i in range(0, len(results), chunk_size):
                    batch = results[i : i + chunk_size]
                    for row in batch:
                        sub = row.get("subdomain")
                        if not sub:
                            continue
                        values = {
                            k: row[k]
                            for k in ("alive", "status_code", "title")
                            if k in row
                        }
                        if not values:
                            continue
                        result = await session.execute(
                            update(Subdomain)
                            .where(
                                Subdomain.target == target,
                                Subdomain.subdomain == sub,
                            )
                            .values(**values)
                        )
                        updated += result.rowcount
        return updated

    async def update_results(
        self, target: str, results: list[dict]
    ) -> int:
        """Persist any tool's normalized output onto existing Subdomain rows.

        Generic counterpart to update_httpx_results: instead of a hardcoded
        column allowlist, this writes whatever keys in each dict match a
        real, writable column on the Subdomain model. That means naabu,
        nuclei, or any future Tool can add their own columns and this method
        handles them with zero changes — it just needs the column to exist
        on the model (add it via a migration, then it's writable here).

        Identity/audit columns (id, target, subdomain, first_seen, last_seen)
        and source_plugin (owned by the original discovery, not by liveness/
        port/vuln probes) are never written from a tool's result dict, even
        if a key with that name is present — last_seen is always bumped to
        "now" instead.

        :param target: the scope these results belong to
        :param results: list of dicts, each with at least "subdomain" plus
            any other fields matching writable Subdomain columns
        :return: number of rows updated
        """
        self._ensure_initialized()
        if not results:
            return 0

        protected = {
            "id", "target", "subdomain", "source_plugin",
            "first_seen", "last_seen",
        }
        writable_columns = {
            col.name for col in Subdomain.__table__.columns
        } - protected

        updated = 0
        chunk_size = 450
        now = datetime.now(tz=timezone.utc)

        async with self._session() as session:
            async with session.begin():
                for i in range(0, len(results), chunk_size):
                    batch = results[i : i + chunk_size]
                    for row in batch:
                        sub = row.get("subdomain")
                        if not sub:
                            continue
                        values = {
                            k: v for k, v in row.items() if k in writable_columns
                        }
                        if not values:
                            continue
                        values["last_seen"] = now
                        result = await session.execute(
                            update(Subdomain)
                            .where(
                                Subdomain.target == target,
                                Subdomain.subdomain == sub,
                            )
                            .values(**values)
                        )
                        updated += result.rowcount
        return updated

    async def migrate(self, backup: bool = True) -> list[str]:
        """Compare the model schema against the live DB and add missing columns.

        Only additive changes (new nullable columns) are applied — nothing is
        dropped or altered, so this is always safe to run.

        Returns a list of column names that were added.
        """
        self._ensure_initialized()

        db_path = self._resolve_db_path()
        if db_path and backup and db_path.exists():
            backup_path = db_path.with_suffix(
                f".backup-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
            )
            shutil.copy2(db_path, backup_path)
            logger.info("Backup created: %s", backup_path)

        added: list[str] = []

        async with self.engine.connect() as conn:
            existing_cols: set[str] = await conn.run_sync(
                lambda sync_conn: {
                    col["name"]
                    for col in inspect(sync_conn).get_columns("subdomain")
                }
            )

            model_table = SQLModel.metadata.tables["subdomain"]

            for col in model_table.columns:
                if col.name in existing_cols:
                    continue

                col_type = col.type.compile(dialect=self.engine.dialect)
                statement = f'ALTER TABLE subdomain ADD COLUMN "{col.name}" {col_type}'
                await conn.execute(text(statement))
                added.append(col.name)
                logger.info("Added column: %s (%s)", col.name, col_type)

            await conn.commit()

        return added

    def _resolve_db_path(self) -> Path | None:
        """Extract the filesystem path from the database URL (SQLite only)."""
        url_str = str(self.engine.url)
        # sqlite+aiosqlite:///subx.db  →  subx.db
        # sqlite+aiosqlite:////abs/path/to/subx.db  →  /abs/path/to/subx.db
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url_str.startswith(prefix):
                raw = url_str[len(prefix):]
                return Path(raw) if raw else None
        return None

    async def save(self, result: ProcessedResult, target: str) -> int:
        self._ensure_initialized()
        new_count = 0
        async with self._session() as session:
            async with session.begin():
                for plugin_name, subdomains in result.by_plugin.items():
                    new_count += await self._upsert_batch(
                        session, target, subdomains, plugin_name
                    )
        return new_count

    async def delete(self, target: str) -> int:
        self._ensure_initialized()
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    delete(Subdomain).where(Subdomain.target == target)
                )
        return result.rowcount

    async def get_all(self, target: str) -> list[Subdomain]:
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(Subdomain.target == target)
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_by_plugin(self, target: str, plugin_name: str) -> list[Subdomain]:
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
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(func.count()).where(Subdomain.target == target)
            )
            return result.scalar_one()

    async def get_targets_summary(self) -> list[dict]:
        self._ensure_initialized()
        _fromisoformat = datetime.fromisoformat
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
                    "last_updated": (
                        _fromisoformat(row[2])
                        if isinstance(row[2], str) else row[2]
                    ),
                }
                for row in result.all()
            ]

    async def raw_query(self, query: str) -> list[dict]:
        self._ensure_initialized()
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("raw_query() only accepts SELECT statements.")

        async with self._session() as session:
            result = await session.execute(text(query))
            return [dict(row) for row in result.mappings().all()]

    async def export(self, target: str, output_path: str) -> int:
        rows = await self.get_all(target)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(row.subdomain for row in rows) + "\n")
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
        session: AsyncSession,
        target: str,
        subdomains: list[str],
        plugin_name: str,
    ) -> int:
        if not subdomains:
            return 0

        now = datetime.now(tz=timezone.utc)
        chunk_size = 450

        existing: dict[str, Subdomain] = {}
        for i in range(0, len(subdomains), chunk_size):
            batch = subdomains[i : i + chunk_size]
            result = await session.execute(
                select(Subdomain).where(
                    Subdomain.target == target,
                    Subdomain.subdomain.in_(batch),
                )
            )
            existing.update({row.subdomain: row for row in result.scalars().all()})

        # Bulk update existing rows
        existing_names = set(existing)
        to_update = [s for s in subdomains if s in existing_names]
        if to_update:
            for i in range(0, len(to_update), chunk_size):
                batch = to_update[i : i + chunk_size]
                await session.execute(
                    update(Subdomain)
                    .where(
                        Subdomain.target == target,
                        Subdomain.subdomain.in_(batch),
                    )
                    .values(last_seen=now)
                )

        # Batch insert new rows
        new_rows = [
            Subdomain(
                target=target,
                subdomain=sub,
                source_plugin=plugin_name,
                first_seen=now,
                last_seen=now,
            )
            for sub in subdomains
            if sub not in existing_names
        ]
        if new_rows:
            session.add_all(new_rows)

        return len(new_rows)