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
    def setup_logging(debug: bool = False) -> None:
        """Initialize the root application logger."""
        setup_logger(debug=debug)

    @staticmethod
    def run_async(coro) -> None:
        """Run an asynchronous coroutine inside a synchronous context with clean exception handling."""
        async def _wrapper():
            loop = asyncio.get_running_loop()
            original_handler = loop.get_exception_handler()

            def _custom_handler(l, context):
                exc = context.get("exception")
                msg = str(context.get("message") or "")
                if isinstance(exc, OSError) or "gaierror" in msg.lower() or (exc and "gaierror" in str(exc).lower()):
                    import logging
                    logging.getLogger("asyncio").debug("Silenced background DNS/network exception: %s", context)
                    return
                if original_handler:
                    original_handler(l, context)
                else:
                    l.default_exception_handler(context)

            loop.set_exception_handler(_custom_handler)
            return await coro

        asyncio.run(_wrapper())
