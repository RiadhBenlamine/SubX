import json
import subprocess
from pathlib import Path

from core.logger import logger
from core.tool import (Tool, ToolExecutionError, ToolNotFoundError,
                       ToolTimeoutError)


class HttpxTool(Tool):
    """
    Pure httpx wrapper: takes a list of hosts, returns normalized liveness
    results. No storage, no I/O beyond running the httpx binary — fetching
    input and persisting output is ToolManager's job.
    """

    TOOL_NAME = "httpx"

    def _validate_tool_path(self, path: Path) -> None:
        """Reject the Python ``httpx`` CLI (pip-installed name collision).

        ProjectDiscovery's Go binary prints 'projectdiscovery' somewhere in
        its ``-version`` output.  The Python ``httpx`` CLI (from the httpx
        HTTP-client library) does not, and it also doesn't understand
        ``-version`` at all — it exits non-zero.
        """
        try:
            result = subprocess.run(
                [str(path), "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            combined = result.stdout + result.stderr
            if "projectdiscovery" not in combined.lower():
                raise ToolNotFoundError(
                    f"'{path}' does not appear to be ProjectDiscovery's httpx "
                    f"(got: {combined.strip()[:120]}). "
                    f"Install the correct httpx via `go install -v "
                    f"github.com/projectdiscovery/httpx/cmd/httpx@latest`."
                )
        except FileNotFoundError:
            raise ToolNotFoundError(
                f"httpx binary not found at '{path}'."
            )
        except subprocess.TimeoutExpired:
            # If it hangs on -version it's probably not the right binary
            raise ToolNotFoundError(
                f"'{path}' timed out on `-version` — likely not "
                f"ProjectDiscovery's httpx."
            )

    # httpx defaults to 50 concurrent workers and ~10s per request before
    # giving up on a single host. Budget generously per host so large lists
    # (thousands of subdomains) don't get cut off mid-run, while small lists
    # still get a reasonable floor rather than an unnecessarily long wait.
    MIN_TIMEOUT = 120
    PER_HOST_SECONDS = 0.3  # ~3000 hosts -> +900s on top of the floor

    def _scaled_timeout(self, target_count: int) -> int:
        return max(self.MIN_TIMEOUT, int(target_count * self.PER_HOST_SECONDS))

    async def run(self, targets: list[str], timeout: int | None = None) -> list[dict]:
        if not targets:
            return []

        if timeout is None:
            timeout = self._scaled_timeout(len(targets))

        input_data = "\n".join(targets) + "\n"

        try:
            stdout, stderr = await self._execute(
                ["-silent", "-json"],
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
