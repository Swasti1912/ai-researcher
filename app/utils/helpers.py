"""
Shared Helper Functions.

  • ``gen_id``    – UUID4 request identifiers
  • ``timed``     – async/sync execution-time decorator
  • ``truncate``  – character-budget text truncation
  • ``safe_json`` – LLM-output JSON parser (handles ``` fences)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from functools import wraps
from typing import Any, Callable

from app.utils.logger import get_logger

_log = get_logger(__name__)


def gen_id() -> str:
    """Return a UUID-4 string suitable for request tracing."""
    return str(uuid.uuid4())


def timed(fn: Callable) -> Callable:
    """
    Decorator that logs wall-clock time for both sync and async callables.

    Logs at INFO on success, ERROR on failure.
    """

    @wraps(fn)
    async def _async(*a: Any, **kw: Any) -> Any:
        t0 = time.perf_counter()
        try:
            result = await fn(*a, **kw)
            _log.info(f"{fn.__qualname__} ok", extra={"elapsed_s": round(time.perf_counter() - t0, 4)})
            return result
        except Exception as exc:
            _log.error(f"{fn.__qualname__} fail", extra={"elapsed_s": round(time.perf_counter() - t0, 4), "error": str(exc)})
            raise

    @wraps(fn)
    def _sync(*a: Any, **kw: Any) -> Any:
        t0 = time.perf_counter()
        try:
            result = fn(*a, **kw)
            _log.info(f"{fn.__qualname__} ok", extra={"elapsed_s": round(time.perf_counter() - t0, 4)})
            return result
        except Exception as exc:
            _log.error(f"{fn.__qualname__} fail", extra={"elapsed_s": round(time.perf_counter() - t0, 4), "error": str(exc)})
            raise

    return _async if asyncio.iscoroutinefunction(fn) else _sync


def truncate(text: str, limit: int = 500) -> str:
    """Shorten *text* to at most *limit* characters with an ellipsis."""
    if not text or len(text) <= limit:
        return text or ""
    return text[: limit - 1] + "…"


def safe_json(raw: str, fallback: Any = None) -> Any:
    """
    Parse JSON from an LLM response, stripping markdown fences.

    Returns *fallback* when parsing fails.
    """
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
    if s.endswith("```"):
        s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        _log.warning("safe_json parse failed", extra={"preview": s[:200]})
        return fallback
