"""CLI command for HTTP probing stored subdomains."""

import typer

from core.cmd.base import Command
from core.services.export_service import ExportService
from core.services.probe_service import ProbeService
from core.tool import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from core.ui.console import console, error, info, warn
from core.ui.renderers import render_http_probe_summary


class ProbeCommand(Command):
    """Subdomain HTTP liveness probing CLI command."""

    name = "http-probe"
    help = "[bold cyan]Probe stored subdomains[/bold cyan] for liveness using httpx."

    # pylint: disable=arguments-differ
    def callback(
        self,
        domain: str = typer.Option(
            ...,
            "-d",
            "--domain",
            help="Target domain to probe stored subdomains for.",
        ),
        output_n: str | None = typer.Option(
            None, "-oN", help="Save alive subdomains to file (one per line)."
        ),
        output_x: str | None = typer.Option(
            None,
            "-oX",
            help=(
                "Save alive subdomains to file with custom separator. "
                "Use -oX '<sep>:<file>'."
            ),
        ),
        output_tech: str | None = typer.Option(
            None,
            "-oT",
            "--output-tech",
            help="Save alive subdomains with detected technologies to file.",
        ),
        export_project: str | None = typer.Option(
            None,
            "--project",
            "-p",
            help="Export/sync plain-text project directory structure after probing. Optionally specify output directory name (default: 'projects').",
        ),
    ) -> None:
        self.run_async(self._http_probe(domain, output_n, output_x, output_tech, export_project))

    async def _http_probe(
        self,
        domain: str,
        output_n: str | None,
        output_x: str | None,
        output_tech: str | None,
        export_project: str | None,
    ) -> None:
        self.show_banner()
        self.setup_logging()

        info(f"Target : [bold white]{domain}[/bold white]")
        console.print()

        service = ProbeService()

        try:
            with console.status(
                f"[cyan]Probing {domain}...[/cyan]", spinner="dots"
            ):
                results, rows = await service.probe_domain(domain)
        except ToolNotFoundError:
            error(
                "httpx binary not found. "
                "Install it (go install / apt) or check your bin/ path."
            )
        except ToolTimeoutError:
            error(
                f"httpx timed out while probing {domain}. "
                "Try again or raise the timeout."
            )
        except ToolExecutionError as e:
            error(f"httpx failed: {e}")

        if not results:
            console.print(
                f"[dim]  No subdomains stored for[/dim] "
                f"[bold white]{domain}[/bold white] "
                f"[dim]— run `subx enum` first.[/dim]\n"
            )
            return

        console.print()
        render_http_probe_summary(rows, domain)

        if output_n or output_x or output_tech:
            alive_rows = [row for row in rows if row.alive is True]
            if not alive_rows:
                warn("No alive subdomains to write.")
            else:
                alive_subs = [r.subdomain for r in alive_rows]
                if output_n:
                    ExportService.write_output(
                        alive_subs, output_n, separator="\n"
                    )
                if output_x:
                    sep, file = ExportService.parse_ox(output_x)
                    ExportService.write_output(alive_subs, file, separator=sep)
                if output_tech:
                    from core.ui.renderers import _format_tech
                    tech_lines = [
                        f"{r.subdomain} [{_format_tech(getattr(r, 'tech', None))}]"
                        for r in alive_rows
                    ]
                    ExportService.write_output(tech_lines, output_tech, separator="\n")

        if export_project is not None:
            from core.services.project_service import ProjectService
            from core.ui.renderers import render_project_summary
            out_dir = export_project if export_project else "projects"
            proj_service = ProjectService()
            summary = await proj_service.export_project(domain, out_dir=out_dir)
            render_project_summary(summary)
