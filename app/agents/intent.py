"""
Intent Agent.

Classifies the refined research query by intent type
(Why, How, When, What, Comparison, Methodology, etc.)
and identifies the research domain.
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent
from app.state import IntentClassification, ResearchState
from app.utils import get_logger

logger = get_logger(__name__)


class IntentAgent(BaseAgent):
    """
    Classify the research query by intent and domain.

    Responsibilities:
        1. Determine the primary intent category.
        2. Assign a confidence score.
        3. Identify the research domain (e.g. NLP, biology).
        4. Tag any secondary intents.
    """

    name = "intent"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Intent Agent of an AI Research Assistant. "
            "Analyse the given research question and classify it.\n\n"
            "Classification categories:\n"
            "  - why:             Causal reasoning questions\n"
            "  - how:             Mechanism / process questions\n"
            "  - when:            Temporal / timeline questions\n"
            "  - what:            Definitional / descriptive questions\n"
            "  - comparison:      Comparing methods, models, or approaches\n"
            "  - methodology:     Questions about research methods\n"
            "  - research_domain: Domain-specific exploration\n"
            "  - general:         Broad or multi-faceted queries\n\n"
            "Also identify the research domain (e.g. machine learning, "
            "genomics, economics) and any secondary intents.\n\n"
            "Respond ONLY with valid JSON."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Classify the refined query's intent and domain.

        Args:
            state: Must contain ``refined_query`` (set by Refiner).

        Returns:
            ``{"intent": IntentClassification, "current_agent": "intent"}``.
        """
        query = state.refined_query or state.original_query

        prompt = f"Research question to classify:\n{query}"

        classification = await self._invoke_llm_structured(
            prompt, IntentClassification
        )

        logger.info(
            "intent_classified",
            primary=classification.primary_intent,
            confidence=classification.confidence,
            domain=classification.research_domain,
        )

        return {
            "intent": classification,
            "current_agent": self.name,
        }


async def intent_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper for the Intent Agent."""
    agent = IntentAgent()
    return await agent(state)
