import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.db_models import Subdomain, SubdomainSource
from core.models import ProcessedResult
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_storage_upsert_and_deduplication():
    storage = StorageManager("sqlite+aiosqlite:///:memory:")
    await storage.init()
    
    target = "example.com"
    
    # 1. First run: ShodanPlugin discovers sub1.example.com
    res1 = ProcessedResult(
        by_plugin={"ShodanPlugin": ["sub1.example.com"]}
    )
    added1 = await storage.save(res1, target)
    assert added1 == 1
    
    # Verify count and source
    subs = await storage.get_all(target)
    assert len(subs) == 1
    assert subs[0].subdomain == "sub1.example.com"
    assert [s.source_plugin for s in subs[0].sources] == ["ShodanPlugin"]
    
    # 2. Second run: CrtshPlugin discovers sub1.example.com too
    res2 = ProcessedResult(
        by_plugin={
            "CrtshPlugin": ["sub1.example.com", "sub2.example.com"]
        }
    )
    added2 = await storage.save(res2, target)
    assert added2 == 1
    
    # Verify count is 2
    subs = await storage.get_all(target)
    assert len(subs) == 2
    
    # Verify sub1 has both ShodanPlugin and CrtshPlugin
    sub1_row = next(s for s in subs if s.subdomain == "sub1.example.com")
    assert set(s.source_plugin for s in sub1_row.sources) == {"ShodanPlugin", "CrtshPlugin"}
    
    # Verify get_by_plugin
    crtsh_subs = await storage.get_by_plugin(target, "CrtshPlugin")
    assert len(crtsh_subs) == 2
    assert set(s.subdomain for s in crtsh_subs) == {"sub1.example.com", "sub2.example.com"}
    
    await storage.close()

@pytest.mark.anyio
async def test_migration_path(tmp_path):
    db_file = tmp_path / "subx.db"
    
    # 1. Create a legacy database using sqlite3
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE subdomain (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT NOT NULL,
        subdomain TEXT NOT NULL,
        source_plugin TEXT NOT NULL,
        alive BOOLEAN,
        status_code INTEGER,
        title TEXT,
        first_seen TIMESTAMP NOT NULL,
        last_seen TIMESTAMP NOT NULL
    );
    """)
    
    now_str = "2026-07-13 18:00:00"
    later_str = "2026-07-13 19:00:00"
    
    cursor.execute("""
    INSERT INTO subdomain (target, subdomain, source_plugin, first_seen, last_seen)
    VALUES ('example.com', 'dup.example.com', 'PluginA', ?, ?);
    """, (now_str, now_str))
    
    cursor.execute("""
    INSERT INTO subdomain (target, subdomain, source_plugin, first_seen, last_seen)
    VALUES ('example.com', 'dup.example.com', 'PluginB', ?, ?);
    """, (later_str, later_str))
    
    conn.commit()
    conn.close()
    
    # 2. Point StorageManager to this legacy DB
    storage = StorageManager(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    await storage.init()
    
    # Run migration
    added = await storage.migrate(backup=True)
    assert "uq_target_subdomain_constraint" in added
    
    # 3. Verify backup file was created
    backups = list(tmp_path.glob("subx.backup-*.db"))
    assert len(backups) == 1
    
    # 4. Verify data in migrated DB
    subs = await storage.get_all("example.com")
    assert len(subs) == 1
    sub = subs[0]
    assert sub.subdomain == "dup.example.com"
    
    # Datetime string parsing can sometimes be a bit format-dependent, let's normalize or compare strings
    assert sub.first_seen.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-13 18:00:00"
    assert sub.last_seen.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-13 19:00:00"
    
    assert set(s.source_plugin for s in sub.sources) == {"PluginA", "PluginB"}
    
    await storage.close()


@pytest.mark.anyio
async def test_storage_tech_and_alive():
    storage = StorageManager("sqlite+aiosqlite:///:memory:")
    await storage.init()

    target = "example.com"
    res = ProcessedResult(by_plugin={"ShodanPlugin": ["app.example.com", "api.example.com"]})
    await storage.save(res, target)

    # Simulate httpx probe results update
    probe_results = [
        {
            "subdomain": "app.example.com",
            "alive": True,
            "status_code": 200,
            "title": "App",
            "tech": '["Nginx", "React"]',
        },
        {
            "subdomain": "api.example.com",
            "alive": False,
            "tech": None,
        },
    ]
    updated = await storage.update_results(target, probe_results)
    assert updated == 2

    # Verify get_by_tech
    nginx_subs = await storage.get_by_tech(target, "Nginx")
    assert len(nginx_subs) == 1
    assert nginx_subs[0].subdomain == "app.example.com"

    # Verify get_alive
    alive_subs = await storage.get_alive(target)
    assert len(alive_subs) == 1
    assert alive_subs[0].subdomain == "app.example.com"
    assert alive_subs[0].last_seen_alive is not None

    await storage.close()


@pytest.mark.anyio
async def test_last_seen_alive_tracking():
    storage = StorageManager("sqlite+aiosqlite:///:memory:")
    await storage.init()

    target = "example.com"
    res = ProcessedResult(by_plugin={"ShodanPlugin": ["app.example.com"]})
    await storage.save(res, target)

    # 1. First probe: app.example.com is ALIVE
    await storage.update_results(target, [{"subdomain": "app.example.com", "alive": True}])
    subs = await storage.get_all(target)
    assert subs[0].alive is True
    first_alive_time = subs[0].last_seen_alive
    assert first_alive_time is not None

    # 2. Second probe later: app.example.com goes DOWN (alive=False)
    await storage.update_results(target, [{"subdomain": "app.example.com", "alive": False}])
    subs = await storage.get_all(target)
    assert subs[0].alive is False
    # last_seen_alive should be preserved from when it was live!
    assert subs[0].last_seen_alive == first_alive_time

    # 3. Verify get_dead returns the down subdomain
    dead_subs = await storage.get_dead(target)
    assert len(dead_subs) == 1
    assert dead_subs[0].subdomain == "app.example.com"
    assert dead_subs[0].last_seen_alive == first_alive_time

    await storage.close()


