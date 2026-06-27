import asyncio
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path


class ToolNotFoundError(Exception):
    """Raised when a required external tool binary cannot be located."""


class ToolExecutionError(Exception):
    """Raised when an external tool exits with a non-zero status."""

    def __init__(self, name: str, returncode: int, stderr: str):
        self.name = name
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{name} exited with code {returncode}: {stderr.strip()[:500]}")


class ToolTimeoutError(Exception):
    """Raised when an external tool exceeds its allotted runtime."""


class Tool(ABC):
    """
    Generic abstract base class for SubX external tool wrappers
    (httpx, naabu, nuclei, the Go resolver, etc).

    Resolution strategy:
      - Windows: BASE_DIR/bin/<name>/<name>.exe (bundled)
      - Linux/macOS: system PATH (installed via `go install` / apt)

    Subclasses must set TOOL_NAME and implement run().
    """

    BASE_DIR = Path(__file__).resolve().parent.parent

    # Subclasses override this with the actual binary name, e.g. "httpx"
    TOOL_NAME: str = ""

    @staticmethod
    def _get_os() -> str:
        return sys.platform

    def _resolve_tool_path(self, name: str) -> Path:
        """
        Resolve the path to a tool binary.

        On Windows, looks for a bundled binary at BASE_DIR/bin/<name>/<name>.exe.
        On Linux/macOS, looks it up on the system PATH (go install / apt installs).

        Raises ToolNotFoundError if the binary can't be found either way.
        """
        if self._get_os() == "win32":
            bundled = self.BASE_DIR / "bin" / name / f"{name}.exe"
            if bundled.is_file():
                return bundled
            raise ToolNotFoundError(
                f"Could not locate '{name}' at expected bundled path '{bundled}'."
            )

        on_path = shutil.which(name)
        if on_path:
            return Path(on_path)

        raise ToolNotFoundError(
            f"Could not locate '{name}' on PATH. Install it via `go install` or apt."
        )

    def _tool_exists(self, name: str) -> bool:
        """Cheap existence check — no subprocess spawn needed."""
        try:
            self._resolve_tool_path(name)
            return True
        except ToolNotFoundError:
            return False

    async def _execute(
        self,
        args: list[str],
        timeout: int = 300,
        input_data: str | None = None,
    ) -> tuple[str, str]:
        """
        Run the resolved tool binary with the given args.

        Returns (stdout, stderr) as strings.
        Raises ToolNotFoundError, ToolExecutionError, or ToolTimeoutError.
        """
        binary = self._resolve_tool_path(self.TOOL_NAME)

        process = await asyncio.create_subprocess_exec(
            str(binary),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
        )

        try:
            stdin_bytes = input_data.encode() if input_data is not None else None
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin_bytes), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ToolTimeoutError(
                f"{self.TOOL_NAME} did not finish within {timeout}s"
            )

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        if process.returncode != 0:
            raise ToolExecutionError(self.TOOL_NAME, process.returncode, stderr)

        return stdout, stderr

    @abstractmethod
    async def run(self, targets: list[str], **kwargs) -> list[dict]:
        """
        Run this tool against the given targets and return normalized results.

        Contract: every subclass takes a flat list of target strings (hosts,
        domains, IPs — whatever this tool operates on) and returns a list of
        plain dicts, one per relevant finding, each containing at minimum a
        "subdomain" key matching one of the input targets. This is the shape
        ToolManager expects so it can persist any tool's output generically.

        Tools are pure: no storage, no I/O beyond running the binary. Fetching
        input and persisting output is ToolManager's job, not the tool's.
        """
        ...