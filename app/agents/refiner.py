"""
Refiner Agent.

Transforms the raw user query into a precise, search-optimised
research question.  When a paper has been uploaded, the refined
query incorporates paper context.

Flow position::

    Orchestrator ──→ **Refiner** ──→ Intent
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent
from app.state import ResearchState
from app.utils.constants import AgentName
from app.utils.helpers import truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RefinerAgent(BaseAgent):
    """
    Modify the user prompt as per AI Researcher context.

    Responsibilities:
        1. Remove ambiguity and vague language from the query.
        2. Expand abbreviations and implicit domain jargon.
        3. Contextualise with uploaded paper when available.
        4. Output a self-contained 1-3 sentence research question.
    """

    name = AgentName.REFINER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Refiner Agent of an AI Research Assistant.\n\n"
            "Your ONLY job is to take the user's raw query and rewrite it "
            "as a clear, precise, and well-structured research question.\n\n"
            "Rules:\n"
            "- Remove vagueness; be specific.\n"
            "- Expand abbreviations (e.g. NLP → Natural Language Processing).\n"
            "- If a research paper is provided, contextualise the query "
            "  within the paper's topic and contributions.\n"
            "- Keep the output to 1–3 sentences.\n"
            "- Do NOT answer the question – only refine it.\n\n"
            "Respond with the refined question text ONLY. No preamble."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Refine the original query using optional paper context.

        Args:
            state: Must contain ``original_query``.

        Returns:
            ``{"refined_query": str, "current_agent": str}``
        """
        paper_ctx = ""
        if state.uploaded_paper_text:
            excerpt = truncate(state.uploaded_paper_text, 2000)
            paper_ctx = (
                f"\n\n--- Uploaded Paper ---\n"
                f"Filename: {state.uploaded_paper_filename or 'unknown'}\n"
                f"Excerpt:\n{excerpt}"
            )

        prompt = (
            f"User's original query:\n\"{state.original_query}\"\n"
            f"{paper_ctx}\n\n"
            "Rewrite this as a precise research question."
        )

        refined = await self.call_llm(prompt)
        refined = refined.strip().strip('"').strip("'")

        logger.info(
            "Query refined",
            extra={
                "original_len": len(state.original_query),
                "refined_len": len(refined),
            },
        )

        return {
            "refined_query": refined,
            "current_agent": self.name,
        }


async def refiner_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Refiner."""
    return await RefinerAgent()(state)
