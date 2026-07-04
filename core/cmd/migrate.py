import asyncio

import typer

from core.services.migrate_service import MigrateService
from core.ui.banner import banner
from core.ui.console import console, info, success, error

HELP_NAMES = {"help_option_names": ["-h", "--help"]}


def register(app: typer.Typer) -> None:
    """Register the dev-migrate command on the given Typer app."""
    app.command("dev-migrate", context_settings=HELP_NAMES)(db_migrate)


def db_migrate(
    no_backup: bool = typer.Option(False, "--no-backup", help="Skip creating a backup before migrating."),
) -> None:
    """
    [bold cyan]Safely migrate the database schema[/bold cyan] to match the current models.


    Adds any new columns that exist in the code but are missing from the DB.
    A timestamped backup of the database file is created before any changes.

    Examples:
      subx dev-migrate                 # migrate with backup
      subx dev-migrate --no-backup     # migrate without backup
    """
    asyncio.run(_db_migrate(backup=not no_backup))


async def _db_migrate(backup: bool) -> None:
    banner()

    service = MigrateService()

    try:
        added = await service.migrate(backup=backup)
    except Exception as e:
        error(f"Migration failed: {e}")

    if added:
        success(f"Migration complete — added [bold white]{len(added)}[/bold white] column(s):")
        for col in added:
            console.print(f"  [dim]•[/dim]  [bold white]{col}[/bold white]")
    else:
        info("Database schema is already up to date. No changes needed.")

    console.print()
