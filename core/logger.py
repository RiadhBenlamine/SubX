import logging
import sys


def setup_logger():
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stdout,
        format="[%(name)s|%(levelname)s]: %(message)s"
    )
    return logging.getLogger(__name__)