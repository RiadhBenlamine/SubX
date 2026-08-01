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

        targets_summary = await source_storage.get_targets_summary()
        total_subdomains = 0
        total_sources = 0

        for item in targets_summary:
            domain = item["target"]
            rows: list[Subdomain] = await source_storage.get_all(domain)
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
            targets_count=len(targets_summary),
            subdomains_imported=total_subdomains,
            sources_linked=total_sources,
        )

    @staticmethod
    async def _import_rows_batch(
        target_storage: StorageManager,
        target: str,
        rows: list[Subdomain],
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

        async with target_storage._session() as session, session.begin():
            # 1. Upsert subdomains
            for i in range(0, len(rows), chunk_size):
                batch = rows[i : i + chunk_size]
                for r in batch:
                    stmt = (
                        insert_fn(Subdomain)
                        .values(
                            target=r.target,
                            subdomain=r.subdomain,
                            source_plugin=r.source_plugin,
                            alive=r.alive,
                            status_code=r.status_code,
                            title=r.title,
                            tech=r.tech,
                            ip=r.ip,
                            first_seen=r.first_seen,
                            last_seen=r.last_seen,
                            last_seen_alive=r.last_seen_alive,
                        )
                        .on_conflict_do_update(
                            index_elements=["target", "subdomain"],
                            set_={
                                "alive": r.alive,
                                "status_code": r.status_code,
                                "title": r.title,
                                "tech": r.tech,
                                "ip": r.ip,
                                "last_seen": r.last_seen,
                                "last_seen_alive": r.last_seen_alive,
                            },
                        )
                    )
                    await session.execute(stmt)
                    imported_count += 1

            # 2. Retrieve new IDs in destination DB for source linkage
            subdomain_names = [r.subdomain for r in rows]
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

            # 3. Link discovery sources
            for r in rows:
                sub_id = subdomain_ids.get(r.subdomain)
                if not sub_id:
                    continue
                source_names = (
                    [s.source_plugin for s in r.sources]
                    if getattr(r, "sources", None)
                    else [r.source_plugin]
                )
                for src_name in source_names:
                    if is_pg:
                        stmt_src = (
                            insert_fn(SubdomainSource)
                            .values(
                                subdomain_id=sub_id,
                                source_plugin=src_name,
                            )
                            .on_conflict_do_nothing(
                                index_elements=["subdomain_id", "source_plugin"]
                            )
                        )
                    else:
                        stmt_src = (
                            insert_fn(SubdomainSource)
                            .values(
                                subdomain_id=sub_id,
                                source_plugin=src_name,
                            )
                            .on_conflict_do_nothing()
                        )
                    await session.execute(stmt_src)
                    linked_sources += 1

        return imported_count, linked_sources
