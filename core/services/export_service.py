"""Service layer for exporting outputs to files."""
from pathlib import Path

from core.ui.console import error, success


class ExportService:
    """Universal I/O handlers.

    Writes domain lines to output files.
    """

    @staticmethod
    def write_output(values: list[str], output: str, separator: str = "\n") -> None:
        """Write a list of values to a file with the given separator."""
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        sep = separator.replace("\\n", "\n").replace("\\t", "\t")
        out.write_text(sep.join(values) + "\n", encoding="utf-8")
        success(
            f"Saved [bold white]{len(values)}[/bold white] entries → "
            f"[bold white]{output}[/bold white]"
        )

