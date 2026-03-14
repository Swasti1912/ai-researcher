"""
Decomposer Agent.

Decomposes complex questions and domains into simpler, targeted
sub-questions.  Each sub-question is assigned to a specific API
source (arXiv, Semantic Scholar, CrossRef, web search).

Flow position::

    Intent ──→ **Decomposer** ──→ Aggregator
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.agents.base import BaseAgent
from app.state import ResearchState, SubQuestion
from app.utils.constants import AgentName
from app.utils.helpers import safe_json_parse
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DecomposerAgent(BaseAgent):
    """
    Decompose complex questions into simpler, API-routable sub-questions.

    Responsibilities:
        1. Analyse the refined query and its intent classification.
        2. Generate 2-6 focused sub-questions.
        3. Assign each to the most appropriate data source.
        4. Prioritise by importance (1 = highest).
    """

    name = AgentName.DECOMPOSER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Decomposer Agent of an AI Research Assistant.\n\n"
            "Given a refined research question and its intent, break it into "
            "2–6 simpler, self-contained sub-questions.\n\n"
            "For each sub-question choose the best API source:\n"
            "  arxiv              – Academic preprints and papers\n"
            "  semantic_scholar   – Citation data, paper metadata\n"
            "  crossref           – DOI lookup, publication metadata\n"
            "  web_search         – General / recent information\n\n"
            "Return ONLY a JSON array of objects with keys:\n"
            '  id (string, e.g. "sq_1"), question (string), '
            "api_source (string), priority (int 1-5, 1=highest).\n\n"
            "Example:\n"
            '[{"id":"sq_1","question":"...","api_source":"arxiv","priority":1}]'
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Decompose the research query into sub-questions.

        Args:
            state: Must contain ``refined_query`` and ``intent``.

        Returns:
            ``{"sub_questions": List[SubQuestion], "current_agent": str}``
        """
        query = state.refined_query or state.original_query
        intent_ctx = ""
        if state.intent:
            intent_ctx = (
                f"\nIntent: {state.intent.primary_intent} "
                f"(confidence {state.intent.confidence:.2f})\n"
                f"Domain: {state.intent.research_domain}"
            )

        prompt = (
            f"Research question:\n\"{query}\"\n{intent_ctx}\n\n"
            "Decompose into sub-questions with API assignments."
        )

        raw = await self.call_llm(prompt)
        parsed = safe_json_parse(raw)

        sub_questions: List[SubQuestion] = []

        if parsed is not None:
            # Handle {"sub_questions": [...]} or bare [...]
            items = parsed if isinstance(parsed, list) else parsed.get("sub_questions", parsed)
            if isinstance(items, list):
                for item in items:
                    try:
                        sub_questions.append(SubQuestion.model_validate(item))
                    except Exception:
                        logger.warning(
                            "Skipping malformed sub-question",
                            extra={"item": str(item)[:200]},
                        )

        # Fallback: single sub-question wrapping the whole query
        if not sub_questions:
            logger.warning("Decomposer fallback to single sub-question")
            sub_questions = [
                SubQuestion(
                    id="sq_1",
                    question=query,
                    api_source="arxiv",
                    priority=1,
                )
            ]

        sub_questions.sort(key=lambda sq: sq.priority)

        logger.info(
            "Query decomposed",
            extra={
                "count": len(sub_questions),
                "sources": list({sq.api_source for sq in sub_questions}),
            },
        )

        return {
            "sub_questions": sub_questions,
            "current_agent": self.name,
        }


async def decomposer_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Decomposer."""
    return await DecomposerAgent()(state)
