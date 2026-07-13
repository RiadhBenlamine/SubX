"""Logging utility module."""
import logging


def setup_logger(level: int = logging.ERROR) -> None:
    """Configure the root stream handler with customized formats."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt="[%(name)s|%(levelname)s]: %(message)s"
    ))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]


# pylint: disable=invalid-name
logger = logging.getLogger("SubX")
