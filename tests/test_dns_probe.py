import pytest
from unittest.mock import AsyncMock, patch

from core.cmd.probe import DnsProbeCommand, HttpProbeCommand, ProbeCommand
from core.db_models import Subdomain
from core.services.probe_service import ProbeService


def test_probe_command_is_base_class():
    """ProbeCommand is the abstract base; Http/Dns inherit from it."""
    assert issubclass(HttpProbeCommand, ProbeCommand)
    assert issubclass(DnsProbeCommand, ProbeCommand)


def test_http_probe_command_registration():
    cmd = HttpProbeCommand()
    assert cmd.name == "http-probe"
    assert cmd.tool_name == "httpx"
    assert "httpx" in cmd.help


def test_dns_probe_command_registration():
    cmd = DnsProbeCommand()
    assert cmd.name == "dns-probe"
    assert cmd.tool_name == "dnsx"
    assert "dnsx" in cmd.help


@pytest.mark.anyio
async def test_dns_probe_service():
    service = ProbeService()
    mock_results = [{"subdomain": "sub.example.com", "ip": "1.2.3.4"}]
    mock_rows = [Subdomain(target="example.com", subdomain="sub.example.com", source_plugin="test", ip="1.2.3.4")]

    with patch("core.tool_manager.ToolManager.run_tool", new_callable=AsyncMock) as mock_run, \
         patch.object(ProbeService, "_with_storage", new_callable=AsyncMock) as mock_storage:
        mock_run.return_value = mock_results
        mock_storage.return_value = mock_rows

        results, rows = await service.dns_probe_domain("example.com")

        assert results == mock_results
        assert rows == mock_rows
        mock_run.assert_called_once()


@pytest.mark.anyio
async def test_http_probe_service():
    service = ProbeService()
    mock_results = [{"subdomain": "sub.example.com", "alive": True, "status_code": 200}]
    mock_rows = [Subdomain(target="example.com", subdomain="sub.example.com", source_plugin="test", alive=True)]

    with patch("core.tool_manager.ToolManager.run_tool", new_callable=AsyncMock) as mock_run, \
         patch.object(ProbeService, "_with_storage", new_callable=AsyncMock) as mock_storage:
        mock_run.return_value = mock_results
        mock_storage.return_value = mock_rows

        results, rows = await service.probe_domain("example.com")

        assert results == mock_results
        assert rows == mock_rows
        mock_run.assert_called_once()
