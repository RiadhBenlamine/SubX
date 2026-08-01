from pathlib import Path
import pytest

from core.cmd.project import ProjectCommand
from core.models import ProcessedResult
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_project_command_config_file_resolution(tmp_path, monkeypatch):
    """Verify ProjectCommand resolves target domains from config.yaml when --domain is omitted."""
    db_file = tmp_path / "subx.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    storage = StorageManager(db_url)
    await storage.init()

    # Save target data for two domains
    await storage.save(ProcessedResult(by_plugin={"CrtshPlugin": ["sub1.domaina.com"]}), "domaina.com")
    await storage.save(ProcessedResult(by_plugin={"CrtshPlugin": ["sub1.domainb.com"]}), "domainb.com")
    await storage.close()

    # Create config file with both domains in scope
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "scope:\n  - domaina.com\n  - domainb.com\n", encoding="utf-8"
    )

    out_dir = tmp_path / "projects"

    # Instantiate command and run
    cmd = ProjectCommand()
    await cmd._project(domain=None, config_path=str(cfg_file), out_dir=str(out_dir))

    # Verify project folders were created for both domains
    assert (out_dir / "domaina.com" / "recon" / "subdomains.txt").exists()
    assert (out_dir / "domainb.com" / "recon" / "subdomains.txt").exists()

    subs_a = (out_dir / "domaina.com" / "recon" / "subdomains.txt").read_text(encoding="utf-8").splitlines()
    assert subs_a == ["sub1.domaina.com"]

    subs_b = (out_dir / "domainb.com" / "recon" / "subdomains.txt").read_text(encoding="utf-8").splitlines()
    assert subs_b == ["sub1.domainb.com"]
