"""
Base Agent.

Abstract superclass every concrete agent inherits from.

Provides:
  • ``call_llm``           – plain-text LLM invocation
  • ``call_llm_structured``– JSON → Pydantic invocation
  • ``__call__``           – LangGraph-compatible wrapper with timing,
                             tracing, and error handling
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import make_agent_llm
from app.state import ResearchState
from app.utils.exceptions import AgentExecutionError
from app.utils.helpers import safe_json
from app.utils.logger import get_logger

_log = get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for every pipeline agent.

    Sub-classes **must** implement ``name``, ``system_prompt``, and ``execute``.
    """

    name: str = "base"

    def __init__(self, **llm_kw: Any) -> None:
        self._llm = make_agent_llm(self.name, **llm_kw)

    # ── Abstract ─────────────────────────────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System-message text that defines the agent's persona."""
        ...

    @abstractmethod
    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Core logic.  Return a dict of state-field updates."""
        ...

    # ── LLM helpers ──────────────────────────────────────────────────

    async def call_llm(self, user_msg: str) -> str:
        """
        Send system + user message to the LLM and return the response text.

        Args:
            user_msg: Human-turn content.

        Returns:
            Assistant reply string.

        Raises:
            AgentExecutionError: On any invocation failure.
        """
        try:
            resp = await self._llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_msg),
            ])
            return resp.content
        except Exception as exc:
            raise AgentExecutionError(self.name, "LLM call failed", str(exc)) from exc

    async def call_llm_structured(self, user_msg: str, model: Type[BaseModel]) -> BaseModel:
        """
        Invoke the LLM expecting JSON output, parsed into *model*.

        Appends a schema instruction so the LLM returns valid JSON.

        Args:
            user_msg: Prompt content.
            model:    Target Pydantic class.

        Returns:
            Validated model instance.

        Raises:
            AgentExecutionError: On LLM or parse failure.
        """
        schema_hint = (
            "\n\nRespond with ONLY valid JSON (no markdown, no extra text) "
            f"matching this schema:\n{json.dumps(model.model_json_schema(), indent=2)}"
        )
        raw = await self.call_llm(user_msg + schema_hint)
        parsed = safe_json(raw)
        if parsed is None:
            raise AgentExecutionError(self.name, "JSON parse failed", raw[:300])
        try:
            return model.model_validate(parsed)
        except Exception as exc:
            raise AgentExecutionError(self.name, "Pydantic validation failed", str(exc)) from exc

    # ── LangGraph callable ───────────────────────────────────────────

    async def __call__(self, state: ResearchState) -> Dict[str, Any]:
        """Wrap execute() with timing, tracing, and error handling."""
        t0 = time.perf_counter()
        _log.info("Agent start", extra={"agent": self.name, "rid": state.request_id})
        try:
            updates = await self.execute(state)
            elapsed = round(time.perf_counter() - t0, 3)
            trace = {"agent": self.name, "elapsed_s": elapsed, "status": "ok"}
            updates.setdefault("agent_trace", list(state.agent_trace) + [trace])
            _log.info("Agent done", extra={"agent": self.name, "elapsed_s": elapsed})
            return updates
        except AgentExecutionError:
            raise
        except Exception as exc:
            raise AgentExecutionError(self.name, "Unexpected error", str(exc)) from exc
