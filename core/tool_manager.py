from core.logger import logger
from core.storage_manager import StorageManager
from core.tool import Tool, ToolExecutionError, ToolNotFoundError, ToolTimeoutError


class ToolManager:
    """
    Orchestrates running any Tool subclass against stored subdomains and
    persisting its normalized output back to storage.

    Tools are pure (see Tool.run() contract: targets in, normalized dicts
    out). ToolManager owns all I/O around that — fetching the input list
    from storage and writing results back — so the same run_tool() method
    works for httpx, naabu, nuclei, or any future Tool without modification.
    """

    def __init__(self):
        self.storage = StorageManager()

    async def run_tool(self, tool: Tool, target: str, **kwargs) -> list[dict]:
        """
        Run `tool` against every stored subdomain for `target`, persist the
        normalized results, and return them.

        Returns [] if there's nothing stored for `target` yet (run `subx
        enum` first). Storage is opened and closed per call so ToolManager
        instances are safe to reuse across multiple run_tool() calls.
        """
        await self.storage.init()
        try:
            hosts = await self._fetch_hosts(target)
            if not hosts:
                logger.warning(f"[{tool.TOOL_NAME}] no subdomains stored for {target}")
                return []

            try:
                results = await tool.run(hosts, **kwargs)
            except (ToolNotFoundError, ToolTimeoutError, ToolExecutionError):
                # Already logged with tool-specific context inside the tool;
                # re-raise so the CLI layer can decide how to present it.
                raise

            if results:
                await self._persist(target, results)

            return results
        finally:
            await self.storage.close()

    async def _fetch_hosts(self, target: str) -> list[str]:
        rows = await self.storage.get_all(target)
        return [row.subdomain for row in rows]

    async def _persist(self, target: str, results: list[dict]) -> None:
        """
        Write a tool's normalized results back to storage.

        Generic on purpose: any Tool's output is a list of dicts keyed by
        "subdomain" plus whatever fields that tool produces (alive/status_code/
        title for httpx, open_ports for naabu, matched templates for nuclei,
        etc.). StorageManager.update_results() is expected to upsert by
        "subdomain" and merge in whatever other keys are present, so adding
        a new tool never requires touching ToolManager.
        """
        await self.storage.update_results(target, results)