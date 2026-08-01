
import pytest
from sqlalchemy.exc import OperationalError

from core.models import ProcessedResult
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_raw_query_readonly_blocks_writes(tmp_path):
    db_file = tmp_path / "subx.db"
    
    storage = StorageManager(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    await storage.init()
    
    res = ProcessedResult(
        by_plugin={"ShodanPlugin": ["test.example.com"]}
    )
    await storage.save(res, "example.com")
    
    rows = await storage.raw_query("SELECT subdomain FROM subdomain WHERE target = 'example.com';")
    assert len(rows) == 1
    assert rows[0]["subdomain"] == "test.example.com"
    
    with pytest.raises(OperationalError) as exc_info:
        await storage.raw_query(
            "INSERT INTO subdomain (target, subdomain, source_plugin) VALUES ('example.com', 'evil.example.com', 'Evil');"
        )
        
    assert "readonly" in str(exc_info.value).lower() or "read-only" in str(exc_info.value).lower()
    
    await storage.close()
