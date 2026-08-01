"""Abstract base class and error types for external binary tool wrappers."""
import asyncio
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from core.errors import ToolExecutionError, ToolNotFoundError, ToolTimeoutError


class Tool(ABC):
    """
    Generic abstract base class for SubX external tool wrappers.

    Resolution strategy (applied on both Windows and Linux/macOS):
      1. Bundled binary at BASE_DIR/bin/<name>/<name>[.exe]
      2. System PATH via shutil.which
      3. Common Go / local install directories (Linux/macOS only):
         ~/go/bin, ~/.local/bin, /usr/local/bin

    Each candidate is validated via _validate_tool_path() so subclasses
    can reject name-colliding binaries.  The first candidate that passes
    validation wins; the result is cached for the lifetime of the instance.

    Subclasses must set TOOL_NAME and implement run().
    """

    BASE_DIR = Path(__file__).resolve().parent.parent

    # Subclasses override this with the actual binary name
    TOOL_NAME: str = ""

    # Cached after the first successful resolution
    _resolved_path: Path | None = None

    @staticmethod
    def _is_windows() -> bool:
        return sys.platform == "win32"

    def _resolve_tool_path(self, name: str) -> Path:
        """
        Resolve the path to a tool binary.

        Candidate sources (checked in order):
          1. Bundled binary at BASE_DIR/bin/<name>/<name>[.exe]
          2. System PATH via shutil.which
          3. Common Go / local install directories (Linux/macOS only)

        Each candidate is validated via _validate_tool_path(); if a candidate
        is rejected (e.g. it's the Python ``httpx`` CLI rather than
        ProjectDiscovery's Go binary) the search continues with the next one.

        The validated path is cached so subsequent calls skip re-resolution.

        Raises ToolNotFoundError if no valid binary can be found.
        """
        if self._resolved_path is not None:
            return self._resolved_path

        candidates: list[Path] = []

        # 1. Bundled binary (works on every OS; .exe suffix on Windows)
        ext = ".exe" if self._is_windows() else ""
        bundled = self.BASE_DIR / "bin" / name / f"{name}{ext}"
        if bundled.is_file():
            candidates.append(bundled)

        # 2. System PATH
        on_path = shutil.which(name)
        if on_path:
            p = Path(on_path)
            if p not in candidates:
                candidates.append(p)

        # 3. Common install directories (go install, pipx, local)
        if not self._is_windows():
            home = Path.home()
            for extra_dir in (
                home / "go" / "bin",
                home / ".local" / "bin",
                Path("/usr/local/bin"),
            ):
                extra = extra_dir / name
                if extra.is_file() and extra not in candidates:
                    candidates.append(extra)

        # Try each candidate; skip those that fail validation
        last_error: ToolNotFoundError | None = None
        for candidate in candidates:
            try:
                self._validate_tool_path(candidate)
                self._resolved_path = candidate
                return candidate
            except ToolNotFoundError as e:
                last_error = e
                continue

        if last_error is not None:
            # We found binaries but none passed validation
            raise last_error

        raise ToolNotFoundError(
            f"Could not locate '{name}'. Checked bundled path '{bundled}', "
            f"system PATH, and common install directories. "
            f"Install it via `go install` or apt."
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
