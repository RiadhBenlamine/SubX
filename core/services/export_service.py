"""Service layer for exporting outputs to files."""
from pathlib import Path

from core.ui.console import error, success


class ExportService:
    """Universal I/O handlers.

    Parses formatting separators and writes domain lines to output files.
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
            f"[bold white]{output}[/bold white]  "
            f"[dim](sep: {repr(sep)})[/dim]"
        )

    @staticmethod
    def parse_ox(value: str) -> tuple[str, str]:
        """Parse -oX 'separator:file' argument into (separator, filepath)."""
        idx = value.rfind(":")
        if idx in (-1, len(value) - 1):
            error(
                "-oX format is '<separator>:<file>' e.g. ';:out.txt' or ' :out.txt'\n"
                "  The separator comes before the last colon, the file path after it."
            )
        sep = value[:idx]
        file = value[idx + 1:]
        return sep, file
