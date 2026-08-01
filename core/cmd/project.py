from pathlib import Path
import typer

from core.cmd.base import Command
from core.config_manager import ConfigManager
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
        domain: str | None = typer.Option(
            None,
            "-d",
            "--domain",
            help="Target domain to create/sync project directory for (optional if config file is used).",
        ),
        config_path: str = typer.Option(
            "config.yaml",
            "-c",
            "--config",
            help="Path to YAML/JSON config file (used when --domain is omitted).",
        ),
        out_dir: str = typer.Option(
            "projects",
            "-o",
            "--output-dir",
            help="Base output directory where project folder will be created.",
        ),
    ) -> None:
        self.run_async(self._project(domain, config_path, out_dir))

    async def _project(self, domain: str | None, config_path: str, out_dir: str) -> None:
        self.show_banner()
        self.setup_logging()

        domains: list[str] = []
        if domain:
            domains = [domain]
        else:
            cfg_file = Path(config_path)
            if not cfg_file.exists():
                error(f"No domain specified via '-d' and config file not found: '{config_path}'")
                info("Specify a target domain with '-d <domain>' or provide a valid config file with '-c <path>'.")
                return
            try:
                cfg = ConfigManager(config_path)
                domains = cfg.get_scope()
            except Exception as e:
                error(f"Failed to load target domains from config file '{config_path}': {e}")
                return

        if not domains:
            error("No target domains found to process.")
            return

        info(f"Target Domains : [bold white]{', '.join(domains)}[/bold white]")
        info(f"Output Dir     : [bold white]{out_dir}/[/bold white]")
        console.print()

        service = ProjectService()

        for d in domains:
            try:
                with console.status(
                    f"[cyan]Syncing project structure for {d}...[/cyan]", spinner="dots"
                ):
                    summary = await service.export_project(d, out_dir=out_dir)
                render_project_summary(summary)
            except Exception as e:  # pylint: disable=broad-exception-caught
                error(f"Failed to export project structure for {d}: {e}")
