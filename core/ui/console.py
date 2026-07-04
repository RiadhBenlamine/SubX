import typer
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()


def info(msg: str) -> None:
    console.print(f"[bold cyan]  ›[/bold cyan]  {msg}")


def success(msg: str) -> None:
    console.print(f"[bold green]  ✔[/bold green]  {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow]  ⚡[/bold yellow]  {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]  ✘[/bold red]  {msg}")
    raise typer.Exit(1)


def make_table(*columns: tuple[str, dict]) -> Table:
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
