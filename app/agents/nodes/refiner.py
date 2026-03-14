"""
Refiner Agent.

Modify the user prompt as per AI Researcher context.  Transforms the
raw query into a clear, detailed research question, incorporating
uploaded paper context when available.

Position: Orchestrator → **Refiner** → Intent.
"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.nodes.base import BaseAgent
from app.state import ResearchState
from app.utils.constants import AgentName
from app.utils.helpers import truncate
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Refiner(BaseAgent):
    """
    Rewrite the user query as a precise research question.

    Behaviour:
      1. Remove vagueness and expand abbreviations.
      2. If paper text is present, contextualise the query within the paper.
      3. Output 1-3 sentence refined question (no answer).
    """

    name = AgentName.REFINER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Refiner Agent of an AI Research Assistant.\n\n"
            "TASK: Rewrite the user's raw query into a precise, self-contained research question.\n"
            "• Remove vagueness, expand abbreviations.\n"
            "• If a paper excerpt is provided, contextualise the query.\n"
            "• Output 1–3 sentences – the refined question only, no preamble."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Produce a refined query string."""
        paper = ""
        if state.uploaded_paper_text:
            paper = f"\n\n--- Uploaded paper ({state.uploaded_paper_filename or 'unknown'}) ---\n{truncate(state.uploaded_paper_text, 2000)}"
        prompt = f'Original query: "{state.original_query}"{paper}\n\nRefine this.'
        refined = (await self.call_llm(prompt)).strip().strip('"\'')
        _log.info("Refined", extra={"in_len": len(state.original_query), "out_len": len(refined)})
        return {"refined_query": refined, "current_agent": self.name}


async def refiner_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Refiner()(state)
