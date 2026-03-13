"""
Centralized logging for Lumi AI.

Usage:
    from src.utils.log import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.error("Something broke", exc_info=True)

Environment variables:
    LUMI_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: WARNING)
    LUMI_LOG_FILE:  Path to log file (default: None — stderr only)
"""

import logging
import os
import sys

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


def _configure_root() -> None:
    """One-time setup of the root logger for Lumi."""
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.getenv("LUMI_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)

    root = logging.getLogger("lumi")
    root.setLevel(level)

    # Stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(stderr_handler)

    # Optional file handler
    log_file = os.getenv("LUMI_LOG_FILE")
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
            root.addHandler(file_handler)
        except OSError:
            root.warning("Could not open log file: %s", log_file)

    # Prevent propagation to the root Python logger
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the 'lumi' namespace.

    Args:
        name: Module name, typically __name__.

    Returns:
        A configured Logger instance.
    """
    _configure_root()
    # Normalize: "src.utils.foo" -> "lumi.utils.foo"
    if name.startswith("src."):
        name = "lumi." + name[4:]
    elif not name.startswith("lumi"):
        name = "lumi." + name
    return logging.getLogger(name)
