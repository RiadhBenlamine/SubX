from pathlib import Path
import pytest

from core.models import ProcessedResult
from core.services.project_service import ProjectService
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_project_service_checks_and_merges_without_dups(tmp_path):
    """Verify export_project reads existing files, appends new entries, and eliminates duplicates."""
    db_file = tmp_path / "subx.db"
    storage = StorageManager(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    await storage.init()

    target = "testdomain.com"

    # 1. Pre-create project recon directory with pre-existing manual data
    projects_dir = tmp_path / "projects"
    recon_dir = projects_dir / target / "recon"
    recon_dir.mkdir(parents=True, exist_ok=True)

    subdomains_file = recon_dir / "subdomains.txt"
    subdomains_file.write_text("old1.testdomain.com\nold2.testdomain.com\n", encoding="utf-8")

    # 2. Save DB result containing an overlap ("old2.testdomain.com") and a new entry ("new3.testdomain.com")
    res = ProcessedResult(by_plugin={"CrtshPlugin": ["old2.testdomain.com", "new3.testdomain.com"]})
    await storage.save(res, target)

    # 3. Export project
    service = ProjectService(storage=storage)
    summary = await service.export_project(target, out_dir=str(projects_dir))

    # 4. Verify subdomains.txt merged without duplicates
    lines = subdomains_file.read_text(encoding="utf-8").splitlines()
    assert lines == ["old1.testdomain.com", "old2.testdomain.com", "new3.testdomain.com"]
    assert len(lines) == len(set(lines))

    await storage.close()
