"""CLI command for database schema migrations."""
import typer

from core.cmd.base import Command
from core.services.migrate_service import MigrateService
from core.ui.console import console, error, info, success


class MigrateCommand(Command):
    """Database schema migration CLI command."""

    name = "migrate"
    help = "Safely migrate the database schema to match the current models."

    # pylint: disable=arguments-differ
    def callback(
        self,
        no_backup: bool = typer.Option(
            False,
            "--no-backup",
            help="Skip creating a backup before migrating.",
        ),
    ) -> None:
        self.run_async(self._db_migrate(backup=not no_backup))

    async def _db_migrate(self, backup: bool) -> None:
        self.show_banner()

        service = MigrateService()

        try:
            added = await service.migrate(backup=backup)
        except Exception as e:  # pylint: disable=broad-exception-caught
            error(f"Migration failed: {e}")

        if added:
            success(
                f"Migration complete — added "
                f"[bold white]{len(added)}[/bold white] column(s):"
            )
            for col in added:
                console.print(f"  [dim]•[/dim]  [bold white]{col}[/bold white]")
        else:
            info("Database schema is already up to date. No changes needed.")

        console.print()
