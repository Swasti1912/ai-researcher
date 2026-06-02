"""
Reasoning Agent.

Takes care of any reasoning and visualization.  Synthesises the
aggregated API context, knowledge-base passages (RAG), and intent
into a comprehensive research answer with optional data
visualisation suggestions.

Flow position::

    Aggregator ──→ **Reasoning** ──→ Evaluator
                       ↕
                  Knowledge Base (RAG)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.state import ResearchState
from app.utils.constants import AgentName
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ReasoningAgent(BaseAgent):
    """
    Synthesise a comprehensive research answer with reasoning.

    Responsibilities:
        1. Query the Knowledge Base (RAG) for relevant uploaded-paper
           passages.
        2. Combine RAG context + aggregated API data.
        3. Produce a thorough, cited, well-structured answer.
        4. Suggest data visualisations (bar, line, pie, table) where
           the data supports it.
    """

    name = AgentName.REASONING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Reasoning Agent of an AI Research Assistant.\n\n"
            "You receive:\n"
            "  • A refined research question\n"
            "  • Its intent classification\n"
            "  • Aggregated data from external APIs\n"
            "  • Relevant passages from a knowledge base (RAG)\n\n"
            "Write a comprehensive, well-structured research answer in plain Markdown.\n\n"
            "Rules:\n"
            "1. Use ## for main sections, ### for sub-sections.\n"
            "2. Cite sources inline by paper title (e.g. [Vaswani et al., 2017]).\n"
            "3. Be thorough — explain concepts, mechanisms, and implications.\n"
            "4. End your answer naturally. Do NOT append JSON, arrays, code blocks,\n"
            "   or any non-Markdown content after the answer text.\n"
            "5. Output ONLY the Markdown answer — no preamble, no JSON wrapper."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Perform deep reasoning to build the research answer.

        Args:
            state: Must contain ``aggregated_context`` and ``intent``.

        Returns:
            Dict with ``reasoning_output``, ``visualizations``,
            ``rag_references``, ``current_agent``.
        """
        query = state.refined_query or state.original_query

        # 1. RAG retrieval from knowledge base
        kb = get_kb()
        rag_chunks = kb.search(query, top_k=5)
        rag_text = (
            "\n---\n".join(rag_chunks) if rag_chunks else "(No knowledge base passages)"
        )

        # 2. Build comprehensive prompt
        intent_str = "N/A"
        domain_str = "N/A"
        if state.intent:
            intent_str = state.intent.primary_intent
            domain_str = state.intent.research_domain

        prompt = (
            f"Research question:\n\"{query}\"\n\n"
            f"Intent: {intent_str}\n"
            f"Domain: {domain_str}\n\n"
            f"--- Aggregated API Context ---\n"
            f"{truncate(state.aggregated_context, 4000)}\n\n"
            f"--- Knowledge Base (RAG) Passages ---\n"
            f"{truncate(rag_text, 2000)}\n\n"
            "Synthesise a comprehensive, well-cited research answer."
        )

        raw = await self.call_llm(prompt)

        # 3. Extract clean markdown — strip all JSON artifacts
        import re
        visualizations: List[Dict[str, Any]] = []
        references: List[str] = []
        answer = raw.strip()

        # Strip outer ``` fences
        answer = re.sub(r'^```(?:json|markdown)?\s*\n?', '', answer)
        answer = re.sub(r'\n?```\s*$', '', answer).strip()

        # If JSON slipped through, try to extract the answer field
        if answer.lstrip().startswith("{"):
            parsed = safe_json_parse(answer)
            if parsed and isinstance(parsed, dict):
                answer = parsed.get("answer", answer)
                visualizations = parsed.get("visualizations", [])
                references = parsed.get("references", [])

        # Aggressive cleanup: find where the real Markdown text ends.
        # Models often append a JSON references array after the answer.
        # Strategy: find the last position that ends a real sentence or
        # Markdown block, before any JSON structure starts.
        #
        # Pattern: a JSON array of references looks like:
        #   \n[\n  "Source...",\n  "Source..."\n]\n}
        # OR an inline list like:
        #   \n  [\n    "..."\n  ]\n}
        #
        # Find the earliest standalone [ or { that begins a trailing JSON block.
        _json_start = re.search(
            r'\n\s*[\[\{]\s*\n\s*"',   # opening [ or { followed by a quoted line
            answer
        )
        if _json_start:
            answer = answer[:_json_start.start()].rstrip()

        # Also strip any remaining trailing code fences or lone brackets/braces
        answer = re.sub(r'\s*```\s*$', '', answer)
        answer = re.sub(r'\s*[\]\}\[]\s*$', '', answer)
        answer = answer.strip()

        logger.info(
            "Reasoning complete",
            extra={
                "answer_len": len(answer),
                "visualizations": len(visualizations),
                "references": len(references),
                "rag_chunks_used": len(rag_chunks),
            },
        )

        return {
            "reasoning_output": answer,
            "visualizations": visualizations,
            "rag_references": references,
            "current_agent": self.name,
        }


async def reasoning_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Reasoning Agent."""
    return await ReasoningAgent()(state)
