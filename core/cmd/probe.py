from typing import Optional
import typer
from core.cmd.base import Command
from core.services.export_service import ExportService
from core.services.probe_service import ProbeService
from core.tool import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from core.ui.console import console, info, warn, error
from core.ui.renderers import render_http_probe_summary

class ProbeCommand(Command):
    name = "http-probe"
    help = "[bold cyan]Probe stored subdomains[/bold cyan] for liveness using httpx."

    def callback(
        self,
        domain: str            = typer.Option(..., "-d", "--domain", help="Target domain to probe stored subdomains for."),
        output_n: Optional[str] = typer.Option(None, "-oN", help="Save alive subdomains to file (one per line)."),
        output_x: Optional[str] = typer.Option(None, "-oX", help="Save alive subdomains to file with custom separator. Use -oX '<sep>:<file>'."),
    ) -> None:
        self.run_async(self._http_probe(domain, output_n, output_x))

    async def _http_probe(self, domain: str, output_n: Optional[str], output_x: Optional[str]) -> None:
        self.show_banner()
        self.setup_logging()

        info(f"Target : [bold white]{domain}[/bold white]")
        console.print()

        service = ProbeService()

        try:
            with console.status(f"[cyan]Probing {domain}...[/cyan]", spinner="dots"):
                results, rows = await service.probe_domain(domain)
        except ToolNotFoundError:
            error("httpx binary not found. Install it (go install / apt) or check your bin/ path.")
            return
        except ToolTimeoutError:
            error(f"httpx timed out while probing {domain}. Try again or raise the timeout.")
            return
        except ToolExecutionError as e:
            error(f"httpx failed: {e}")
            return

        if not results:
            console.print(f"[dim]  No subdomains stored for[/dim] [bold white]{domain}[/bold white] [dim]— run `subx enum` first.[/dim]\n")
            return

        console.print()
        render_http_probe_summary(rows, domain)

        if output_n or output_x:
            alive_subs = [row.subdomain for row in rows if row.alive is True]
            if not alive_subs:
                warn("No alive subdomains to write.")
            else:
                if output_n:
                    ExportService.write_output(alive_subs, output_n, separator="\n")
                if output_x:
                    sep, file = ExportService.parse_ox(output_x)
                    ExportService.write_output(alive_subs, file, separator=sep)
