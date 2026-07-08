"""
LLM Provider — preference chain with automatic fallback.

Order (whichever are configured): OpenAI → Groq → Gemini. The primary is
wrapped with LangChain's ``with_fallbacks`` so any failure (rate limit / bad
key / timeout) transparently retries the same request on the next provider.
Agents call ``.ainvoke(messages)`` and read ``.content`` regardless of provider.

Usage::

    from app.llm import get_llm, make_agent_llm
    llm = get_llm()                          # shared cached default
    llm = make_agent_llm("refiner")          # per-agent instance
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional, Tuple

from langchain_core.runnables import Runnable

from app.config import get_settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _t(temperature: Optional[float]) -> float:
    return temperature if temperature is not None else get_settings().llm_temperature


def _mx(max_tokens: Optional[int]) -> int:
    return max_tokens or get_settings().llm_max_tokens


def _build_openai(temperature: Optional[float], max_tokens: Optional[int]) -> Optional[Runnable]:
    s = get_settings()
    if not s.openai_api_key:
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=s.openai_model, temperature=_t(temperature), max_tokens=_mx(max_tokens),
        api_key=s.openai_api_key, timeout=120, max_retries=1,
    )


def _build_groq(temperature: Optional[float], max_tokens: Optional[int]) -> Optional[Runnable]:
    s = get_settings()
    if not s.groq_api_key:
        return None
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=s.llm_model, temperature=_t(temperature), max_tokens=_mx(max_tokens),
        api_key=s.groq_api_key, request_timeout=120.0, max_retries=1,
    )


def _build_gemini(temperature: Optional[float], max_tokens: Optional[int]) -> Optional[Runnable]:
    s = get_settings()
    if not s.google_api_key:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        _log.warning("google_api_key set but langchain-google-genai not installed")
        return None
    return ChatGoogleGenerativeAI(
        model=s.gemini_model, temperature=_t(temperature), max_output_tokens=_mx(max_tokens),
        google_api_key=s.google_api_key, timeout=120, max_retries=1,
    )


# Preference order: OpenAI (funded, reliable) → Groq (fast, free) → Gemini (free)
_BUILDERS: List[Tuple[str, callable]] = [
    ("openai", _build_openai),
    ("groq", _build_groq),
    ("gemini", _build_gemini),
]


def _build_llm(temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Runnable:
    chain: List[Tuple[str, Runnable]] = []
    for name, build in _BUILDERS:
        llm = build(temperature, max_tokens)
        if llm is not None:
            chain.append((name, llm))
    if not chain:
        raise LLMProviderError(
            "No LLM provider configured",
            "Set OPENAI_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY",
        )
    primary_name, primary = chain[0]
    fallbacks = [llm for _, llm in chain[1:]]
    if fallbacks:
        _log.info("LLM chain", extra={"primary": primary_name,
                                      "fallbacks": [n for n, _ in chain[1:]]})
        return primary.with_fallbacks(fallbacks)
    _log.info("LLM chain", extra={"primary": primary_name, "fallbacks": []})
    return primary


@lru_cache()
def get_llm() -> Runnable:
    """Return the cached default LLM (primary + fallbacks)."""
    return _build_llm()


def make_agent_llm(agent: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Runnable:
    """Create a fresh (non-cached) LLM for a specific agent."""
    _log.info("Creating agent LLM", extra={"agent": agent})
    return _build_llm(temperature=temperature, max_tokens=max_tokens)


# Alias used by app/agents/base.py
create_agent_llm = make_agent_llm


def provider_chain() -> List[str]:
    """Names of the configured providers, in fallback order."""
    out: List[str] = []
    for name, build in _BUILDERS:
        try:
            if build(None, None) is not None:
                out.append(name)
        except Exception:  # noqa: BLE001
            pass
    return out


def fallback_active() -> bool:
    """True when at least one fallback exists behind the primary."""
    return len(provider_chain()) > 1
