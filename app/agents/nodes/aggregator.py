"""
Aggregator Agent.

Aggregates all the results from different APIs.  Dispatches each
sub-question to its assigned API concurrently, collects responses,
and uses the LLM to synthesise a unified research context.

Position: Decomposer → **Aggregator** → Reasoning.
              ↕
         External APIs (arXiv, Semantic Scholar, CrossRef)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from app.agents.nodes.base import BaseAgent
from app.services.external_apis import API_REGISTRY
from app.state import APIResult, ResearchState, SubQuestion
from app.utils.constants import AgentName
from app.utils.exceptions import ExternalAPIError
from app.utils.helpers import truncate
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Aggregator(BaseAgent):
    """
    Make API calls for better context/understanding.

    Behaviour:
      1. Fire all sub-question API calls concurrently.
      2. Collect into ``APIResult`` objects (with error handling).
      3. Invoke the LLM to merge raw results into a coherent summary.
    """

    name = AgentName.AGGREGATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Aggregator Agent of an AI Research Assistant.\n\n"
            "You receive raw results from multiple research APIs.\n"
            "Merge, deduplicate, and summarise the most relevant findings\n"
            "into a factual, well-structured context (~600 words max).\n"
            "Cite paper titles and years. Reply with text only."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Call APIs and aggregate results."""
        sqs = state.sub_questions
        if not sqs:
            return {"api_results": [], "aggregated_context": "", "current_agent": self.name}

        # Fire API calls with a small stagger for rate-limited APIs (arXiv/S2)
        # to avoid concurrent 429s. Group by source; arXiv gets 1 s delay between calls.
        arxiv_sqs  = [sq for sq in sqs if sq.api_source.lower() == "arxiv"]
        other_sqs  = [sq for sq in sqs if sq.api_source.lower() != "arxiv"]

        results: List[APIResult] = []

        # Other APIs (S2, CrossRef, web) run concurrently
        other_results = await asyncio.gather(*[self._fetch(sq) for sq in other_sqs])
        results.extend(other_results)

        # arXiv runs sequentially with 1 s gap to avoid rate-limiting
        for i, sq in enumerate(arxiv_sqs):
            if i > 0:
                await asyncio.sleep(1.0)
            results.append(await self._fetch(sq))

        ok = [r for r in results if not r.error]
        raw = json.dumps([r.model_dump() for r in ok], indent=2, default=str)

        prompt = (
            f"Query: {state.refined_query or state.original_query}\n\n"
            f"Raw API results ({len(ok)} ok, {len(results)-len(ok)} failed):\n"
            f"{truncate(raw, 6000)}\n\nSynthesise."
        )
        aggregated = await self.call_llm(prompt)
        _log.info("Aggregated", extra={"ok": len(ok), "fail": len(results)-len(ok)})
        return {"api_results": results, "aggregated_context": aggregated, "current_agent": self.name}

    @staticmethod
    async def _fetch(sq: SubQuestion) -> APIResult:
        """Call one API for one sub-question."""
        src = sq.api_source.lower().strip()
        fn = API_REGISTRY.get(src)
        if fn is None:
            return APIResult(source=src, query=sq.question, summary=f"No adapter for '{src}'")
        try:
            data = await fn(sq.question)
            items = data.get("papers", data.get("works", []))
            lines = [f"• {it.get('title','?')}: {truncate(it.get('abstract') or it.get('summary',''), 200)}" for it in items[:5]]
            return APIResult(source=src, query=sq.question, data=data, summary="\n".join(lines) or "No results")
        except ExternalAPIError as exc:
            _log.warning("API fail", extra={"src": src, "err": str(exc)})
            return APIResult(source=src, query=sq.question, error=str(exc))


async def aggregator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Aggregator()(state)
