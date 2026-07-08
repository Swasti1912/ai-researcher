"""
Intent Agent.

Rank the question according to the intent.  Classifies the refined
query by intent type (Why?, How?, When?, What?, Comparison,
Methodology, Survey, General) and detects the research domain.

Position: Refiner → **Intent** → Decomposer.
"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.nodes.base import BaseAgent
from app.state import IntentResult, ResearchState
from app.utils.constants import AgentName
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Intent(BaseAgent):
    """
    Classify intent and domain of the research question.

    Behaviour:
      1. Choose exactly one primary_intent from the enumerated set.
      2. Assign a confidence score.
      3. Detect the research domain (e.g. NLP, biology, economics).
      4. Tag secondary intents if applicable.
    """

    name = AgentName.INTENT

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Intent Agent of an AI Research Assistant.\n\n"
            "Classify the research question into ONE primary intent:\n"
            "  why, how, when, what, who, comparison, methodology, survey, general\n\n"
            "Also identify the research_domain (e.g. 'machine learning', 'genomics').\n\n"
            "Return ONLY JSON: {primary_intent, confidence (0-1), research_domain, sub_intents: [...]}"
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Classify intent and domain."""
        q = state.refined_query or state.original_query
        hint = ""
        if state.uploaded_paper_text:
            hint = f"\n(Paper uploaded: {state.uploaded_paper_filename or '?'})"
        result = await self.call_llm_structured(f'Question: "{q}"{hint}', IntentResult)
        _log.info("Intent", extra={"intent": result.primary_intent, "conf": result.confidence, "domain": result.research_domain})
        return {"intent": result, "current_agent": self.name}


async def intent_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Intent()(state)
