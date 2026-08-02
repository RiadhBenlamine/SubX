"""CLI command for subdomain enumeration."""
import typer

from core.cmd.base import Command
from core.logger import get_dedup_handler
from core.services.enum_service import EnumService
from core.ui.console import console, error, info
from core.ui.renderers import render_enum_results


class EnumCommand(Command):
    """Subdomain enumeration CLI command."""

    name = "enum"
    help = "[bold cyan]Enumerate subdomains[/bold cyan] for target domain(s)."

    # pylint: disable=arguments-differ
    def callback(
        self,
        config_file: str = typer.Option(
            ..., "-c", "--config", help="Path to YAML/JSON config file."
        ),
        save: bool = typer.Option(
            True, "--save/--no-save", help="Save results to database."
        ),
        export_project: str | None = typer.Option(
            None, "--project", "-p", help="Export plain-text project directory structure after enumeration. Optionally specify output directory name (default: 'projects')."
        ),
    ) -> None:
        self.run_async(self._enum(config_file, save, export_project))

    async def _enum(self, config_file: str, save: bool, export_project: str | None) -> None:
        self.show_banner()
        self.setup_logging()

        service = EnumService()

        try:
            with console.status(
                "[cyan]Running passive engines...[/cyan]", spinner="dots"
            ):
                result = await service.run(config_file, save)
        except (FileNotFoundError, ValueError) as e:
            error(str(e))
        except RuntimeError as e:
            error(str(e))
        except Exception as e:  # pylint: disable=broad-exception-caught
            error(f"Failed to load config: {e}")

        # Display scope info
        info(f"Scope   : [bold white]{', '.join(result.scope)}[/bold white]")
        if result.out_of_scope:
            info(
                f"OOS     : [bold white]{', '.join(result.out_of_scope)}[/bold white]"
            )
        if result.sources:
            info(
                f"Sources : [bold white]{', '.join(result.sources)}[/bold white]"
            )
        console.print()
        info(f"Plugins : [bold white]{', '.join(result.plugin_names)}[/bold white]")
        console.print()

        render_enum_results(result.processed_by_target, save)

        if export_project is not None and save:
            from core.services.project_service import ProjectService
            from core.ui.renderers import render_project_summary
            out_dir = export_project if export_project else "projects"
            proj_service = ProjectService()
            for target in result.scope:
                summary = await proj_service.export_project(target, out_dir=out_dir)
                render_project_summary(summary)

        # ── Error summary (deduplicated) ────────────────────────
        self._print_error_summary()

    @staticmethod
    def _print_error_summary() -> None:
        """Print a compact summary of repeated errors and point to the log file."""
        handler = get_dedup_handler()
        if handler is None:
            return

        repeated = handler.get_counts()
        if not repeated:
            return

        console.print()
        console.print("[bold yellow]  ⚡  Some errors were suppressed (duplicates):[/bold yellow]")
        for key, count in repeated.items():
            # key format is "LoggerName|level|message"
            parts = key.split("|", 2)
            msg = parts[2] if len(parts) == 3 else key
            console.print(f"[dim]      × {count}  {msg}[/dim]")

        from core.logger import _LOG_FILE
        console.print(
            f"\n[dim]  Full error log → [bold]{_LOG_FILE}[/bold][/dim]"
        )
