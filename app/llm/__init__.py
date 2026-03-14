"""
LLM Provider.

Exposes ``get_llm()`` (cached default) and ``make_agent_llm()``
(per-agent, non-cached) factory functions.

Usage::

    from app.llm import get_llm, make_agent_llm
    llm = get_llm()                               # shared default
    llm = make_agent_llm("refiner", temperature=0.3)  # agent-specific
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

_log = get_logger(__name__)


@lru_cache()
def get_llm() -> ChatOpenAI:
    """Return the cached default LLM instance."""
    s = get_settings()
    _assert_key(s.openai_api_key)
    _log.info("Creating default LLM", extra={"model": s.llm_model})
    return ChatOpenAI(
        model=s.llm_model,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        api_key=s.openai_api_key,
        request_timeout=60,
    )


def make_agent_llm(
    agent: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    """
    Create a *fresh* LLM for a specific agent (not cached).

    Args:
        agent:       Agent name for logging.
        temperature: Override sampling temperature.
        max_tokens:  Override max completion tokens.

    Returns:
        ``ChatOpenAI`` instance with the requested settings.
    """
    s = get_settings()
    _assert_key(s.openai_api_key)
    t = temperature if temperature is not None else s.llm_temperature
    m = max_tokens or s.llm_max_tokens
    _log.info("Creating agent LLM", extra={"agent": agent, "temp": t, "max_tok": m})
    return ChatOpenAI(
        model=s.llm_model, temperature=t, max_tokens=m,
        api_key=s.openai_api_key, request_timeout=60,
    )


def _assert_key(key: str) -> None:
    if not key:
        raise LLMProviderError("OPENAI_API_KEY not configured", "Set it in .env")
