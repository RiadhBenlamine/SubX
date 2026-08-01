"""CLI command for exporting target plain-text project directories."""

import typer

from core.cmd.base import Command
from core.services.project_service import ProjectService
from core.ui.console import console, error, info
from core.ui.renderers import render_project_summary


class ProjectCommand(Command):
    """Target project directory management CLI command."""

    name = "project"
    help = "[bold cyan]Set up & export project directory[/bold cyan] with plain-text recon files."

    # pylint: disable=arguments-differ
    def callback(
        self,
        domain: str = typer.Option(
            ...,
            "-d",
            "--domain",
            help="Target domain to create/sync project directory for.",
        ),
        out_dir: str = typer.Option(
            "projects",
            "-o",
            "--output-dir",
            help="Base output directory where project folder will be created.",
        ),
    ) -> None:
        self.run_async(self._project(domain, out_dir))

    async def _project(self, domain: str, out_dir: str) -> None:
        self.show_banner()
        self.setup_logging()

        info(f"Target      : [bold white]{domain}[/bold white]")
        info(f"Output Dir  : [bold white]{out_dir}/{domain}[/bold white]")
        console.print()

        service = ProjectService()

        try:
            with console.status(
                f"[cyan]Creating project structure for {domain}...[/cyan]", spinner="dots"
            ):
                summary = await service.export_project(domain, out_dir=out_dir)
        except Exception as e:  # pylint: disable=broad-exception-caught
            error(f"Failed to export project structure: {e}")
            return

        render_project_summary(summary)
