"""PostgreSQL storage manager for executing database operations, upserts, queries, and migrations."""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlmodel import SQLModel, select

from core.db_models import Subdomain, SubdomainSource
from core.models import ProcessedResult

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres@127.0.0.1:5432/subx"

# PostgreSQL parameter limit per query is 32,767 ($32767).
# 5000 rows × ~6 columns = ~30,000 parameters, staying comfortably under the limit
# while keeping chunk payload size efficient for high-throughput batch operations.
PG_CHUNK_SIZE = 5000


def _load_pg_url_from_config_files() -> str | None:
    """Attempt to load PostgreSQL configuration from global ~/.config/subx/config.yaml or local config.yaml."""
    candidates = [
        Path.home() / ".config" / "subx" / "config.yaml",
        Path("config.yaml"),
        Path("config.yml"),
    ]
    for c in candidates:
        if not c.exists():
            continue
        try:
            import yaml
            with c.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            db_cfg = data.get("db", {})
            if isinstance(db_cfg, dict) and db_cfg.get("host"):
                host = db_cfg["host"]
                user = db_cfg.get("user") or db_cfg.get("username") or "postgres"
                password = db_cfg.get("password") or db_cfg.get("pass") or ""
                port = db_cfg.get("port") or 5432
                dbname = db_cfg.get("dbname") or db_cfg.get("database") or "subx"
                auth = f"{user}:{password}@" if password else f"{user}@"
                return f"postgresql+asyncpg://{auth}{host}:{port}/{dbname}"
        except Exception:
            continue
    return None


def normalize_db_url(db_url: str | None = None) -> str:
    """Resolve and normalize database URL for PostgreSQL engine."""
    if db_url:
        url = db_url
    elif os.environ.get("DATABASE_URL"):
        url = os.environ["DATABASE_URL"]
    elif os.environ.get("SUBX_DB_URL"):
        url = os.environ["SUBX_DB_URL"]
    elif os.environ.get("SUBX_DB_HOST") or os.environ.get("PGHOST"):
        host = os.environ.get("SUBX_DB_HOST") or os.environ.get("PGHOST")
        user = os.environ.get("SUBX_DB_USER") or os.environ.get("PGUSER") or "postgres"
        password = os.environ.get("SUBX_DB_PASS") or os.environ.get("SUBX_DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
        port = os.environ.get("SUBX_DB_PORT") or os.environ.get("PGPORT") or "5432"
        dbname = os.environ.get("SUBX_DB_NAME") or os.environ.get("PGDATABASE") or "subx"
        auth = f"{user}:{password}@" if password else f"{user}@"
        url = f"postgresql+asyncpg://{auth}{host}:{port}/{dbname}"
    else:
        pg_from_config = _load_pg_url_from_config_files()
        if pg_from_config:
            url = pg_from_config
        else:
            url = DEFAULT_DATABASE_URL

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class StorageManager:
    """Manages PostgreSQL connection pooling, transactions, dynamic migrations, and schema definition."""

    def __init__(self, db_url: str | None = None) -> None:
        self.db_url = normalize_db_url(db_url)
        self.engine: AsyncEngine = create_async_engine(self.db_url, echo=False, future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def init(self) -> None:
        """Initialize connection engine, create database 'subx' on PostgreSQL if missing, and create schema tables."""
        async with self._init_lock:
            if self._initialized:
                return

            try:
                await self._ensure_pg_database_exists()
                async with self.engine.begin() as conn:
                    await conn.run_sync(SQLModel.metadata.create_all)
                self._initialized = True
            except Exception as e:
                logger.error("PostgreSQL database connection failed: %s", e)
                raise RuntimeError(
                    f"PostgreSQL connection error: {e}. "
                    "Please verify PostgreSQL is running and credentials in config.yaml / environment variables are correct."
                ) from e

    async def _ensure_pg_database_exists(self) -> None:
        """Ensure PostgreSQL database 'subx' exists on the target server before table creation."""
        url_obj = self.engine.url
        dbname = url_obj.database or "subx"
        if not dbname or dbname in ("postgres", "template1"):
            return

        admin_url = url_obj.set(database="postgres")
        admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with admin_engine.connect() as conn:
                res = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": dbname},
                )
                if not res.scalar():
                    logger.info("First run — creating PostgreSQL database '%s'...", dbname)
                    await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
                    logger.info("Successfully created database '%s'.", dbname)
        except Exception as e:
            logger.debug("Automatic PG database check/creation skipped: %s", e)
        finally:
            await admin_engine.dispose()

    async def update_results(
        self, target: str, results: list[dict]
    ) -> int:
        """Persist any tool's normalized output onto existing Subdomain rows in PostgreSQL.

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
            "first_seen", "last_seen", "last_seen_alive",
        }
        writable_columns = {
            col.name for col in Subdomain.__table__.columns
        } - protected

        updated = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self._session() as session, session.begin():
            for i in range(0, len(results), PG_CHUNK_SIZE):
                batch = results[i : i + PG_CHUNK_SIZE]
                seen_in_batch: set[str] = set()
                batch_values = []
                for row in batch:
                    sub = row.get("subdomain")
                    if not sub:
                        continue
                    sub_clean = sub.strip()
                    if sub_clean in seen_in_batch:
                        continue
                    seen_in_batch.add(sub_clean)
                    values = {
                        k: v for k, v in row.items() if k in writable_columns and v is not None
                    }
                    values["target"] = target
                    values["subdomain"] = sub_clean
                    values["source_plugin"] = "Tool"
                    values["first_seen"] = now
                    values["last_seen"] = now
                    if row.get("alive") is True:
                        values["last_seen_alive"] = now
                    batch_values.append(values)

                if not batch_values:
                    continue

                all_keys = set()
                for v in batch_values:
                    all_keys.update(v.keys())

                for v in batch_values:
                    for k in all_keys:
                        if k not in v:
                            v[k] = None

                all_keys.discard("target")
                all_keys.discard("subdomain")
                all_keys.discard("first_seen")
                all_keys.discard("source_plugin")

                stmt = pg_insert(Subdomain).values(batch_values)
                update_cols = {k: getattr(stmt.excluded, k) for k in all_keys}
                stmt = stmt.on_conflict_do_update(
                    index_elements=["target", "subdomain"],
                    set_=update_cols,
                )
                await session.execute(stmt)
                updated += len(batch_values)
        return updated

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    async def migrate(self, backup: bool = True) -> list[str]:
        """Compare the PostgreSQL model schema against the live DB and add missing columns,
        and ensure unique constraints and join tables are properly migrated.
        """
        self._ensure_initialized()

        if backup:
            logger.warning(
                "Automatic database backup is skipped on PostgreSQL. "
                "Please perform backups externally using `pg_dump` or your PostgreSQL backup procedures."
            )

        table_name = "subx_subdomain"

        # 1. Create any missing tables (like subx_subdomain_sources)
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        added: list[str] = []

        # 2. Add any new columns to subx_subdomain first
        async with self.engine.connect() as conn:
            existing_cols = await conn.run_sync(
                lambda sync_conn: {
                    col["name"]
                    for col in inspect(sync_conn).get_columns(table_name)
                }
            )

            model_table = SQLModel.metadata.tables[table_name]
            for col in model_table.columns:
                if col.name in existing_cols:
                    continue

                col_type = col.type.compile(dialect=self.engine.dialect)
                statement = f'ALTER TABLE {table_name} ADD COLUMN "{col.name}" {col_type}'
                await conn.execute(text(statement))
                added.append(col.name)
                logger.info("Added column: %s (%s)", col.name, col_type)

            await conn.commit()

        # 3. Check for the unique constraint on (target, subdomain)
        has_unique_constraint = False
        async with self.engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_indexes(table_name)
            )
            for idx in indexes:
                is_target_subdomain = set(idx.get("column_names", [])) == {"target", "subdomain"}
                if idx.get("unique") and is_target_subdomain:
                    has_unique_constraint = True
                    break

            if not has_unique_constraint:
                unique_cons = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_unique_constraints(table_name)
                )
                for uc in unique_cons:
                    if set(uc.get("column_names", [])) == {"target", "subdomain"}:
                        has_unique_constraint = True
                        break

        # 4. If missing unique constraint, add PostgreSQL-native UNIQUE constraint
        if not has_unique_constraint:
            logger.info(
                "Adding PostgreSQL unique constraint uq_target_subdomain on %s(target, subdomain)...",
                table_name,
            )
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "ADD CONSTRAINT uq_target_subdomain UNIQUE (target, subdomain);"
                    )
                )
            logger.info("Added uq_target_subdomain constraint to %s successfully.", table_name)
            added.append("uq_target_subdomain_constraint")

        return added

    async def save(
        self,
        result: ProcessedResult,
        target: str,
        auto_pipeline: bool = True,
        progress_cb=None,
        total_plugins: int = 0,
    ) -> int:
        """Save a ProcessedResult of subdomain scan results into PostgreSQL."""
        self._ensure_initialized()
        new_count = 0
        total_to_save = result.total
        total_saved = 0
        async with self._session() as session, session.begin():
            for plugin_name, subdomains in result.by_plugin.items():
                if not subdomains:
                    continue
                added, saved = await self._upsert_batch(
                    session,
                    target,
                    subdomains,
                    plugin_name,
                    progress_cb=progress_cb,
                    total_saved=total_saved,
                    total_to_save=total_to_save,
                    total_plugins=total_plugins,
                )
                new_count += added
                total_saved += saved

        if auto_pipeline:
            await self._run_auto_pipeline(
                target, progress_cb=progress_cb, total_plugins=total_plugins
            )
        return new_count

    async def _run_auto_pipeline(
        self, target: str, progress_cb=None, total_plugins: int = 0
    ) -> None:
        """Automatically run tool pipeline (subdomains -> dnsx -> httpx) if configured in config.yaml."""
        try:
            from core.config_manager import ConfigManager
            dnsx_cfg = ConfigManager.load_tool_config("dnsx")
            httpx_cfg = ConfigManager.load_tool_config("httpx")

            if dnsx_cfg is None and httpx_cfg is None:
                return

            resolved_hosts: list[str] | None = None

            # ── Step 1: Resolve subdomains via dnsx ─────────────────
            if dnsx_cfg is not None:
                from tools.dnsx import DnsxTool
                from core.tool_manager import ToolManager
                logger.info("Pipeline Step 1: Resolving subdomains for %s with dnsx...", target)
                if progress_cb:
                    progress_cb(
                        total_plugins,
                        total_plugins,
                        f"Resolving subdomains for {target} via dnsx...",
                    )
                tool_mgr = ToolManager()
                dns_results = await tool_mgr.run_tool(DnsxTool(), target, tool_config=dnsx_cfg)
                if dns_results:
                    resolved_hosts = [r["subdomain"] for r in dns_results if r.get("ip")]
                    logger.info("dnsx resolved %d active subdomains for %s", len(resolved_hosts), target)

            # ── Step 2: Probe resolved subdomains via httpx ─────────
            if httpx_cfg is not None:
                from core.services.probe_service import ProbeService
                probe_service = ProbeService(storage=self)
                count_str = f" ({len(resolved_hosts):,} resolved)" if resolved_hosts is not None else ""
                if progress_cb:
                    progress_cb(
                        total_plugins,
                        total_plugins,
                        f"Probing subdomains for {target} via httpx{count_str}...",
                    )
                if resolved_hosts is not None:
                    logger.info("Pipeline Step 2: Probing %d resolved subdomains with httpx...", len(resolved_hosts))
                    await probe_service.probe_domain(target, tool_config=httpx_cfg, hosts=resolved_hosts)
                else:
                    logger.info("Pipeline: Probing subdomains for %s with httpx...", target)
                    await probe_service.probe_domain(target, tool_config=httpx_cfg)

        except Exception as e:
            logger.warning("Auto-pipeline execution failed for %s: %s", target, e)

    async def delete(self, target: str) -> int:
        """Delete all database records associated with the target domain."""
        self._ensure_initialized()
        async with self._session() as session, session.begin():
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
                    Subdomain.tech.ilike(pattern),  # pylint: disable=no-member
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
                    Subdomain.alive == True,
                )
                .options(selectinload(Subdomain.sources))
                .order_by(Subdomain.subdomain)
            )
            return list(result.scalars().all())

    async def get_dead(self, target: str) -> list[Subdomain]:
        """Fetch subdomains for the target domain that are verified dead (down)."""
        self._ensure_initialized()
        async with self._session() as session:
            result = await session.execute(
                select(Subdomain)
                .where(
                    Subdomain.target == target,
                    Subdomain.alive == False,
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
        """Execute a raw SQL SELECT query against PostgreSQL in a READ ONLY transaction context."""
        self._ensure_initialized()

        async with self.engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
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
            self._initialized = False

    # pylint: disable=too-many-locals
    async def _upsert_batch(
        self,
        session: AsyncSession,
        target: str,
        subdomains: list[str],
        plugin_name: str,
        progress_cb=None,
        total_saved: int = 0,
        total_to_save: int = 0,
        total_plugins: int = 0,
    ) -> tuple[int, int]:
        """Perform a high-performance PostgreSQL batch upsert and populate subdomain source linkages."""
        if not subdomains:
            return 0, 0

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_count = 0
        saved_count = 0
        subdomain_ids: dict[str, int] = {}

        # 1. Batch upsert subdomains into subx_subdomain in a single round trip per chunk.
        # Uses PostgreSQL .returning() with (xmax = 0) AS is_new:
        # Postgres sets xmax = 0 for freshly inserted rows, and xmax != 0 for updated rows.
        # This yields the primary key ID and computes new_count without requiring separate SELECT queries.
        for i in range(0, len(subdomains), PG_CHUNK_SIZE):
            batch = subdomains[i : i + PG_CHUNK_SIZE]
            seen_in_batch: set[str] = set()
            batch_values = []
            for sub in batch:
                if not sub:
                    continue
                sub_clean = sub.strip()
                if sub_clean in seen_in_batch:
                    continue
                seen_in_batch.add(sub_clean)
                batch_values.append({
                    "target": target,
                    "subdomain": sub_clean,
                    "source_plugin": plugin_name,
                    "first_seen": now,
                    "last_seen": now,
                })
            if not batch_values:
                continue

            if progress_cb and total_to_save:
                current_saved = min(total_saved + saved_count + len(batch_values), total_to_save)
                progress_cb(
                    total_plugins,
                    total_plugins,
                    f"Saving subdomains to database [{current_saved:,}/{total_to_save:,}] ({plugin_name})...",
                )

            stmt = (
                pg_insert(Subdomain)
                .values(batch_values)
                .on_conflict_do_update(
                    index_elements=["target", "subdomain"],
                    set_={"last_seen": now},
                )
                .returning(Subdomain.id, Subdomain.subdomain, text("(xmax = 0) AS is_new"))
            )
            res = await session.execute(stmt)
            for row in res.all():
                sub_id, name, is_new = row[0], row[1], row[2]
                subdomain_ids[name] = sub_id
                if is_new:
                    new_count += 1
            saved_count += len(batch_values)

        # 2. Batch insert discovery sources into subx_subdomain_sources in a single round trip per chunk
        source_values = [
            {"subdomain_id": sub_id, "source_plugin": plugin_name}
            for name, sub_id in subdomain_ids.items()
            if sub_id
        ]

        if source_values:
            for i in range(0, len(source_values), PG_CHUNK_SIZE):
                batch_src = source_values[i : i + PG_CHUNK_SIZE]
                stmt_source = (
                    pg_insert(SubdomainSource)
                    .values(batch_src)
                    .on_conflict_do_nothing(
                        index_elements=["subdomain_id", "source_plugin"]
                    )
                )
                await session.execute(stmt_source)

        return new_count, saved_count
