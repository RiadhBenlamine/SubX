
from core.db_models import Subdomain, SubdomainSource
from core.storage_manager import normalize_db_url


def test_table_names_prefix():
    """Verify tables use the subx_ prefix."""
    assert Subdomain.__tablename__ == "subx_subdomain"
    assert SubdomainSource.__tablename__ == "subx_subdomain_sources"


def test_normalize_db_url_env_vars(monkeypatch):
    """Verify PostgreSQL connection URL construction from environment variables."""
    monkeypatch.setenv("SUBX_DB_HOST", "192.168.1.100")
    monkeypatch.setenv("SUBX_DB_USER", "recon_user")
    monkeypatch.setenv("SUBX_DB_PASS", "secr3tpass")
    monkeypatch.setenv("SUBX_DB_PORT", "5433")
    monkeypatch.setenv("SUBX_DB_NAME", "subx")

    url = normalize_db_url()
    assert url == "postgresql+asyncpg://recon_user:secr3tpass@192.168.1.100:5433/subx"
