import typer
from core.cmd.base import Command
from core.services.enum_service import EnumService
from core.ui.console import console, info, error
from core.ui.renderers import render_enum_results

class EnumCommand(Command):
    name = "enum"
    help = "[bold cyan]Enumerate subdomains[/bold cyan] for target domain(s)."

    def callback(
        self,
        config_file: str = typer.Option(..., "-c", "--config", help="Path to YAML/JSON config file."),
        save: bool       = typer.Option(True, "--save/--no-save", help="Save results to database."),
    ) -> None:
        self.run_async(self._enum(config_file, save))

    async def _enum(self, config_file: str, save: bool) -> None:
        self.show_banner()
        self.setup_logging()

        service = EnumService()

        try:
            with console.status("[cyan]Running passive engines...[/cyan]", spinner="dots"):
                result = await service.run(config_file, save)
        except (FileNotFoundError, ValueError) as e:
            error(str(e))
            return
        except RuntimeError as e:
            error(str(e))
            return
        except Exception as e:
            error(f"Failed to load config: {e}")
            return

        # Display scope info
        info(f"Scope   : [bold white]{', '.join(result.scope)}[/bold white]")
        if result.out_of_scope:
            info(f"OOS     : [bold white]{', '.join(result.out_of_scope)}[/bold white]")
        if result.sources:
            info(f"Sources : [bold white]{', '.join(result.sources)}[/bold white]")
        console.print()
        info(f"Plugins : [bold white]{', '.join(result.plugin_names)}[/bold white]")
        console.print()

        render_enum_results(result.processed_by_target, save)

