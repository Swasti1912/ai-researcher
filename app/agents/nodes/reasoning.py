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
            "Write a comprehensive, well-structured research answer in plain Markdown.\n\n"
            "Rules:\n"
            "1. Use ## for main sections, ### for sub-sections.\n"
            "2. Cite sources inline, e.g. [Vaswani et al., 2017].\n"
            "3. Be thorough — explain concepts, mechanisms, and implications.\n"
            "4. Output ONLY the Markdown answer text.\n"
            "5. Do NOT wrap in JSON. Do NOT append code blocks, arrays, or references lists."
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

        import re as _re
        raw = await self.call_llm(prompt)
        vizs, refs = [], []
        answer = raw.strip()

        # Strip any ``` code fences
        answer = _re.sub(r'^```(?:json|markdown)?\s*\n?', '', answer)
        answer = _re.sub(r'\n?```\s*$', '', answer).strip()

        # If model still returned JSON despite instructions, extract the answer field
        if answer.lstrip().startswith('{'):
            parsed = safe_json(answer)
            if parsed and isinstance(parsed, dict):
                answer = parsed.get("answer", answer)
                vizs = parsed.get("visualizations", []) or []
                raw_refs = parsed.get("references", [])
                refs = [r if isinstance(r, str) else str(r) for r in raw_refs] if isinstance(raw_refs, list) else []

        # Find and remove any trailing JSON array/object (references list embedded in text)
        # Pattern: a standalone [ or { on its own line followed by a quoted string line
        m = _re.search(r'\n[ \t]*[\[\{][ \t]*\n[ \t]*"', answer)
        if m:
            answer = answer[:m.start()].rstrip()

        # Final sweep: strip lone trailing brackets/braces/fences one at a time
        for _ in range(5):
            prev = answer
            answer = _re.sub(r'\s*```\s*$', '', answer)
            answer = _re.sub(r'\s*[\]\}\[]\s*$', '', answer)
            if answer == prev:
                break
        answer = answer.strip()

        _log.info("Reasoning", extra={"ans_len": len(answer), "vizs": len(vizs), "refs": len(refs), "rag": len(rag)})
        return {"reasoning_output": answer, "visualizations": vizs, "rag_references": refs, "current_agent": self.name}


async def reasoning_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Reasoning()(state)
