"""
Intent Agent.

Ranks the question according to its intent (Why?, How?, When?,
What?, Comparison, Methodology, etc.) and identifies the research
domain.

Flow position::

    Refiner ──→ **Intent** ──→ Decomposer
                    ↕
           (paper upload feeds context)
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent
from app.state import IntentResult, ResearchState
from app.utils.constants import AgentName
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IntentAgent(BaseAgent):
    """
    Rank the question according to its intent.

    Responsibilities:
        1. Classify the primary intent (why / how / when / what /
           comparison / methodology / survey / general).
        2. Assign a confidence score.
        3. Detect the research domain (machine learning, biology, …).
        4. Tag secondary intents.
    """

    name = AgentName.INTENT

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Intent Agent of an AI Research Assistant.\n\n"
            "Classify the given research question into exactly ONE primary intent:\n"
            "  why          – Causal / explanatory questions\n"
            "  how          – Mechanism / process questions\n"
            "  when         – Temporal / timeline questions\n"
            "  what         – Definitional / descriptive questions\n"
            "  who          – Person / group identification\n"
            "  comparison   – Comparing methods, models, or approaches\n"
            "  methodology  – Questions about experimental design\n"
            "  survey       – Broad literature overview requests\n"
            "  general      – Does not fit above\n\n"
            "Also identify the research domain (e.g. 'machine learning', "
            "'genomics', 'economics').\n\n"
            "Return ONLY a JSON object with keys: "
            "primary_intent, confidence (0-1), research_domain, sub_intents (list)."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Classify the refined query's intent and domain.

        Args:
            state: Must contain ``refined_query`` (or falls back to ``original_query``).

        Returns:
            ``{"intent": IntentResult, "current_agent": str}``
        """
        query = state.refined_query or state.original_query

        paper_hint = ""
        if state.uploaded_paper_text:
            paper_hint = (
                f"\n\n(The user also uploaded a paper titled "
                f"'{state.uploaded_paper_filename or 'unknown'}' which may "
                "inform the domain classification.)"
            )

        prompt = f"Research question to classify:\n\"{query}\"{paper_hint}"

        intent = await self.call_llm_structured(prompt, IntentResult)

        logger.info(
            "Intent classified",
            extra={
                "primary": intent.primary_intent,
                "confidence": intent.confidence,
                "domain": intent.research_domain,
            },
        )

        return {
            "intent": intent,
            "current_agent": self.name,
        }


async def intent_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Intent Agent."""
    return await IntentAgent()(state)
