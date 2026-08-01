"""Storage manager for executing database operations, upserts, queries, and migrations."""
import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, inspect, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    create_async_engine)
from sqlalchemy.orm import selectinload, sessionmaker
from sqlmodel import SQLModel, select

from core.db_models import Subdomain, SubdomainSource
from core.models import ProcessedResult

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite+aiosqlite:///subx.db"


class StorageManager:
    """Manages raw connection pooling, transactions, dynamic migrations, and schema definition."""

    def __init__(self, db_url: str = DATABASE_URL) -> None:
        self.db_url = db_url
        self.engine: AsyncEngine = create_async_engine(db_url, echo=False, future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._ro_engine = None

    async def init(self) -> None:
        """Initialize connection engines and create schema tables if missing."""
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

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    async def migrate(self, backup: bool = True) -> list[str]:
        """Compare the model schema against the live DB and add missing columns,
        and ensure unique constraints and join tables are properly migrated.
        """
        self._ensure_initialized()

        db_path = self._resolve_db_path()
        if db_path and backup and db_path.exists():
            backup_path = db_path.with_suffix(
                f".backup-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
            )
            shutil.copy2(db_path, backup_path)
            logger.info("Backup created: %s", backup_path)

        # 1. Create any missing tables (like subdomain_sources)
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        added: list[str] = []

        # 2. Add any new columns to subdomain first
        async with self.engine.connect() as conn:
            existing_cols = await conn.run_sync(
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

        # 3. Check for the unique constraint on (target, subdomain)
        has_unique_constraint = False
        async with self.engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_indexes("subdomain")
            )
            for idx in indexes:
                is_target_subdomain = set(idx.get("column_names", [])) == {"target", "subdomain"}
                if idx.get("unique") and is_target_subdomain:
                    has_unique_constraint = True
                    break

            if not has_unique_constraint:
                unique_cons = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_unique_constraints("subdomain")
                )
                for uc in unique_cons:
                    if set(uc.get("column_names", [])) == {"target", "subdomain"}:
                        has_unique_constraint = True
                        break

        # 4. If missing unique constraint, recreate table and migrate data
        if not has_unique_constraint:
            logger.info(
                "Migrating subdomain table to add unique constraint on (target, subdomain)"
            )
            async with self.engine.connect() as conn:
                existing_cols_list = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("subdomain")
                )

            col_defs = []
            for col in existing_cols_list:
                col_name = col["name"]
                col_type = str(col["type"])
                nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                if col_name == "id":
                    col_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
                else:
                    col_defs.append(f'"{col_name}" {col_type} {nullable}')
            col_defs.append("UNIQUE(target, subdomain)")

            ddl_create = f"CREATE TABLE subdomain_new ({', '.join(col_defs)});"

            select_fields = []
            for col in existing_cols_list:
                col_name = col["name"]
                if col_name == "id":
                    continue
                if col_name == "first_seen":
                    select_fields.append("MIN(first_seen) as first_seen")
                elif col_name == "last_seen":
                    select_fields.append("MAX(last_seen) as last_seen")
                else:
                    select_fields.append(f'"{col_name}"')

            col_names_str = ", ".join(
                f'"{col["name"]}"' for col in existing_cols_list if col["name"] != "id"
            )
            select_fields_str = ", ".join(select_fields)

            dedup_insert = f"""
            INSERT INTO subdomain_new ({col_names_str})
            SELECT {select_fields_str}
            FROM subdomain
            GROUP BY target, subdomain;
            """  # nosec B608

            sources_insert = """
            INSERT OR IGNORE INTO subdomain_sources (subdomain_id, source_plugin)
            SELECT n.id, o.source_plugin
            FROM subdomain_new n
            JOIN subdomain o ON n.target = o.target AND n.subdomain = o.subdomain;
            """

            async with self.engine.begin() as conn:
                await conn.execute(text(ddl_create))
                await conn.execute(text(dedup_insert))
                await conn.execute(text(sources_insert))
                await conn.execute(text("DROP TABLE subdomain;"))
                await conn.execute(text("ALTER TABLE subdomain_new RENAME TO subdomain;"))
                await conn.execute(
                    text("CREATE INDEX ix_subdomain_target ON subdomain (target);")
                )
                await conn.execute(
                    text("CREATE INDEX ix_subdomain_subdomain ON subdomain (subdomain);")
                )

            logger.info("Migrated subdomain table successfully.")
            added.append("uq_target_subdomain_constraint")

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
        """Save a ProcessedResult of subdomain scan results into the database."""
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
        """Delete all database records associated with the target domain."""
        self._ensure_initialized()
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    delete(Subdomain).where(Subdomain.target == target)
                )
        return result.rowcount

    async def get_all(self, target: str) -> list[Subdomain]:
        """Fetch all stored subdomains for the target domain, including sources."""
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(Subdomain.target == target)
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_by_plugin(self, target: str, plugin_name: str) -> list[Subdomain]:
        """Fetch stored subdomains for the target domain discovered by a specific plugin."""
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .join(SubdomainSource)
                .where(
                    Subdomain.target == target,
                    SubdomainSource.source_plugin == plugin_name,
                )
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_by_tech(self, target: str, tech_name: str) -> list[Subdomain]:
        """Fetch subdomains where the tech JSON column contains the given technology."""
        self._ensure_initialized()
        pattern = f"%{tech_name}%"
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.tech.ilike(pattern),
                )
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_alive(self, target: str) -> list[Subdomain]:
        """Fetch subdomains for the target domain that are verified alive."""
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.alive == True,  # noqa: E712
                )
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_new_since(self, target: str, since: datetime) -> list[Subdomain]:
        """Fetch stored subdomains for the target domain first seen on or after a given time."""
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                # pylint: disable=no-member
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.first_seen >= since,
                )
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.first_seen.desc())
            )
            return list(result.scalars().all())

    async def count(self, target: str) -> int:
        """Count the number of subdomains stored for the target domain."""
        self._ensure_initialized()
        async with self._session() as session:
            # pylint: disable=not-callable
            result = await session.execute(
                select(func.count()).where(Subdomain.target == target)
            )
            return result.scalar_one()

    async def get_targets_summary(self) -> list[dict]:
        """Return a target-level summary list of database contents."""
        self._ensure_initialized()
        _fromisoformat = datetime.fromisoformat
        async with self._session() as session:
            # pylint: disable=not-callable
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
        """Execute a raw SQL query against a read-only instance of the database."""
        self._ensure_initialized()

        if self._ro_engine is None:
            db_path = self._resolve_db_path()
            if db_path:
                ro_url = (
                    f"sqlite+aiosqlite:///file:{db_path.absolute().as_posix()}"
                    "?mode=ro&uri=true"
                )
            else:
                ro_url = self.db_url

            self._ro_engine = create_async_engine(ro_url)

        async with self._ro_engine.connect() as conn:
            result = await conn.execute(text(query))
            if result.returns_rows:
                return [dict(row) for row in result.mappings().all()]
            return []

    def _session(self) -> AsyncSession:
        """Generate a new database transaction session."""
        return self._session_factory()

    def _ensure_initialized(self) -> None:
        """Ensure storage engines are fully initialized before usage."""
        if not self._initialized:
            raise RuntimeError(
                "StorageManager not initialized — call `await storage.init()` first."
            )

    async def close(self) -> None:
        """Close database engines and release all connection resources."""
        if self._initialized:
            await self.engine.dispose()
            if self._ro_engine is not None:
                await self._ro_engine.dispose()
            self._initialized = False

    # pylint: disable=too-many-locals
    async def _upsert_batch(
        self,
        session: AsyncSession,
        target: str,
        subdomains: list[str],
        plugin_name: str,
    ) -> int:
        """Perform a batch sqlite upsert and populate subdomain source linkages."""
        if not subdomains:
            return 0

        now = datetime.now(tz=timezone.utc)
        chunk_size = 450

        # Query existing subdomains in this batch to determine new_count
        existing_subdomains = set()
        for i in range(0, len(subdomains), chunk_size):
            batch = subdomains[i : i + chunk_size]
            # pylint: disable=no-member
            result = await session.execute(
                select(Subdomain.subdomain).where(
                    Subdomain.target == target,
                    Subdomain.subdomain.in_(batch),
                )
            )
            existing_subdomains.update(result.scalars().all())

        new_count = 0
        for sub in subdomains:
            if sub not in existing_subdomains:
                new_count += 1

            stmt = (
                sqlite_insert(Subdomain)
                .values(
                    target=target,
                    subdomain=sub,
                    source_plugin=plugin_name,
                    first_seen=now,
                    last_seen=now,
                )
                .on_conflict_do_update(
                    index_elements=["target", "subdomain"],
                    set_={"last_seen": now},
                )
            )
            await session.execute(stmt)

        # Retrieve IDs to populate subdomain_sources
        subdomain_ids = {}
        for i in range(0, len(subdomains), chunk_size):
            batch = subdomains[i : i + chunk_size]
            # pylint: disable=no-member
            result = await session.execute(
                select(Subdomain.id, Subdomain.subdomain).where(
                    Subdomain.target == target,
                    Subdomain.subdomain.in_(batch),
                )
            )
            for sub_id, name in result.all():
                subdomain_ids[name] = sub_id

        # Insert sources into join table
        for name in subdomains:
            sub_id = subdomain_ids.get(name)
            if sub_id:
                stmt_source = (
                    sqlite_insert(SubdomainSource)
                    .values(
                        subdomain_id=sub_id,
                        source_plugin=plugin_name,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt_source)

        return new_count
