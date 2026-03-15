"""Centralized logging for nagare.

All modules should use: from nagare.log import logger

Logs to ~/.local/share/nagare/nagare.log with rotation.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "share" / "nagare"
LOG_PATH = LOG_DIR / "nagare.log"
MAX_BYTES = 1_000_000  # 1MB
BACKUP_COUNT = 3

LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("nagare")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s.%(funcName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
