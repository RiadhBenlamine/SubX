from core.logger import logger
from core.services.base import _get_storage
from core.tool import (Tool, ToolExecutionError, ToolNotFoundError,
                       ToolTimeoutError)


class ToolManager:
    """
    Orchestrates running any Tool subclass against stored subdomains and
    persisting its normalized output back to storage.

    Tools are pure (see Tool.run() contract: targets in, normalized dicts
    out). ToolManager owns all I/O around that — fetching the input list
    from storage and writing results back — so the same run_tool() method
    works for httpx, naabu, nuclei, or any future Tool without modification.
    """

    async def run_tool(self, tool: Tool, target: str, **kwargs) -> list[dict]:
        """
        Run `tool` against every stored subdomain for `target`, persist the
        normalized results, and return them.

        Returns [] if there's nothing stored for `target` yet (run `subx
        enum` first).
        """
        storage = _get_storage()
        await storage.init()

        hosts = await self._fetch_hosts(storage, target)
        if not hosts:
            logger.warning(f"[{tool.TOOL_NAME}] no subdomains stored for {target}")
            return []

        try:
            results = await tool.run(hosts, **kwargs)
        except (ToolNotFoundError, ToolTimeoutError, ToolExecutionError):
            raise

        if results:
            await storage.update_results(target, results)

        return results

    @staticmethod
    async def _fetch_hosts(storage, target: str) -> list[str]:
        rows = await storage.get_all(target)
        return [row.subdomain for row in rows]