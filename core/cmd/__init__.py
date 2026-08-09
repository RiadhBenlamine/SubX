"""CLI command module and registering app commands."""
import typer

from core.cmd.base import HELP_NAMES
from core.cmd.db import DbCommand
from core.cmd.enum import EnumCommand
from core.cmd.import_sqlite import ImportSqliteCommand
from core.cmd.init_db import InitDbCommand
from core.cmd.migrate import MigrateCommand
from core.cmd.probe import DnsProbeCommand, HttpProbeCommand
from core.cmd.project import ProjectCommand

app = typer.Typer(
    name="subx",
    help="[bold cyan]SUBX[/bold cyan] — Subdomain Recon Framework",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings=HELP_NAMES,
)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version_flag: bool = typer.Option(
        False,
        "-v",
        "--version",
        help="Show SubX version and exit.",
        is_eager=True,
    ),
) -> None:
    """SUBX — Subdomain Reconnaissance & Asset Management Framework."""
    from core.ui.banner import banner, check_for_updates, get_version
    from core.ui.console import console

    if version_flag:
        console.print(f"[bold cyan]subx-recon[/bold cyan] v[bold yellow]{get_version()}[/bold yellow]")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        banner()
        check_for_updates()


# Register all subcommands
InitDbCommand().register(app)
EnumCommand().register(app)
DbCommand().register(app)
HttpProbeCommand().register(app)
DnsProbeCommand().register(app)
ProjectCommand().register(app)
ImportSqliteCommand().register(app)
MigrateCommand().register(app)

