from pathlib import Path
from core.storage_manager import normalize_db_url


def test_normalize_db_url_config_fallback(tmp_path, monkeypatch):
    """Verify normalize_db_url prioritizes PostgreSQL settings in config file."""
    # Ensure env vars are cleared for clean test
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUBX_DB_URL", raising=False)
    monkeypatch.delenv("SUBX_DB_HOST", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)

    fake_config = tmp_path / "config.yaml"
    fake_config.write_text(
        "db:\n  host: '10.0.0.50'\n  user: 'sec_admin'\n  password: 'mypassword'\n  port: 5432\n  dbname: 'subx'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Write to ~/.config/subx/config.yaml
    global_cfg_dir = tmp_path / ".config" / "subx"
    global_cfg_dir.mkdir(parents=True, exist_ok=True)
    global_cfg = global_cfg_dir / "config.yaml"
    global_cfg.write_text(fake_config.read_text())

    url = normalize_db_url()
    assert url == "postgresql+asyncpg://sec_admin:mypassword@10.0.0.50:5432/subx"
