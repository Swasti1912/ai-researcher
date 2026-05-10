"""
Reasoning Agent.

Takes care of any reasoning and Visualization.  Combines aggregated
API context with Knowledge Base (RAG) passages to produce a
comprehensive, cited answer with optional data visualisations.

Position: Aggregator → **Reasoning** → Evaluator.
                          ↕
                    Knowledge Base (RAG)
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.nodes.base import BaseAgent
from app.knowledge_base import get_kb
from app.state import ResearchState
from app.utils.constants import AgentName
from app.utils.helpers import safe_json, truncate
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Reasoning(BaseAgent):
    """
    Synthesise the final research answer.

    Behaviour:
      1. Retrieve top-k RAG passages from the Knowledge Base.
      2. Combine with aggregated API context and intent metadata.
      3. Produce a structured answer with citations.
      4. Suggest data visualisations where the data supports it.
    """

    name = AgentName.REASONING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Reasoning Agent of an AI Research Assistant.\n\n"
            "You receive:\n"
            "  • Refined question + intent + domain\n"
            "  • Aggregated API context\n"
            "  • Knowledge base (RAG) passages\n\n"
            "Task:\n"
            "1. Synthesise a comprehensive answer citing sources.\n"
            "2. Structure with clear sections.\n"
            "3. If data supports it, include a 'visualizations' list.\n\n"
            "Return JSON: {\"answer\":\"...\",\"visualizations\":[{\"type\":\"bar|line|pie|table\","
            "\"title\":\"...\",\"data\":{...}}],\"references\":[\"...\"]}\n\n"
            "If you cannot produce JSON, return the answer as plain text."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Build the research answer."""
        q = state.refined_query or state.original_query

        # RAG retrieval
        kb = get_kb()
        rag = kb.search(q, top_k=5)
        rag_text = "\n---\n".join(rag) if rag else "(no KB passages)"

        intent_s = state.intent.primary_intent if state.intent else "N/A"
        domain_s = state.intent.research_domain if state.intent else "N/A"

        prompt = (
            f'Question: "{q}"\nIntent: {intent_s} | Domain: {domain_s}\n\n'
            f"--- Aggregated Context ---\n{truncate(state.aggregated_context, 4000)}\n\n"
            f"--- RAG Passages ---\n{truncate(rag_text, 2000)}\n\nSynthesise."
        )

        raw = await self.call_llm(prompt)
        answer, vizs, refs = raw, [], []
        parsed = safe_json(raw)
        if parsed and isinstance(parsed, dict):
            answer = parsed.get("answer", raw)
            vizs = parsed.get("visualizations", [])
            raw_refs = parsed.get("references", [])
            # Ensure refs is always List[str] — LLMs sometimes return dicts
            if isinstance(raw_refs, list):
                refs = [
                    r if isinstance(r, str) else (r.get("title") or r.get("text") or str(r))
                    for r in raw_refs
                ]
            elif isinstance(raw_refs, dict):
                refs = list(raw_refs.values())
            # Ensure vizs is always a list
            if not isinstance(vizs, list):
                vizs = []

        _log.info("Reasoning", extra={"ans_len": len(answer), "vizs": len(vizs), "refs": len(refs), "rag": len(rag)})
        return {"reasoning_output": answer, "visualizations": vizs, "rag_references": refs, "current_agent": self.name}


async def reasoning_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Reasoning()(state)
