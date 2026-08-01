"""Abstract base class and error types for external binary tool wrappers."""
import asyncio
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from core.errors import (
ToolNotFoundError,ToolExecutionError,ToolTimeoutError
)

class Tool(ABC):
    """
    Generic abstract base class for SubX external tool wrappers

    Resolution strategy:
      - Windows: BASE_DIR/bin/<name>/<name>.exe (bundled)
      - Linux/macOS: system PATH (installed via `go install` / apt)

    Subclasses must set TOOL_NAME and implement run().
    """

    BASE_DIR = Path(__file__).resolve().parent.parent

    # Subclasses override this with the actual binary name
    TOOL_NAME: str = ""

    @staticmethod
    def _get_os() -> str:
        return sys.platform

    def _resolve_tool_path(self, name: str) -> Path:
        """
        Resolve the path to a tool binary.

        Resolution order:
          1. Bundled binary at BASE_DIR/bin/<name>/<name>[.exe]  (any OS)
          2. System PATH lookup via shutil.which                  (fallback)

        After resolution the path is handed to _validate_tool_path() so
        subclasses can reject name-colliding binaries (e.g. the Python
        ``httpx`` CLI vs. ProjectDiscovery's Go ``httpx``).

        Raises ToolNotFoundError if no valid binary can be found.
        """
        # 1. Bundled binary (works on every OS; .exe suffix on Windows)
        ext = ".exe" if self._get_os() == "win32" else ""
        bundled = self.BASE_DIR / "bin" / name / f"{name}{ext}"
        if bundled.is_file():
            self._validate_tool_path(bundled)
            return bundled

        # 2. Fallback: system PATH
        on_path = shutil.which(name)
        if on_path:
            resolved = Path(on_path)
            self._validate_tool_path(resolved)
            return resolved

        raise ToolNotFoundError(
            f"Could not locate '{name}'. Checked bundled path '{bundled}' "
            f"and system PATH. Install it via `go install` or apt."
        )

    def _validate_tool_path(self, path: Path) -> None:
        """Optional hook for subclasses to reject an incorrect binary.

        Called by _resolve_tool_path after finding a candidate. Override in
        subclasses to inspect the binary (e.g. run ``<binary> -version``) and
        raise ToolNotFoundError if it is not the expected tool.

        The default implementation accepts any existing file.
        """

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
        except asyncio.TimeoutError as e:
            process.kill()
            await process.wait()
            raise ToolTimeoutError(
                f"{self.TOOL_NAME} did not finish within {timeout}s"
            ) from e

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
