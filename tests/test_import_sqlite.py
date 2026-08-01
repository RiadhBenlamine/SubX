import pytest

from core.models import ProcessedResult
from core.services.import_service import ImportService
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_import_sqlite_to_target_db(tmp_path):
    sqlite_file = tmp_path / "legacy_subx.db"

    # 1. Setup source SQLite database with sample subdomains, probe results, and sources
    source_storage = StorageManager(f"sqlite+aiosqlite:///{sqlite_file.as_posix()}")
    await source_storage.init()

    target = "example.com"
    res = ProcessedResult(
        by_plugin={
            "ShodanPlugin": ["sub1.example.com"],
            "CrtshPlugin": ["sub1.example.com", "sub2.example.com"],
        }
    )
    await source_storage.save(res, target)

    probe_data = [
        {
            "subdomain": "sub1.example.com",
            "alive": True,
            "status_code": 200,
            "title": "Sub 1 App",
            "tech": '["Nginx", "Vue"]',
            "ip": "1.1.1.1",
        },
        {
            "subdomain": "sub2.example.com",
            "alive": False,
        },
    ]
    await source_storage.update_results(target, probe_data)
    await source_storage.close()

    # 2. Setup target destination database
    target_db_file = tmp_path / "target_subx.db"
    target_url = f"sqlite+aiosqlite:///{target_db_file.as_posix()}"
    target_storage = StorageManager(target_url)

    # 3. Instantiate ImportService with target_storage and run import
    import_service = ImportService(storage=target_storage)
    summary = await import_service.import_sqlite(
        str(sqlite_file), target_db_url=target_url
    )

    assert summary.targets_count == 1
    assert summary.subdomains_imported == 2
    assert summary.sources_linked >= 2

    # 4. Verify data integrity in destination database
    imported_subs = await target_storage.get_all("example.com")
    assert len(imported_subs) == 2

    sub1_row = next(s for s in imported_subs if s.subdomain == "sub1.example.com")
    assert sub1_row.alive is True
    assert sub1_row.status_code == 200
    assert sub1_row.title == "Sub 1 App"
    assert sub1_row.tech == '["Nginx", "Vue"]'
    assert sub1_row.ip == "1.1.1.1"
    assert set(s.source_plugin for s in sub1_row.sources) == {"ShodanPlugin", "CrtshPlugin"}

    sub2_row = next(s for s in imported_subs if s.subdomain == "sub2.example.com")
    assert sub2_row.alive is False
    assert set(s.source_plugin for s in sub2_row.sources) == {"CrtshPlugin"}

    await target_storage.close()
