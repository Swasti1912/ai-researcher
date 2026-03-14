"""
Base Agent Module.

Provides ``BaseAgent`` – the abstract superclass every concrete agent
inherits from.  It encapsulates:

  • System-prompt construction
  • Plain-text and structured (JSON → Pydantic) LLM invocation
  • Markdown fence stripping
  • Standardised error wrapping and trace recording
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import create_agent_llm
from app.state import ResearchState
from app.utils.exceptions import AgentExecutionError
from app.utils.helpers import safe_json_parse
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for every agent in the AI Researcher pipeline.

    Subclasses **must** implement:
      • ``name``          – unique agent identifier
      • ``system_prompt``  – property returning the system message text
      • ``execute``        – the core async logic
    """

    name: str = "base"

    def __init__(self, **llm_kwargs: Any) -> None:
        """
        Initialise the agent with an LLM instance.

        Args:
            **llm_kwargs: Forwarded to ``create_agent_llm`` for
                          per-agent overrides (temperature, max_tokens).
        """
        self._llm = create_agent_llm(self.name, **llm_kwargs)

    # ── Abstract interface ───────────────────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt defining this agent's behaviour."""
        ...

    @abstractmethod
    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Execute the agent's core logic.

        Args:
            state: Current graph state.

        Returns:
            Dict of state-field updates to merge back.
        """
        ...

    # ── LLM helpers ──────────────────────────────────────────────────

    async def call_llm(self, user_message: str) -> str:
        """
        Send system + user messages to the LLM and return text.

        Args:
            user_message: Human-turn content.

        Returns:
            The assistant's response string.

        Raises:
            AgentExecutionError: On any invocation failure.
        """
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_message),
            ]
            response = await self._llm.ainvoke(messages)
            return response.content
        except Exception as exc:
            logger.error(
                "LLM call failed",
                extra={"agent": self.name, "error": str(exc)},
            )
            raise AgentExecutionError(
                agent_name=self.name,
                message="LLM invocation failed",
                detail=str(exc),
            ) from exc

    async def call_llm_structured(
        self,
        user_message: str,
        model_cls: Type[BaseModel],
    ) -> BaseModel:
        """
        Invoke the LLM and parse the response into a Pydantic model.

        Appends a JSON-schema instruction to the user prompt so the
        model returns valid JSON.

        Args:
            user_message: Human-turn content.
            model_cls:    Target Pydantic model class.

        Returns:
            Parsed model instance.

        Raises:
            AgentExecutionError: If LLM call or JSON parsing fails.
        """
        schema_instruction = (
            "\n\nYou MUST respond with ONLY valid JSON matching this schema "
            "(no markdown, no explanation):\n"
            f"{json.dumps(model_cls.model_json_schema(), indent=2)}"
        )
        raw = await self.call_llm(user_message + schema_instruction)
        parsed = safe_json_parse(raw)

        if parsed is None:
            raise AgentExecutionError(
                agent_name=self.name,
                message="Failed to parse structured JSON from LLM",
                detail=f"Raw output: {raw[:300]}",
            )

        try:
            return model_cls.model_validate(parsed)
        except Exception as exc:
            raise AgentExecutionError(
                agent_name=self.name,
                message="Pydantic validation failed on LLM output",
                detail=str(exc),
            ) from exc

    # ── LangGraph callable ───────────────────────────────────────────

    async def __call__(self, state: ResearchState) -> Dict[str, Any]:
        """
        Wrap ``execute`` with tracing, timing, and error handling.

        This is the method LangGraph invokes.
        """
        start = time.perf_counter()
        logger.info(
            "Agent starting",
            extra={"agent": self.name, "request_id": state.request_id},
        )

        try:
            updates = await self.execute(state)

            elapsed = round(time.perf_counter() - start, 3)

            # Record trace entry
            trace_entry = {
                "agent": self.name,
                "elapsed_s": elapsed,
                "status": "success",
            }
            updates.setdefault("agent_trace", list(state.agent_trace) + [trace_entry])

            logger.info(
                "Agent completed",
                extra={"agent": self.name, "elapsed_s": elapsed},
            )
            return updates

        except AgentExecutionError:
            raise
        except Exception as exc:
            elapsed = round(time.perf_counter() - start, 3)
            logger.error(
                "Agent unexpected failure",
                extra={"agent": self.name, "error": str(exc), "elapsed_s": elapsed},
            )
            raise AgentExecutionError(
                agent_name=self.name,
                message="Unexpected error",
                detail=str(exc),
            ) from exc
