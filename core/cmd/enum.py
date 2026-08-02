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
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TaskProgressColumn,
                TextColumn,
                TimeElapsedColumn,
            )

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}[/bold cyan]"),
                BarColumn(bar_width=35, style="cyan", complete_style="bold cyan"),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            )

            with progress:
                task_id = progress.add_task("Running passive engines...", total=100)

                def _on_progress(completed: int, total: int, desc: str) -> None:
                    progress.update(
                        task_id,
                        completed=completed,
                        total=total,
                        description=f"Running passive engines ({desc})" if desc else "Running passive engines...",
                    )

                result = await service.run(config_file, save, progress_cb=_on_progress)
        except (FileNotFoundError, ValueError) as e:
            error(str(e))
            return
        except RuntimeError as e:
            error(str(e))
            return
        except Exception as e:  # pylint: disable=broad-exception-caught
            error(f"Failed to load config: {e}")
            return

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

        if result.probe_results_by_target:
            from core.ui.renderers import render_http_probe_summary
            console.print()
            info("[bold cyan]Pipeline Execution: Automatic Probing (httpx)[/bold cyan]")
            console.print()
            for domain, (probe_res, probe_rows) in result.probe_results_by_target.items():
                if probe_rows:
                    render_http_probe_summary(probe_rows, domain)

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
