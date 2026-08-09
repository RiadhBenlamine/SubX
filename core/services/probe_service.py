"""Service layer for probing subdomains (HTTP/liveness & DNS resolution)."""
from core.db_models import Subdomain
from core.services.base import Service
from core.tool_manager import ToolManager
from tools.dnsx import DnsxTool
from tools.httpx import HttpxTool


class ProbeService(Service):
    """Orchestrates HTTP liveness and DNS resolution probing: run tool → persist → return rows."""

    async def probe_domain(
        self,
        domain: str,
        tool_config: dict | None = None,
        hosts: list[str] | None = None,
    ) -> tuple[list[dict], list[Subdomain]]:
        """Probe subdomains for a domain using httpx.

        Returns (raw_results, updated_rows).
        """
        tool_manager = ToolManager()
        results = await tool_manager.run_tool(
            HttpxTool(), domain, tool_config=tool_config, hosts=hosts
        )

        if not results:
            return [], []

        rows = await self._with_storage(lambda storage: storage.get_all(domain))
        return results, rows

    async def dns_probe_domain(
        self,
        domain: str,
        tool_config: dict | None = None,
        hosts: list[str] | None = None,
    ) -> tuple[list[dict], list[Subdomain]]:
        """Probe subdomains for a domain using dnsx.

        Returns (raw_results, updated_rows).
        """
        tool_manager = ToolManager()
        results = await tool_manager.run_tool(
            DnsxTool(), domain, tool_config=tool_config, hosts=hosts
        )

        if not results:
            return [], []

        rows = await self._with_storage(lambda storage: storage.get_all(domain))
        return results, rows

