from core.db_models import Subdomain
from core.storage_manager import StorageManager
from core.tool_manager import ToolManager
from tools.httpx import HttpxTool


class ProbeService:
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

        # ToolManager already persisted the results, read back the updated rows
        storage = StorageManager()
        await storage.init()
        try:
            rows = await storage.get_all(domain)
        finally:
            await storage.close()

        return results, rows
