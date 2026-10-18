from __future__ import annotations

import logging
import sys


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger("auttorna")


logger = logging.getLogger("auttorna")
