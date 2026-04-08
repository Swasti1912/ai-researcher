"""
Structured Logging.

Every log line is emitted as a single-line JSON object for easy
ingestion by CloudWatch / ELK / Datadog.  Extra context fields
(request_id, agent, elapsed_s …) are merged automatically.

Usage::

    from app.utils import get_logger
    logger = get_logger(__name__)
    logger.info("Hello", extra={"request_id": "abc"})
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class _JSONFormatter(logging.Formatter):
    """Emit each record as a flat JSON object."""

    _SKIP = frozenset({
        "name", "msg", "args", "created", "relativeCreated",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "pathname", "filename", "module", "levelno", "levelname",
        "msecs", "taskName", "message", "thread", "threadName",
        "processName", "process",
    })

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        entry: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in self._SKIP and not k.startswith("_"):
                try:
                    json.dumps(v)
                    entry[k] = v
                except (TypeError, ValueError):
                    entry[k] = str(v)
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """
    Initialise the root logger with JSON output to stdout.

    Call once at application startup.

    Args:
        level: Minimum log level (DEBUG / INFO / WARNING / ERROR).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())
    root.addHandler(handler)

    for name in ("httpx", "httpcore", "urllib3", "asyncio", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (uses JSON formatter once ``setup_logging`` has been called)."""
    return logging.getLogger(name)
