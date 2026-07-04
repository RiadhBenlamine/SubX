from rich.panel import Panel
from rich.text import Text

from core.ui.console import console


def banner() -> None:
    console.print(Panel.fit(
        Text.assemble(
            ("░██████╗██╗░░░██╗██████╗░██╗░░██╗\n", "bold cyan"),
            ("██╔════╝██║░░░██║██╔══██╗╚██╗██╔╝\n", "bold cyan"),
            ("╚█████╗░██║░░░██║██████╦╝░╚███╔╝░\n", "bold cyan"),
            ("░╚═══██╗██║░░░██║██╔══██╗░██╔██╗░\n", "bold cyan"),
            ("██████╔╝╚██████╔╝██████╦╝██╔╝╚██╗\n", "bold cyan"),
            ("╚═════╝░░╚═════╝░╚═════╝░╚═╝░░╚═╝\n", "bold cyan"),
            ("        subdomain recon framework  ", "dim white"),
            ("\n                        by ",        "dim white"),
            ("rbn0x00",                             "bold cyan"),
        ),
        border_style="cyan",
        padding=(0, 2),
    ))
