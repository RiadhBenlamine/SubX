"""Logging utility module.

Console output deduplicates identical messages (showing each only once).
All warnings and errors are additionally written to a persistent log file.
"""
import logging
import pathlib
from collections import Counter
from logging.handlers import RotatingFileHandler

# Default log file lives next to the project root
_LOG_DIR = pathlib.Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "subx.log"


class DeduplicatingHandler(logging.Handler):
    """Stream handler that suppresses repeated identical messages.

    Each unique (logger-name, level, message) triple is emitted to the
    console exactly once.  Occurrence counts are tracked so a summary
    can be printed later via `get_counts()`.
    """

    def __init__(self, stream=None):
        super().__init__()
        self._seen: set[str] = set()
        self._counts: Counter = Counter()
        self._stream_handler = logging.StreamHandler(stream)

    def setFormatter(self, fmt):  # noqa: N802 – overrides stdlib
        super().setFormatter(fmt)
        self._stream_handler.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        key = f"{record.name}|{record.levelno}|{record.getMessage()}"
        self._counts[key] += 1
        if key not in self._seen:
            self._seen.add(key)
            self._stream_handler.emit(record)

    def get_counts(self) -> dict[str, int]:
        """Return {message_key: count} for messages that appeared more than once."""
        return {k: v for k, v in self._counts.items() if v > 1}

    def reset(self) -> None:
        """Clear seen messages and counts (useful between runs)."""
        self._seen.clear()
        self._counts.clear()


# Module-level reference so other modules can retrieve the summary
_dedup_handler: DeduplicatingHandler | None = None


def setup_logger(level: int = logging.ERROR) -> None:
    """Configure logging with deduplicated console output and a log file.

    Console : shows each unique error/warning only once.
    File    : captures every message with timestamps for debugging.
    """
    global _dedup_handler  # noqa: PLW0603

    # ── Console (deduplicated) ──────────────────────────────────
    _dedup_handler = DeduplicatingHandler()
    _dedup_handler.setLevel(level)
    _dedup_handler.setFormatter(logging.Formatter(
        fmt="[%(name)s|%(levelname)s]: %(message)s"
    ))

    # ── File (full detail) ──────────────────────────────────────
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=2 * 1024 * 1024,   # 2 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(name)s|%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logging.root.setLevel(min(level, logging.WARNING))
    logging.root.handlers = [_dedup_handler, file_handler]


def get_dedup_handler() -> DeduplicatingHandler | None:
    """Return the active deduplicating handler (if set up)."""
    return _dedup_handler


# pylint: disable=invalid-name
logger = logging.getLogger("SubX")

