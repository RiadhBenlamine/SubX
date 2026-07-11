from abc import ABC, abstractmethod
import asyncio
import typer
from core.ui.banner import banner
from core.logger import setup_logger

HELP_NAMES = {"help_option_names": ["-h", "--help"]}


class Command(ABC):
    """Abstract base class for CLI subcommands."""

    name: str = ""
    help: str = ""

    def register(self, app: typer.Typer) -> None:
        """Register the command to the Typer app."""
        app.command(
            name=self.name,
            help=self.help,
            context_settings=HELP_NAMES
        )(self.callback)

    @abstractmethod
    def callback(self, *args, **kwargs) -> None:
        """The command callback containing typer.Option declarations."""
        ...

    @staticmethod
    def show_banner() -> None:
        banner()

    @staticmethod
    def setup_logging() -> None:
        setup_logger()

    @staticmethod
    def run_async(coro) -> None:
        asyncio.run(coro)
