"""
LLM Provider — Groq only.

Usage::

    from app.llm import get_llm, make_agent_llm
    llm = get_llm()                          # shared cached default
    llm = make_agent_llm("refiner")          # per-agent instance
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_groq import ChatGroq

from app.config import get_settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _build_llm(temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> ChatGroq:
    s = get_settings()
    if not s.groq_api_key:
        raise LLMProviderError("GROQ_API_KEY not set", "Add GROQ_API_KEY=<your-key> to .env")
    t = temperature if temperature is not None else s.llm_temperature
    m = max_tokens or s.llm_max_tokens
    _log.info("Using Groq LLM", extra={"model": s.llm_model})
    return ChatGroq(
        model=s.llm_model,
        temperature=t,
        max_tokens=m,
        api_key=s.groq_api_key,
        # Groq SDK default is 60 s — bumped to 120 s so large-paper summarise
        # calls don't hit the timeout on the first (cold-connection) request.
        request_timeout=120.0,
        # Keep one retry so transient rate-limit errors self-heal, but don't
        # chain 3× 60 s waits that blow past the frontend's 180 s budget.
        max_retries=1,
    )


@lru_cache()
def get_llm() -> ChatGroq:
    """Return the cached default Groq LLM instance."""
    return _build_llm()


def make_agent_llm(agent: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> ChatGroq:
    """Create a fresh (non-cached) Groq LLM for a specific agent."""
    _log.info("Creating agent LLM", extra={"agent": agent})
    return _build_llm(temperature=temperature, max_tokens=max_tokens)


# Alias used by app/agents/base.py
create_agent_llm = make_agent_llm
