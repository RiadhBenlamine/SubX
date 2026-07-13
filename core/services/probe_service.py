"""Service layer for probing subdomains (HTTP/liveness)."""
from core.db_models import Subdomain
from core.services.base import Service
from core.tool_manager import ToolManager
from tools.httpx import HttpxTool


class ProbeService(Service):
    """Orchestrates HTTP liveness probing: run httpx → persist → return rows."""

    async def probe_domain(self, domain: str) -> tuple[list[dict], list[Subdomain]]:
        """Probe all stored subdomains for a domain.

        Returns (raw_results, updated_rows):
          - raw_results: the httpx output (empty list if nothing stored)
          - updated_rows: the full subdomain list from storage after probing
        """
        tool_manager = ToolManager()
        results = await tool_manager.run_tool(HttpxTool(), domain)

        if not results:
            return [], []

        rows = await self._with_storage(lambda storage: storage.get_all(domain))
        return results, rows
