import logging


def setup_logger(level: int = logging.ERROR) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt="[%(name)s|%(levelname)s]: %(message)s"
    ))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]

logger = logging.getLogger("SubX")