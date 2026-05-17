"""
logger.py
---------
Centralized logging for the pipeline.

All modules call get_logger(__name__) to get a consistently configured
logger that writes to both stdout and outputs/pipeline.log.

Log levels:
  INFO  → stdout + file  (normal pipeline progress)
  DEBUG → file only       (verbose API/parsing detail)
  WARNING/ERROR → both    (always visible)
"""

import logging
import sys
from pathlib import Path

_LOG_DIR  = Path("outputs")
_LOG_FILE = _LOG_DIR / "pipeline.log"
_FMT      = "%(asctime)s  %(levelname)-8s  %(name)-28s  %(message)s"
_DATE     = "%Y-%m-%d %H:%M:%S"
_INIT     = False   # module-level flag — configure root handler once


def _bootstrap():
    global _INIT
    if _INIT:
        return
    _INIT = True

    root = logging.getLogger("pipeline")
    root.setLevel(logging.DEBUG)

    # ── Console: INFO and above ───────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(ch)

    # ── File: DEBUG and above ─────────────────────────────────────────
    _LOG_DIR.mkdir(exist_ok=True)
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(fh)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'pipeline' hierarchy."""
    _bootstrap()
    return logging.getLogger(f"pipeline.{name}")
