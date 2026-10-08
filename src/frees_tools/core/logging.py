"""Local structured logs with no paths, download URLs or RPC credentials."""

import json
from logging.handlers import RotatingFileHandler
import logging
from .config import STATE_DIR, load_config


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "time": self.formatTime(record),
                "level": record.levelname,
                "event": record.getMessage(),
            },
            ensure_ascii=False,
        )


def configure():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("frees_tools")
    if not logger.handlers:
        handler = RotatingFileHandler(
            STATE_DIR / "events.jsonl", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, load_config()["log_level"].upper(), logging.INFO))
    return logger
