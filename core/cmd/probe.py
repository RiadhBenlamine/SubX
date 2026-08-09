"""CLI commands for HTTP and DNS probing of stored subdomains."""

import typer

from core.cmd.base import Command
from core.services.export_service import ExportService
from core.services.probe_service import ProbeService
from core.tool import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from core.ui.console import console, error, info, warn


class ProbeCommand(Command):
    """Base class for subdomain probing commands.

    Subclasses must set:
        - name, help          (CLI registration)
        - tool_name           (e.g. "httpx", "dnsx")
        - status_verb         (e.g. "Probing", "DNS resolving")
        - _run_probe()        (call the appropriate ProbeService method)
        - _render()           (display results)
        - _export_outputs()   (write filtered rows to files)
    """

    tool_name: str = ""
    status_verb: str = ""

    # ── shared helpers ──────────────────────────────────────────

    def _show_header(self, domain: str) -> None:
        self.show_banner()
        self.setup_logging()
        info(f"Target : [bold white]{domain}[/bold white]")
        console.print()

    def _load_tool_config(self) -> dict | None:
        from core.config_manager import ConfigManager
        return ConfigManager.load_tool_config(self.tool_name)

    async def _probe(self, domain: str, **kwargs) -> None:
        """Common probe flow: load config → run tool → render → export."""
        self._show_header(domain)

        tool_config = self._load_tool_config()
        service = ProbeService()

        try:
            with console.status(
                f"[cyan]{self.status_verb} {domain}...[/cyan]", spinner="dots"
            ):
                results, rows = await self._run_probe(
                    service, domain, tool_config
                )
        except ToolNotFoundError:
            error(
                f"{self.tool_name} binary not found. "
                "Install it (go install / apt) or check your bin/ path."
            )
        except ToolTimeoutError:
            error(
                f"{self.tool_name} timed out while probing {domain}. "
                "Try again or raise the timeout."
            )
        except ToolExecutionError as e:
            error(f"{self.tool_name} failed: {e}")

        if not results:
            console.print(
                f"[dim]  No subdomains stored for[/dim] "
                f"[bold white]{domain}[/bold white] "
                f"[dim]— run `subx enum` first.[/dim]\n"
            )
            return

        console.print()
        self._render(rows, domain)
        self._export_outputs(rows, **kwargs)
        await self._maybe_export_project(domain, kwargs.get("export_project"))

    # ── methods subclasses must override ────────────────────────

    async def _run_probe(self, service, domain, tool_config):
        """Execute the appropriate probe and return (results, rows)."""
        raise NotImplementedError

    def _render(self, rows, domain):
        """Print the probe-specific results table + summary panel."""
        raise NotImplementedError

    def _export_outputs(self, rows, **kwargs):
        """Write filtered rows to output files when requested."""
        raise NotImplementedError

    # ── shared project export ───────────────────────────────────

    @staticmethod
    async def _maybe_export_project(domain: str, export_project: str | None) -> None:
        if export_project is not None:
            from core.services.project_service import ProjectService
            from core.ui.renderers import render_project_summary
            out_dir = export_project if export_project else "projects"
            proj_service = ProjectService()
            summary = await proj_service.export_project(domain, out_dir=out_dir)
            render_project_summary(summary)


# ════════════════════════════════════════════════════════════════
#  HTTP Probe  (httpx)
# ════════════════════════════════════════════════════════════════

class HttpProbeCommand(ProbeCommand):
    """Subdomain HTTP liveness probing CLI command."""

    name = "http-probe"
    help = "[bold cyan]Probe stored subdomains[/bold cyan] for liveness using httpx."
    tool_name = "httpx"
    status_verb = "Probing"

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
        self.run_async(self._probe(
            domain,
            output_n=output_n,
            output_x=output_x,
            output_tech=output_tech,
            export_project=export_project,
        ))

    async def _run_probe(self, service, domain, tool_config):
        from core.config_manager import ConfigManager

        dnsx_cfg = ConfigManager.load_tool_config("dnsx")
        resolved_hosts = None

        # If dnsx is configured, resolve first so httpx only probes alive hosts
        if dnsx_cfg is not None:
            info("[dim]dnsx configured — resolving subdomains first…[/dim]")
            dns_results, _ = await service.dns_probe_domain(
                domain, tool_config=dnsx_cfg
            )
            if dns_results:
                resolved_hosts = [
                    r["subdomain"] for r in dns_results if r.get("ip")
                ]
                info(
                    f"[dim]dnsx resolved [bold white]{len(resolved_hosts)}[/bold white] "
                    f"of {len(dns_results)} subdomains — probing only resolved.[/dim]"
                )
            console.print()

        return await service.probe_domain(
            domain, tool_config=tool_config, hosts=resolved_hosts
        )

    def _render(self, rows, domain):
        from core.ui.renderers import render_http_probe_summary
        render_http_probe_summary(rows, domain)

    def _export_outputs(self, rows, **kwargs):
        output_n = kwargs.get("output_n")
        output_x = kwargs.get("output_x")
        output_tech = kwargs.get("output_tech")

        if not (output_n or output_x or output_tech):
            return

        alive_rows = [row for row in rows if row.alive is True]
        if not alive_rows:
            warn("No alive subdomains to write.")
            return

        alive_subs = [r.subdomain for r in alive_rows]
        if output_n:
            ExportService.write_output(alive_subs, output_n, separator="\n")
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


# ════════════════════════════════════════════════════════════════
#  DNS Probe  (dnsx)
# ════════════════════════════════════════════════════════════════

class DnsProbeCommand(ProbeCommand):
    """Subdomain DNS resolution probing CLI command."""

    name = "dns-probe"
    help = "[bold cyan]Probe stored subdomains[/bold cyan] for DNS resolution using dnsx."
    tool_name = "dnsx"
    status_verb = "DNS resolving"

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
            None, "-oN", help="Save resolved subdomains to file (one per line)."
        ),
        output_x: str | None = typer.Option(
            None,
            "-oX",
            help=(
                "Save resolved subdomains to file with custom separator. "
                "Use -oX '<sep>:<file>'."
            ),
        ),
        output_ip: str | None = typer.Option(
            None,
            "-oI",
            "--output-ip",
            help="Save resolved subdomains with IP addresses to file.",
        ),
        export_project: str | None = typer.Option(
            None,
            "--project",
            "-p",
            help="Export/sync plain-text project directory structure after probing. Optionally specify output directory name (default: 'projects').",
        ),
    ) -> None:
        self.run_async(self._probe(
            domain,
            output_n=output_n,
            output_x=output_x,
            output_ip=output_ip,
            export_project=export_project,
        ))

    async def _run_probe(self, service, domain, tool_config):
        return await service.dns_probe_domain(domain, tool_config=tool_config)

    def _render(self, rows, domain):
        from core.ui.renderers import render_dns_probe_summary
        render_dns_probe_summary(rows, domain)

    def _export_outputs(self, rows, **kwargs):
        output_n = kwargs.get("output_n")
        output_x = kwargs.get("output_x")
        output_ip = kwargs.get("output_ip")

        if not (output_n or output_x or output_ip):
            return

        resolved_rows = [row for row in rows if getattr(row, "ip", None)]
        if not resolved_rows:
            warn("No resolved subdomains to write.")
            return

        resolved_subs = [r.subdomain for r in resolved_rows]
        if output_n:
            ExportService.write_output(resolved_subs, output_n, separator="\n")
        if output_x:
            sep, file = ExportService.parse_ox(output_x)
            ExportService.write_output(resolved_subs, file, separator=sep)
        if output_ip:
            ip_lines = [
                f"{r.subdomain} [{r.ip}]"
                for r in resolved_rows
            ]
            ExportService.write_output(ip_lines, output_ip, separator="\n")
