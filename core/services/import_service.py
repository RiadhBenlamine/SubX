"""Service layer for importing assets from a SQLite database into PostgreSQL (or active DB)."""
import logging
from pathlib import Path
from typing import NamedTuple

from sqlmodel import select

from core.db_models import Subdomain, SubdomainSource
from core.services.base import Service
from core.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class ImportSummary(NamedTuple):
    sqlite_file: str
    target_db_url: str
    targets_count: int
    subdomains_imported: int
    sources_linked: int


from datetime import datetime, timezone
from sqlalchemy import inspect, text


class ImportService(Service):
    """Imports subdomains, web probe statuses, tech tags, IPs, and sources from SQLite into PostgreSQL."""

    async def import_sqlite(
        self,
        sqlite_path: str,
        target_db_url: str | None = None,
    ) -> ImportSummary:
        """Migrate all records from an existing SQLite database file into the target database engine."""
        sqlite_file = Path(sqlite_path)
        if not sqlite_file.exists():
            raise FileNotFoundError(f"SQLite database file not found: '{sqlite_path}'")

        source_url = f"sqlite+aiosqlite:///{sqlite_file.absolute().as_posix()}"
        source_storage = StorageManager(source_url)
        await source_storage.init()

        target_storage = self._custom_storage or (
            StorageManager(target_db_url) if target_db_url else self.storage
        )
        await target_storage.init()

        # Determine table names in source SQLite DB (legacy 'subdomain' or current 'subx_subdomain')
        source_table = "subx_subdomain"
        source_join_table = "subx_subdomain_sources"
        async with source_storage.engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
            if "subdomain" in tables:
                res = await conn.execute(text("SELECT COUNT(*) FROM subdomain"))
                subdomain_count = res.scalar() or 0
                if "subx_subdomain" in tables:
                    res_subx = await conn.execute(text("SELECT COUNT(*) FROM subx_subdomain"))
                    subx_count = res_subx.scalar() or 0
                    if subdomain_count > subx_count:
                        source_table = "subdomain"
                        source_join_table = "subdomain_sources"
                elif subdomain_count > 0:
                    source_table = "subdomain"
                    source_join_table = "subdomain_sources"

        total_subdomains = 0
        total_sources = 0
        targets_count = 0

        async with source_storage._session() as session:
            # Query targets summary from resolved source_table
            result = await session.execute(
                text(f"""
                SELECT target, COUNT(id) as count
                FROM {source_table}
                GROUP BY target
                """)
            )
            targets_list = [row[0] for row in result.all() if row[0]]
            targets_count = len(targets_list)

            for domain in targets_list:
                rows = await self._fetch_source_rows(
                    session, domain, source_table, source_join_table
                )
                if not rows:
                    continue

                # Batch import rows into destination storage engine
                subdomains_imported, sources_linked = await self._import_rows_batch(
                    target_storage, domain, rows
                )
                total_subdomains += subdomains_imported
                total_sources += sources_linked

        await source_storage.close()

        return ImportSummary(
            sqlite_file=str(sqlite_file),
            target_db_url=target_storage.db_url,
            targets_count=targets_count,
            subdomains_imported=total_subdomains,
            sources_linked=total_sources,
        )

    @staticmethod
    async def _fetch_source_rows(
        session, domain: str, source_table: str, source_join_table: str
    ) -> list[dict]:
        """Fetch raw subdomain records and linked discovery sources from source SQLite DB."""
        # 1. Inspect existing columns in source_table
        res = await session.execute(text(f"PRAGMA table_info('{source_table}')"))
        cols = {row[1] for row in res.all()}

        col_selects = ["id", "target", "subdomain", "source_plugin"]
        for optional_col in ("alive", "status_code", "title", "tech", "ip", "first_seen", "last_seen", "last_seen_alive"):
            if optional_col in cols:
                col_selects.append(optional_col)
            else:
                col_selects.append(f"NULL as {optional_col}")

        stmt = f"SELECT {', '.join(col_selects)} FROM {source_table} WHERE target = :target ORDER BY subdomain"
        res_rows = await session.execute(text(stmt), {"target": domain})
        raw_rows = res_rows.mappings().all()
        if not raw_rows:
            return []

        # 2. Fetch linked sources from source_join_table if table exists
        sources_by_subid = {}
        res_tables = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"), {"name": source_join_table})
        if res_tables.scalar():
            sub_ids = [r["id"] for r in raw_rows if r.get("id")]
            if sub_ids:
                stmt_sources = f"SELECT subdomain_id, source_plugin FROM {source_join_table} WHERE subdomain_id IN ({', '.join(str(i) for i in sub_ids)})"
                res_src = await session.execute(text(stmt_sources))
                for sub_id, src in res_src.all():
                    sources_by_subid.setdefault(sub_id, []).append(src)

        rows = []
        for r in raw_rows:
            d = dict(r)
            sub_id = d.get("id")
            linked_srcs = sources_by_subid.get(sub_id, [])
            if not linked_srcs and d.get("source_plugin"):
                linked_srcs = [d["source_plugin"]]
            d["sources_list"] = linked_srcs
            rows.append(d)
        return rows

    @staticmethod
    async def _import_rows_batch(
        target_storage: StorageManager,
        target: str,
        rows: list[dict | Subdomain],
    ) -> tuple[int, int]:
        """Perform high-performance batch upsert into destination database engine."""
        if not rows:
            return 0, 0

        chunk_size = 450
        is_pg = target_storage.engine.dialect.name == "postgresql"
        if is_pg:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            insert_fn = pg_insert
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            insert_fn = sqlite_insert

        imported_count = 0
        linked_sources = 0

        def _get(row, key, default=None):
            if isinstance(row, dict):
                return row.get(key, default)
            return getattr(row, key, default)

        async with target_storage._session() as session, session.begin():
            # 1. Bulk Upsert subdomains
            for i in range(0, len(rows), chunk_size):
                batch = rows[i : i + chunk_size]
                batch_values = []
                for r in batch:
                    first_seen = _get(r, "first_seen")
                    last_seen = _get(r, "last_seen")
                    last_seen_alive = _get(r, "last_seen_alive")

                    if isinstance(first_seen, str):
                        try:
                            first_seen = datetime.fromisoformat(first_seen)
                        except ValueError:
                            first_seen = None
                    if isinstance(last_seen, str):
                        try:
                            last_seen = datetime.fromisoformat(last_seen)
                        except ValueError:
                            last_seen = None
                    if isinstance(last_seen_alive, str):
                        try:
                            last_seen_alive = datetime.fromisoformat(last_seen_alive)
                        except ValueError:
                            last_seen_alive = None

                    now = datetime.now(tz=timezone.utc)
                    first_seen = first_seen or now
                    last_seen = last_seen or now

                    batch_values.append({
                        "target": target,
                        "subdomain": _get(r, "subdomain"),
                        "source_plugin": _get(r, "source_plugin") or "Imported",
                        "alive": _get(r, "alive"),
                        "status_code": _get(r, "status_code"),
                        "title": _get(r, "title"),
                        "tech": _get(r, "tech"),
                        "ip": _get(r, "ip"),
                        "first_seen": first_seen,
                        "last_seen": last_seen,
                        "last_seen_alive": last_seen_alive,
                    })

                if not batch_values:
                    continue

                if is_pg:
                    stmt = pg_insert(Subdomain)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["target", "subdomain"],
                        set_={
                            "alive": stmt.excluded.alive,
                            "status_code": stmt.excluded.status_code,
                            "title": stmt.excluded.title,
                            "tech": stmt.excluded.tech,
                            "ip": stmt.excluded.ip,
                            "last_seen": stmt.excluded.last_seen,
                            "last_seen_alive": stmt.excluded.last_seen_alive,
                        },
                    )
                else:
                    stmt = sqlite_insert(Subdomain)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["target", "subdomain"],
                        set_={
                            "alive": stmt.excluded.alive,
                            "status_code": stmt.excluded.status_code,
                            "title": stmt.excluded.title,
                            "tech": stmt.excluded.tech,
                            "ip": stmt.excluded.ip,
                            "last_seen": stmt.excluded.last_seen,
                            "last_seen_alive": stmt.excluded.last_seen_alive,
                        },
                    )
                await session.execute(stmt, batch_values)
                imported_count += len(batch_values)

            # 2. Retrieve new IDs in destination DB for source linkage
            subdomain_names = [_get(r, "subdomain") for r in rows]
            subdomain_ids = {}
            for i in range(0, len(subdomain_names), chunk_size):
                batch_names = subdomain_names[i : i + chunk_size]
                result = await session.execute(
                    select(Subdomain.id, Subdomain.subdomain).where(
                        Subdomain.target == target,
                        Subdomain.subdomain.in_(batch_names),
                    )
                )
                for sub_id, name in result.all():
                    subdomain_ids[name] = sub_id

            # 3. Bulk Link discovery sources
            source_values = []
            for r in rows:
                sub_id = subdomain_ids.get(_get(r, "subdomain"))
                if not sub_id:
                    continue
                source_names = _get(r, "sources_list")
                if not source_names:
                    sources_obj = _get(r, "sources")
                    source_names = (
                        [s.source_plugin for s in sources_obj]
                        if sources_obj
                        else [_get(r, "source_plugin") or "Imported"]
                    )
                for src_name in source_names:
                    if not src_name:
                        continue
                    source_values.append({
                        "subdomain_id": sub_id,
                        "source_plugin": src_name,
                    })

            for i in range(0, len(source_values), chunk_size):
                batch_src = source_values[i : i + chunk_size]
                if is_pg:
                    stmt_src = (
                        pg_insert(SubdomainSource)
                        .on_conflict_do_nothing(
                            index_elements=["subdomain_id", "source_plugin"]
                        )
                    )
                else:
                    stmt_src = (
                        sqlite_insert(SubdomainSource)
                        .on_conflict_do_nothing()
                    )
                await session.execute(stmt_src, batch_src)
                linked_sources += len(batch_src)

        return imported_count, linked_sources
