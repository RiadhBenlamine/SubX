"""Console utilities and helpers for output formatting."""
from typing import NoReturn

import typer
from rich import box
from rich.console import Console
from rich.table import Table

console = Console(force_terminal=True)


def info(msg: str) -> None:
    """Print an informational message with a cyan indicator."""
    console.print(f"[bold cyan]  ›[/bold cyan]  {msg}")


def success(msg: str) -> None:
    """Print a success message with a green checkmark."""
    console.print(f"[bold green]  ✔[/bold green]  {msg}")


def warn(msg: str) -> None:
    """Print a warning message with a yellow thunderbolt."""
    console.print(f"[bold yellow]  ⚡[/bold yellow]  {msg}")


def error(msg: str) -> NoReturn:
    """Print an error message and exit the application."""
    console.print(f"[bold red]  ✘[/bold red]  {msg}")
    raise typer.Exit(1)


def make_table(*columns: tuple[str, dict]) -> Table:
    """Create a formatted table container configured with clean styles."""
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 2),
    )
    for header, kwargs in columns:
        table.add_column(header, **kwargs)
    return table
