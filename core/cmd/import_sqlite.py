"""CLI command for importing SQLite database files into PostgreSQL or active DB."""

import typer

from core.cmd.base import Command
from core.services.import_service import ImportService
from core.ui.console import console, error, info
from core.ui.renderers import render_import_summary


class ImportSqliteCommand(Command):
    """SQLite to PostgreSQL database migration CLI command."""

    name = "import"
    help = "[bold cyan]Import SQLite database[/bold cyan] into PostgreSQL or active target DB engine."

    # pylint: disable=arguments-differ
    def callback(
        self,
        sqlite_file: str = typer.Argument(
            ...,
            help="Path to source SQLite database file (e.g. subx.db).",
        ),
        target_db_url: str | None = typer.Option(
            None,
            "--target-db-url",
            "-t",
            help="Target database URL (e.g. postgresql+asyncpg://user:pass@localhost:5432/subx). Omit to use active DATABASE_URL.",
        ),
    ) -> None:
        self.run_async(self._import(sqlite_file, target_db_url))

    async def _import(self, sqlite_file: str, target_db_url: str | None) -> None:
        self.show_banner()
        self.setup_logging()

        info(f"Source SQLite : [bold white]{sqlite_file}[/bold white]")
        if target_db_url:
            info(f"Target DB URL : [bold white]{target_db_url}[/bold white]")
        console.print()

        service = ImportService()

        try:
            with console.status(
                "[cyan]Importing SQLite database into target database...[/cyan]",
                spinner="dots",
            ):
                summary = await service.import_sqlite(sqlite_file, target_db_url=target_db_url)
        except FileNotFoundError as e:
            error(str(e))
        except Exception as e:  # pylint: disable=broad-exception-caught
            error(f"Failed to import database: {e}")

        render_import_summary(summary)
