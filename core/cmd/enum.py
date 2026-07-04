import asyncio

import typer

from core.logger import setup_logger
from core.services.enum_service import EnumService
from core.ui.banner import banner
from core.ui.console import console, info, warn, error
from core.ui.renderers import render_enum_results

HELP_NAMES = {"help_option_names": ["-h", "--help"]}


def register(app: typer.Typer) -> None:
    """Register the enum command on the given Typer app."""
    app.command("enum", context_settings=HELP_NAMES)(enum)


def enum(
    config_file: str = typer.Option(..., "-c", "--config", help="Path to YAML/JSON config file."),
    save: bool       = typer.Option(True, "--save/--no-save", help="Save results to database."),
) -> None:
    """[bold cyan]Enumerate subdomains[/bold cyan] for target domain(s)."""
    asyncio.run(_enum(config_file, save))


async def _enum(config_file: str, save: bool) -> None:
    banner()
    setup_logger()

    service = EnumService()

    try:
        result = await service.run(config_file, save)
    except (FileNotFoundError, ValueError) as e:
        error(str(e))
    except RuntimeError as e:
        error(str(e))
    except Exception as e:
        error(f"Failed to load config: {e}")

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
