"""Base CLI command classes and configurations."""
import asyncio
from abc import ABC, abstractmethod

import typer

from core.logger import setup_logger
from core.ui.banner import banner

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

    @staticmethod
    def show_banner() -> None:
        """Display the SUBX CLI banner."""
        banner()

    @staticmethod
    def setup_logging() -> None:
        """Initialize the root application logger."""
        setup_logger()

    @staticmethod
    def run_async(coro) -> None:
        """Run an asynchronous coroutine inside a synchronous context."""
        asyncio.run(coro)
