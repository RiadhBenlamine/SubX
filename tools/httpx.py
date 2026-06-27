import json

from core.logger import logger
from core.tool import Tool, ToolExecutionError, ToolNotFoundError, ToolTimeoutError


class HttpxTool(Tool):
    """
    Pure httpx wrapper: takes a list of hosts, returns normalized liveness
    results. No storage, no I/O beyond running the httpx binary — fetching
    input and persisting output is ToolManager's job.
    """

    TOOL_NAME = "httpx"

    async def run(self, targets: list[str], timeout: int = 120) -> list[dict]:
        if not targets:
            return []

        input_data = "\n".join(targets) + "\n"

        try:
            stdout, stderr = await self._execute(
                ["-silent", "-json", "-t 50"],
                input_data=input_data,
                timeout=timeout,
            )
        except ToolNotFoundError:
            logger.error("[httpx] binary not found — check install / PATH")
            raise
        except ToolTimeoutError:
            logger.error(f"[httpx] timed out after {timeout}s on {len(targets)} hosts")
            raise
        except ToolExecutionError as e:
            # httpx can write warnings to stderr and still exit 0 in some
            # versions, but a genuine non-zero exit means something broke.
            logger.error(f"[httpx] {e}")
            raise

        raw_results = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw_results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return self._normalize(targets, raw_results)

    def _normalize(self, targets: list[str], raw_results: list[dict]) -> list[dict]:
        """Map httpx's raw JSON lines onto a generic {subdomain, alive, ...} shape.

        httpx emits one JSON object per *attempted* host, keyed by "input"
        (the original hostname you fed it), "status_code", and "title".
        Confirmed live sample line:

            {"input": "pmbounces.hackerone.com", "status_code": 200,
             "title": "Postmark — Email delivery for web apps",
             "failed": False, ...}

        Two distinct "dead" cases:
          1. httpx emits a line but sets "failed": True (connection refused,
             TLS error, etc. after a real attempt) — status_code/title will
             usually be absent or stale, so we don't trust them.
          2. httpx never emits a line at all for that host (DNS resolution
             failed before any HTTP attempt was made).

        Both are recorded as alive=False; only a line with failed=False
        gets alive=True plus its status_code/title.
        """
        results: dict[str, dict] = {}

        for raw in raw_results:
            host = raw.get("input") or raw.get("url")
            if not host:
                continue

            if raw.get("failed"):
                results[host] = {"subdomain": host, "alive": False}
            else:
                results[host] = {
                    "subdomain": host,
                    "alive": True,
                    "status_code": raw.get("status_code"),
                    "title": raw.get("title"),
                }

        # Anything we sent in but didn't get a response line for = dead.
        for host in targets:
            if host not in results:
                results[host] = {"subdomain": host, "alive": False}

        return list(results.values())