"""
Logging configuration.
"""

import logging


def create_logger(level: str) -> logging.Logger:
    """Create and configure the XRack logger."""

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    return logging.getLogger("XRack")
