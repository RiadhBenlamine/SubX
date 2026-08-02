"""Orchestrator for managing and executing pure external command-line tool wrappers."""
from core.logger import logger
from core.services.base import _get_storage
from core.tool import Tool


class ToolManager:
    """
    Orchestrates running any Tool subclass against stored subdomains and
    persisting its normalized output back to storage.

    Tools are pure (see Tool.run() contract: targets in, normalized dicts
    out). ToolManager owns all I/O around that — fetching the input list
    from storage and writing results back — so the same run_tool() method
    works for httpx, naabu, nuclei, or any future Tool without modification.
    """

    async def run_tool(
        self,
        tool: Tool,
        target: str,
        tool_config: dict | None = None,
        hosts: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        """
        Run `tool` against specified or stored subdomains for `target`, persist the
        normalized results, and return them.

        Returns [] if there's nothing to process.
        """
        storage = _get_storage()
        await storage.init()

        target_hosts = hosts if hosts is not None else await self._fetch_hosts(storage, target)
        if not target_hosts:
            logger.warning(
                "[%s] no subdomains to process for %s",
                tool.TOOL_NAME,
                target,
            )
            return []

        results = await tool.run(target_hosts, tool_config=tool_config, **kwargs)

        if results:
            await storage.update_results(target, results)

        return results

    @staticmethod
    async def _fetch_hosts(storage, target: str) -> list[str]:
        rows = await storage.get_all(target)
        return [row.subdomain for row in rows]
