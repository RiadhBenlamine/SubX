import json
import subprocess
import sys
from pathlib import Path

from core.logger import logger
from core.tool import Tool, ToolExecutionError, ToolNotFoundError, ToolTimeoutError


class HttpxTool(Tool):
    """
    Pure httpx wrapper: takes a list of hosts, returns normalized liveness
    results. No storage, no I/O beyond running the httpx binary — fetching
    input and persisting output is ToolManager's job.

    Works on both Windows (bundled .exe in bin/) and Linux/macOS
    (resolved from PATH or common Go install directories).
    """

    TOOL_NAME = "httpx"

    # httpx defaults to 50 concurrent workers and ~10s per request before
    # giving up on a single host. Budget generously per host so large lists
    # (thousands of subdomains) don't get cut off mid-run, while small lists
    # still get a reasonable floor rather than an unnecessarily long wait.
    MIN_TIMEOUT = 120
    PER_HOST_SECONDS = 0.3  # ~3000 hosts -> +900s on top of the floor

    @staticmethod
    def _install_hint() -> str:
        """Return a platform-appropriate install instruction."""
        if sys.platform == "win32":
            return (
                "Download the latest release from "
                "https://github.com/projectdiscovery/httpx/releases "
                "and place the .exe in bin/httpx/httpx.exe."
            )
        return (
            "Install via: go install -v "
            "github.com/projectdiscovery/httpx/cmd/httpx@latest  "
            "or: apt install httpx"
        )

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
                    f"'{path}' is not ProjectDiscovery's httpx "
                    f"(got: {combined.strip()[:120]}). "
                    f"{self._install_hint()}"
                )
        except FileNotFoundError:
            raise ToolNotFoundError(
                f"httpx binary not found at '{path}'."
            )
        except PermissionError:
            raise ToolNotFoundError(
                f"'{path}' is not executable. "
                f"On Linux/macOS run: chmod +x '{path}'"
            )
        except OSError as e:
            # Catch-all for other OS-level errors (e.g. bad ELF binary on
            # wrong architecture, missing shared libraries, etc.)
            raise ToolNotFoundError(
                f"Cannot execute '{path}': {e}"
            )
        except subprocess.TimeoutExpired:
            raise ToolNotFoundError(
                f"'{path}' timed out on `-version` — likely not "
                f"ProjectDiscovery's httpx."
            )

    def _scaled_timeout(self, target_count: int) -> int:
        return max(self.MIN_TIMEOUT, int(target_count * self.PER_HOST_SECONDS))

    async def run(
        self,
        targets: list[str],
        timeout: int | None = None,
        tool_config: dict | None = None,
    ) -> list[dict]:
        if not targets:
            return []

        if timeout is None:
            timeout = self._scaled_timeout(len(targets))

        input_data = "\n".join(targets) + "\n"

        user_config = tool_config or {}
        args = ["-silent", "-json", "-tech-detect", "-no-color"]

        target_count = len(targets)
        # Dynamically auto-tune concurrency, timeout & retries based on target count
        if "threads" not in user_config and "t" not in user_config:
            if target_count < 50:
                threads = max(5, target_count)
            elif target_count < 1000:
                threads = 100
            else:
                threads = 200
            args.extend(["-threads", str(threads)])

        if "timeout" not in user_config:
            timeout_val = "5" if target_count < 1000 else "4"
            args.extend(["-timeout", timeout_val])

        if "retries" not in user_config and "r" not in user_config:
            retries_val = "2" if target_count < 50 else "1"
            args.extend(["-retries", retries_val])

        # Merge extra CLI flags from config
        if tool_config:
            for key, value in tool_config.items():
                if key == "enabled":
                    continue
                flag = f"-{key}" if not key.startswith("-") else key
                if isinstance(value, bool):
                    if value:
                        args.append(flag)
                else:
                    args.extend([flag, str(value)])

        try:
            stdout, stderr = await self._execute(
                args,
                input_data=input_data,
                timeout=timeout,
            )
        except ToolNotFoundError:
            logger.info(
                "[httpx] binary not found — %s", self._install_hint()
            )
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
                tech_list = raw.get("tech")
                if tech_list:
                    tech_list = [t for t in tech_list if t.upper() != "HSTS"]
                host_ip = raw.get("host_ip")
                if not host_ip and raw.get("a"):
                    a_rec = raw["a"]
                    host_ip = ", ".join(a_rec) if isinstance(a_rec, list) else str(a_rec)
                results[host] = {
                    "subdomain": host,
                    "alive": True,
                    "status_code": raw.get("status_code"),
                    "title": raw.get("title"),
                    "tech": json.dumps(tech_list) if tech_list else None,
                    "ip": host_ip,
                }

        # Anything we sent in but didn't get a response line for = dead.
        for host in targets:
            if host not in results:
                results[host] = {"subdomain": host, "alive": False}

        return list(results.values())
