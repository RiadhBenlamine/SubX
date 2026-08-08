"""CLI ASCII banner display function and version/update checking."""
from importlib.metadata import PackageNotFoundError, version as get_pkg_version
import json
import re
import urllib.request

from rich.panel import Panel
from rich.text import Text

from core.ui.console import console


def get_version() -> str:
    """Retrieve installed subx-recon version dynamically or fallback."""
    try:
        ver = get_pkg_version("subx-recon")
        if ver:
            return ver
    except PackageNotFoundError:
        pass
    try:
        ver = get_pkg_version("subx")
        if ver:
            return ver
    except PackageNotFoundError:
        pass
    return "2.1.0"


def _is_newer_version(current: str, latest: str) -> bool:
    """Compare semver version strings to determine if latest > current."""
    try:
        def _parse(v: str):
            return tuple(int(x) for x in re.findall(r"\d+", v))
        return _parse(latest) > _parse(current)
    except Exception:
        return False


def banner(version_str: str | None = None) -> None:
    """Print the SUBX recon framework banner with version to the console."""
    ver = version_str or get_version()
    console.print(Panel.fit(
        Text.assemble(
            ("░██████╗██╗░░░██╗██████╗░██╗░░██╗\n", "bold cyan"),
            ("██╔════╝██║░░░██║██╔══██╗╚██╗██╔╝\n", "bold cyan"),
            ("╚█████╗░██║░░░██║██████╦╝░╚███╔╝░\n", "bold cyan"),
            ("░╚═══██╗██║░░░██║██╔══██╗░██╔██╗░\n", "bold cyan"),
            ("██████╔╝╚██████╔╝██████╦╝██╔╝╚██╗\n", "bold cyan"),
            ("╚═════╝░░╚═════╝░╚═════╝░╚═╝░░╚═╝\n", "bold cyan"),
            ("        subdomain recon framework  ", "dim white"),
            (f"v{ver}\n",                             "bold yellow"),
            ("                        by ",        "dim white"),
            ("rbn0x00",                             "bold cyan"),
        ),
        border_style="cyan",
        padding=(0, 2),
    ))


def check_for_updates() -> None:
    """Check PyPI for newer releases of subx-recon and display update banner if available."""
    current_ver = get_version()
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/subx-recon/json",
            headers={"User-Agent": "SubX-UpdateCheck"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                latest_ver = data.get("info", {}).get("version")
                if latest_ver and _is_newer_version(current_ver, latest_ver):
                    console.print(
                        Panel.fit(
                            f"[bold yellow]💡 Update available![/bold yellow] [dim]v{current_ver}[/dim] ➔ [bold green]v{latest_ver}[/bold green]\n"
                            f"[dim]Run [bold cyan]pip install --upgrade subx-recon[/bold cyan] to update.[/dim]",
                            border_style="yellow",
                            padding=(0, 2),
                        )
                    )
    except Exception:
        # Ignore network errors or timeouts silently
        pass
