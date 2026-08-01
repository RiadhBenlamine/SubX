
import pytest

from core.models import ProcessedResult
from core.services.project_service import ProjectService
from core.storage_manager import StorageManager


@pytest.mark.anyio
async def test_project_service_structure_and_export(tmp_path):
    db_file = tmp_path / "subx.db"
    storage = StorageManager(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    await storage.init()

    target = "example.com"
    res = ProcessedResult(by_plugin={"ShodanPlugin": ["app.example.com", "api.example.com"]})
    await storage.save(res, target)

    # Update probing results including tech, status_code, title, and IP
    probe_results = [
        {
            "subdomain": "app.example.com",
            "alive": True,
            "status_code": 200,
            "title": "Example App",
            "tech": '["Nginx", "React"]',
            "ip": "1.2.3.4",
        },
        {
            "subdomain": "api.example.com",
            "alive": False,
        },
    ]
    await storage.update_results(target, probe_results)

    # Instantiate ProjectService and run export
    service = ProjectService(storage=storage)
    summary = await service.export_project(target, out_dir=str(tmp_path / "projects"))

    recon_dir = summary.recon_dir
    assert recon_dir.exists()
    assert summary.project_dir == tmp_path / "projects" / target

    # Verify subdomains.txt
    subdomains_file = recon_dir / "subdomains.txt"
    assert subdomains_file.is_file()
    subs_content = subdomains_file.read_text(encoding="utf-8").splitlines()
    assert set(subs_content) == {"api.example.com", "app.example.com"}

    # Verify alive.txt
    alive_file = recon_dir / "alive.txt"
    assert alive_file.is_file()
    assert alive_file.read_text(encoding="utf-8").splitlines() == ["app.example.com"]

    # Verify dead.txt
    dead_file = recon_dir / "dead.txt"
    assert dead_file.is_file()
    assert dead_file.read_text(encoding="utf-8").splitlines() == ["api.example.com"]

    # Verify techs.txt
    techs_file = recon_dir / "techs.txt"
    assert techs_file.is_file()
    techs_content = techs_file.read_text(encoding="utf-8")
    assert "app.example.com [Nginx, React]" in techs_content

    # Verify status.txt
    status_file = recon_dir / "status.txt"
    assert status_file.is_file()
    status_content = status_file.read_text(encoding="utf-8")
    assert "app.example.com [200] [Example App]" in status_content

    # Verify ips.txt
    ips_file = recon_dir / "ips.txt"
    assert ips_file.is_file()
    ips_content = ips_file.read_text(encoding="utf-8")
    assert "app.example.com [1.2.3.4]" in ips_content

    # Verify sources.txt
    sources_file = recon_dir / "sources.txt"
    assert sources_file.is_file()
    sources_content = sources_file.read_text(encoding="utf-8")
    assert "app.example.com [ShodanPlugin]" in sources_content

    await storage.close()
