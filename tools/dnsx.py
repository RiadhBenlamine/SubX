import json
import subprocess
import sys
from pathlib import Path

from core.logger import logger
from core.tool import Tool, ToolExecutionError, ToolNotFoundError, ToolTimeoutError


class DnsxTool(Tool):
    """
    Pure dnsx wrapper: takes a list of hosts, performs fast DNS resolution,
    and returns normalized IP mapping results.
    """

    TOOL_NAME = "dnsx"

    MIN_TIMEOUT = 60
    PER_HOST_SECONDS = 0.1

    @staticmethod
    def _install_hint() -> str:
        """Return a platform-appropriate install instruction."""
        if sys.platform == "win32":
            return (
                "Download the latest release from "
                "https://github.com/projectdiscovery/dnsx/releases "
                "and place the .exe in bin/dnsx/dnsx.exe."
            )
        return (
            "Install via: go install -v "
            "github.com/projectdiscovery/dnsx/cmd/dnsx@latest  "
            "or: apt install dnsx"
        )

    def _validate_tool_path(self, path: Path) -> None:
        """Validate ProjectDiscovery's dnsx binary."""
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
                    f"'{path}' is not ProjectDiscovery's dnsx "
                    f"(got: {combined.strip()[:120]}). "
                    f"{self._install_hint()}"
                )
        except FileNotFoundError:
            raise ToolNotFoundError(
                f"dnsx binary not found at '{path}'."
            )
        except PermissionError:
            raise ToolNotFoundError(
                f"'{path}' is not executable. "
                f"On Linux/macOS run: chmod +x '{path}'"
            )
        except OSError as e:
            raise ToolNotFoundError(
                f"Cannot execute '{path}': {e}"
            )
        except subprocess.TimeoutExpired:
            raise ToolNotFoundError(
                f"'{path}' timed out on `-version` — likely not "
                f"ProjectDiscovery's dnsx."
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
        args = ["-silent", "-json", "-a", "-resp", "-no-color"]

        target_count = len(targets)
        # Dynamically auto-tune concurrency & retries based on target count
        if "threads" not in user_config and "t" not in user_config:
            if target_count < 50:
                threads = max(5, target_count)
            elif target_count < 1000:
                threads = 150
            elif target_count < 10000:
                threads = 300
            else:
                threads = 500
            args.extend(["-threads", str(threads)])

        if "retry" not in user_config and "r" not in user_config:
            retry = "3" if target_count < 100 else "2"
            args.extend(["-retry", retry])

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
            stdout, _ = await self._execute(
                args,
                input_data=input_data,
                timeout=timeout,
            )
        except ToolNotFoundError:
            logger.info("[dnsx] binary not found — %s", self._install_hint())
            raise
        except ToolTimeoutError:
            logger.error(f"[dnsx] timed out after {timeout}s on {len(targets)} hosts")
            raise
        except ToolExecutionError as e:
            logger.error(f"[dnsx] {e}")
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
        """Map dnsx's raw JSON lines onto generic {subdomain, ip} dicts.

        dnsx emits lines such as:
            {"host": "app.example.com", "a": ["1.2.3.4", "1.2.3.5"]}
        """
        results: list[dict] = []

        for raw in raw_results:
            host = raw.get("host") or raw.get("input")
            if not host:
                continue

            a_records = raw.get("a") or []
            if isinstance(a_records, str):
                a_records = [a_records]

            ip_str = ", ".join(a_records) if a_records else None
            if ip_str:
                results.append({
                    "subdomain": host,
                    "ip": ip_str,
                })

        return results
