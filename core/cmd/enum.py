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
        debug: bool = typer.Option(
            False, "--debug", "--verbose", help="Enable verbose debug logging."
        ),
    ) -> None:
        self.run_async(self._enum(config_file, save, export_project, debug))

    async def _enum(self, config_file: str, save: bool, export_project: str | None, debug: bool) -> None:
        self.show_banner()
        self.setup_logging(debug=debug)

        service = EnumService()

        try:
            result = await self._run_with_live_display(service, config_file, save)
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

        if result.probe_results_by_target:
            from core.ui.renderers import render_http_probe_summary
            console.print()
            info("[bold cyan]Pipeline Execution: Automatic Probing (httpx)[/bold cyan]")
            console.print()
            for domain, (_, probe_rows) in result.probe_results_by_target.items():
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
    async def _run_with_live_display(service, config_file, save):
        """Run enumeration with a real-time live subdomain streaming display."""
        import time

        from rich.console import Group
        from rich.live import Live
        from rich.rule import Rule
        from rich.text import Text

        # ── State shared between callbacks ──────────────────────
        seen_subs: set[str] = set()
        seen_domains: set[str] = set()
        lines: list[Text] = []
        status_text = Text("Initializing...", style="bold cyan")
        start_time = time.monotonic()

        def _build_renderable():
            """Compose the full renderable: streamed lines + sticky status bar."""
            parts = list(lines)
            elapsed = time.monotonic() - start_time
            bar = Text()
            bar.append("  ⏱ ", style="dim")
            bar.append(f"{elapsed:.1f}s", style="bold white")
            bar.append("  │  ", style="dim")
            bar.append(f"{len(seen_subs)}", style="bold green")
            bar.append(" unique", style="dim")
            bar.append("  │  ", style="dim")
            bar.append_text(status_text)
            parts.append(Text())
            parts.append(Rule(style="cyan"))
            parts.append(bar)
            return Group(*parts)

        live = Live(
            _build_renderable(),
            console=console,
            refresh_per_second=12,
            transient=False,
        )

        def _on_progress(completed: int, total: int, desc: str) -> None:
            nonlocal status_text
            pct = int(completed / total * 100) if total else 0
            status_text = Text()
            status_text.append(f"[{completed}/{total}] ", style="bold white")
            status_text.append(f"{pct}% ", style="bold cyan")
            status_text.append(desc, style="dim white")
            live.update(_build_renderable())

        def _on_subdomain(plugin_name: str, subdomains: list[str]) -> None:
            """Track unique subdomains for live count without flooding terminal lines."""
            for sub in subdomains:
                sub_lower = sub.strip().lower()
                seen_subs.add(sub_lower)
            live.update(_build_renderable())

        def _on_domain_started(domain: str) -> None:
            """Print a target domain header when enumeration begins."""
            if domain in seen_domains:
                return
            seen_domains.add(domain)
            header = Text()
            header.append(f"\n  ─── {domain} ", style="bold cyan")
            header.append("─" * max(1, 50 - len(domain)), style="cyan")
            lines.append(header)
            live.update(_build_renderable())

        with live:
            return await service.run(
                config_file,
                save,
                progress_cb=_on_progress,
                subdomain_cb=_on_subdomain,
                domain_started_cb=_on_domain_started,
            )

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
