import logging
import sys

LOG_FORMAT = "%(levelname)-5s %(asctime)s [%(filename)s:%(lineno)d]:%(name)s: %(message)s"


def setup_stdout_logger(name: str, level) -> logging.Logger:
    """Return the named logger with a single stdout handler using the project
    log format. Idempotent — a second call adds no extra handler.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    return logger
