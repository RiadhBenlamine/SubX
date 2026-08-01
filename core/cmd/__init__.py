"""CLI command module and registering app commands."""
import typer

from core.cmd.base import HELP_NAMES
from core.cmd.db import DbCommand
from core.cmd.enum import EnumCommand
from core.cmd.import_sqlite import ImportSqliteCommand
from core.cmd.migrate import MigrateCommand
from core.cmd.probe import ProbeCommand
from core.cmd.project import ProjectCommand

app = typer.Typer(
    name="subx",
    help="[bold cyan]SUBX[/bold cyan] — Subdomain Recon Framework",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings=HELP_NAMES,
)

# Register all subcommands
EnumCommand().register(app)
DbCommand().register(app)
ProbeCommand().register(app)
ProjectCommand().register(app)
ImportSqliteCommand().register(app)
MigrateCommand().register(app)
