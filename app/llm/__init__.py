"""
LLM Provider — Groq primary, optional Gemini fallback.

Usage::

    from app.llm import get_llm, make_agent_llm
    llm = get_llm()                          # shared cached default
    llm = make_agent_llm("refiner")          # per-agent instance

When ``GOOGLE_API_KEY`` is set, every call is wrapped so that a Groq failure
(rate limit / bad key / timeout) transparently retries the same request on
Gemini — the agents call ``.ainvoke(messages)`` and read ``.content`` either
way, so nothing downstream changes.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from app.config import get_settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _build_groq(temperature: Optional[float], max_tokens: Optional[int]) -> ChatGroq:
    s = get_settings()
    if not s.groq_api_key:
        raise LLMProviderError("GROQ_API_KEY not set", "Add GROQ_API_KEY=<your-key> to .env")
    t = temperature if temperature is not None else s.llm_temperature
    m = max_tokens or s.llm_max_tokens
    return ChatGroq(
        model=s.llm_model,
        temperature=t,
        max_tokens=m,
        api_key=s.groq_api_key,
        request_timeout=120.0,
        max_retries=1,
    )


def _build_gemini(temperature: Optional[float], max_tokens: Optional[int]) -> Optional[Runnable]:
    """Build the Gemini fallback, or None when unavailable (no key / package)."""
    s = get_settings()
    if not s.google_api_key:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        _log.warning("google_api_key set but langchain-google-genai not installed; no fallback")
        return None
    t = temperature if temperature is not None else s.llm_temperature
    m = max_tokens or s.llm_max_tokens
    return ChatGoogleGenerativeAI(
        model=s.gemini_model,
        temperature=t,
        max_output_tokens=m,
        google_api_key=s.google_api_key,
        timeout=120,
        max_retries=1,
    )


def _build_llm(temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Runnable:
    """
    Return the Groq LLM, wrapped with a Gemini fallback when configured.

    ``with_fallbacks`` catches any exception from the primary (Groq 429 rate
    limits, 401 bad key, 5xx/timeout) and re-runs the same call on Gemini.
    """
    s = get_settings()
    groq = _build_groq(temperature, max_tokens)
    gemini = _build_gemini(temperature, max_tokens)
    if gemini is not None:
        _log.info("Using Groq LLM (Gemini fallback active)", extra={"model": s.llm_model, "fallback": s.gemini_model})
        return groq.with_fallbacks([gemini])
    _log.info("Using Groq LLM (no fallback)", extra={"model": s.llm_model})
    return groq


@lru_cache()
def get_llm() -> Runnable:
    """Return the cached default LLM (Groq + optional Gemini fallback)."""
    return _build_llm()


def make_agent_llm(agent: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Runnable:
    """Create a fresh (non-cached) LLM for a specific agent."""
    _log.info("Creating agent LLM", extra={"agent": agent})
    return _build_llm(temperature=temperature, max_tokens=max_tokens)


# Alias used by app/agents/base.py
create_agent_llm = make_agent_llm


def fallback_active() -> bool:
    """True when the Gemini fallback is usable (key set + package importable)."""
    if not get_settings().google_api_key:
        return False
    try:
        import langchain_google_genai  # noqa: F401
        return True
    except ImportError:
        return False
