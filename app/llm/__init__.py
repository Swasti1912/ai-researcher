"""
LLM Provider.

Supports Groq (default) and OpenAI, controlled by LLM_PROVIDER in .env.

Usage::

    from app.llm import get_llm, make_agent_llm
    llm = get_llm()                          # shared cached default
    llm = make_agent_llm("refiner")          # per-agent instance
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.config import get_settings
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _build_llm(temperature: Optional[float] = None, max_tokens: Optional[int] = None):
    s = get_settings()
    t = temperature if temperature is not None else s.llm_temperature
    m = max_tokens or s.llm_max_tokens

    if s.llm_provider.lower() == "groq":
        if not s.groq_api_key:
            raise LLMProviderError("GROQ_API_KEY not set", "Add it to .env")
        from langchain_groq import ChatGroq
        _log.info("Using Groq LLM", extra={"model": s.llm_model})
        return ChatGroq(
            model=s.llm_model,
            temperature=t,
            max_tokens=m,
            api_key=s.groq_api_key,
        )
    else:
        if not s.openai_api_key:
            raise LLMProviderError("OPENAI_API_KEY not set", "Add it to .env")
        from langchain_openai import ChatOpenAI
        _log.info("Using OpenAI LLM", extra={"model": s.llm_model})
        return ChatOpenAI(
            model=s.llm_model,
            temperature=t,
            max_tokens=m,
            api_key=s.openai_api_key,
        )


@lru_cache()
def get_llm():
    """Return the cached default LLM instance."""
    return _build_llm()


def make_agent_llm(agent: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None):
    """Create a fresh (non-cached) LLM for a specific agent."""
    _log.info("Creating agent LLM", extra={"agent": agent})
    return _build_llm(temperature=temperature, max_tokens=max_tokens)


# Alias used by app/agents/base.py
create_agent_llm = make_agent_llm


def _assert_key(key: str) -> None:
    if not key:
        raise LLMProviderError("API key not configured", "Set it in .env")
