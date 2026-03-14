"""
Decomposer Agent.

Decomposes complex questions, domain into simpler ones.  Each
sub-question is assigned an API source and a priority rank.

Position: Intent → **Decomposer** → Aggregator.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.nodes.base import BaseAgent
from app.state import ResearchState, SubQuestion
from app.utils.constants import AgentName
from app.utils.helpers import safe_json
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Decomposer(BaseAgent):
    """
    Break the refined query into 2-6 API-routable sub-questions.

    Behaviour:
      1. Analyse the intent classification and domain.
      2. Generate focused, self-contained sub-questions.
      3. Assign each to: arxiv, semantic_scholar, crossref, or web_search.
      4. Rank by priority (1 = highest).
    """

    name = AgentName.DECOMPOSER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Decomposer Agent of an AI Research Assistant.\n\n"
            "Break the research question into 2–6 simpler sub-questions.\n"
            "Assign each an api_source: arxiv, semantic_scholar, crossref, web_search.\n\n"
            "Return ONLY a JSON array:\n"
            '[{"id":"sq_1","question":"...","api_source":"arxiv","priority":1}, ...]'
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Decompose into sub-questions."""
        q = state.refined_query or state.original_query
        ctx = ""
        if state.intent:
            ctx = f"\nIntent: {state.intent.primary_intent} | Domain: {state.intent.research_domain}"

        raw = await self.call_llm(f'Research question: "{q}"{ctx}\n\nDecompose.')
        parsed = safe_json(raw)

        sqs: List[SubQuestion] = []
        if parsed is not None:
            items = parsed if isinstance(parsed, list) else parsed.get("sub_questions", parsed) if isinstance(parsed, dict) else []
            if isinstance(items, list):
                for item in items:
                    try:
                        sqs.append(SubQuestion.model_validate(item))
                    except Exception:
                        pass

        if not sqs:
            _log.warning("Decomposer fallback")
            sqs = [SubQuestion(id="sq_1", question=q, api_source="arxiv", priority=1)]

        sqs.sort(key=lambda s: s.priority)
        _log.info("Decomposed", extra={"count": len(sqs), "sources": list({s.api_source for s in sqs})})
        return {"sub_questions": sqs, "current_agent": self.name}


async def decomposer_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Decomposer()(state)
