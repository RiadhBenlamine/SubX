import typer

from core.cmd import db, enum, migrate, probe

HELP_NAMES = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    name="subx",
    help="[bold cyan]SUBX[/bold cyan] — Subdomain Recon Framework",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings=HELP_NAMES,
)

# Register all subcommands
enum.register(app)
db.register(app)
probe.register(app)
migrate.register(app)
