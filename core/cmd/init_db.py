"""CLI command for initializing PostgreSQL database and setting it as default."""
from pathlib import Path
import typer
import yaml
from rich.panel import Panel
from rich.table import Table

from core.cmd.base import Command
from core.storage_manager import StorageManager
from core.ui.console import console


class InitDbCommand(Command):
    """Command to initialize PostgreSQL database and set PostgreSQL as default for SubX."""

    name = "setup"
    help = "[bold green]Initialize PostgreSQL database ('subx')[/bold green] and set PostgreSQL as default."

    def callback(
        self,
        host: str = typer.Option(
            None, "--host", "-H", help="PostgreSQL server IP / host (default: 127.0.0.1)"
        ),
        user: str = typer.Option(
            None, "--user", "-u", help="PostgreSQL username (default: postgres)"
        ),
        password: str = typer.Option(
            None, "--password", "-W", help="PostgreSQL password"
        ),
        port: int = typer.Option(
            5432, "--port", "-p", help="PostgreSQL port (default: 5432)"
        ),
        dbname: str = typer.Option(
            "subx", "--dbname", "-n", help="Target database name (default: subx)"
        ),
        non_interactive: bool = typer.Option(
            False, "--non-interactive", help="Skip interactive prompts"
        ),
    ) -> None:
        self.show_banner()
        self.setup_logging()
        self.run_async(
            self._run_init(
                host=host,
                user=user,
                password=password,
                port=port,
                dbname=dbname,
                non_interactive=non_interactive,
            )
        )

    async def _run_init(
        self,
        host: str | None,
        user: str | None,
        password: str | None,
        port: int,
        dbname: str,
        non_interactive: bool,
    ) -> None:
        if not non_interactive:
            if not host:
                host = typer.prompt("PostgreSQL Host / IP", default="127.0.0.1")
            if not user:
                user = typer.prompt("PostgreSQL Username", default="postgres")
            if password is None:
                password = typer.prompt("PostgreSQL Password", hide_input=True, default="")
        else:
            host = host or "127.0.0.1"
            user = user or "postgres"
            password = password or ""

        auth = f"{user}:{password}@" if password else f"{user}@"
        pg_url = f"postgresql+asyncpg://{auth}{host}:{port}/{dbname}"

        console.print(f"\n[cyan]⚙ Initializing PostgreSQL database on [bold]{host}:{port}[/bold]...[/cyan]")

        try:
            storage = StorageManager(pg_url)
            await storage.init()
            await storage.close()
        except Exception as e:
            console.print(f"[bold red]✘ PostgreSQL Database Initialization Failed:[/bold red] {e}")
            raise typer.Exit(code=1) from e

        # Save config globally to ~/.config/subx/config.yaml
        config_dir = Path.home() / ".config" / "subx"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"

        existing_data = {}
        if config_file.exists():
            try:
                with config_file.open("r", encoding="utf-8") as f:
                    existing_data = yaml.safe_load(f) or {}
            except Exception:
                existing_data = {}

        existing_data["db"] = {
            "host": host,
            "user": user,
            "password": password,
            "port": port,
            "dbname": dbname,
        }

        with config_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(existing_data, f, sort_keys=False)

        table = Table(title="PostgreSQL Default Configuration", show_header=False)
        table.add_column("Setting", style="bold cyan")
        table.add_column("Value", style="bold white")

        table.add_row("Status", "[bold green]Active & Connected[/bold green]")
        table.add_row("Engine", "PostgreSQL (asyncpg)")
        table.add_row("Server IP / Host", f"{host}:{port}")
        table.add_row("User", user)
        table.add_row("Database Name", dbname)
        table.add_row("Tables Created", "subx_subdomain, subx_subdomain_sources")
        table.add_row("Global Config", str(config_file))

        console.print()
        console.print(Panel(table, border_style="green"))
        console.print("\n[bold green]✔ PostgreSQL database successfully initialized and set as default for SubX![/bold green]\n")
