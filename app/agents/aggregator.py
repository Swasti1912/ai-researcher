"""
Aggregator Agent.

Makes API calls for better context/understanding.  Dispatches each
sub-question to its assigned external API (arXiv, Semantic Scholar,
CrossRef), collects all results, and uses the LLM to synthesise
a unified research context.

Flow position::

    Decomposer ──→ **Aggregator** ──→ Reasoning
                        ↕
                   External APIs
"""

from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

from app.agents.base import BaseAgent
from app.config import get_settings
from app.state import APIResult, ResearchState, SubQuestion
from app.utils.constants import AgentName
from app.utils.exceptions import ExternalAPIError
from app.utils.helpers import truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 25.0  # seconds per API call


# ═══════════════════════════════════════════════════════════════════════════════
# External API Adapters
# ═══════════════════════════════════════════════════════════════════════════════


async def fetch_arxiv(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the arXiv API for papers matching *query*.

    Args:
        query:       Free-text search.
        max_results: Maximum papers to return.

    Returns:
        Dict ``{"papers": [{"title", "summary", "url", "authors"}]}``.

    Raises:
        ExternalAPIError: On HTTP or XML parsing failure.
    """
    settings = get_settings()
    url = (
        f"{settings.arxiv_base_url}?"
        f"search_query=all:{quote_plus(query)}"
        f"&start=0&max_results={max_results}&sortBy=relevance"
    )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        papers = []
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("a:summary", "", ns) or "").strip().replace("\n", " ")
            authors = [
                a.findtext("a:name", "", ns)
                for a in entry.findall("a:author", ns)
            ]
            link = ""
            for lnk in entry.findall("a:link", ns):
                if lnk.get("title") == "pdf":
                    link = lnk.get("href", "")
                    break
            if not link:
                for lnk in entry.findall("a:link", ns):
                    if lnk.get("type") == "text/html":
                        link = lnk.get("href", "")
                        break
            papers.append({
                "title": title,
                "summary": truncate(summary, 400),
                "url": link,
                "authors": authors[:5],
            })
        return {"papers": papers}

    except Exception as exc:
        raise ExternalAPIError("arxiv", message=str(exc)) from exc


async def fetch_semantic_scholar(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search Semantic Scholar for papers matching *query*.

    Args:
        query: Free-text search.
        limit: Max results.

    Returns:
        Dict ``{"papers": [{"title", "abstract", "year", "citations", "url"}]}``.

    Raises:
        ExternalAPIError: On failure.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,abstract,year,citationCount,url",
    }
    headers = {}
    key = get_settings().semantic_scholar_api_key
    if key:
        headers["x-api-key"] = key

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        papers = []
        for p in data.get("data", []):
            papers.append({
                "title": p.get("title", ""),
                "abstract": truncate(p.get("abstract") or "", 400),
                "year": p.get("year"),
                "citations": p.get("citationCount", 0),
                "url": p.get("url", ""),
            })
        return {"papers": papers}

    except Exception as exc:
        raise ExternalAPIError("semantic_scholar", message=str(exc)) from exc


async def fetch_crossref(query: str, rows: int = 5) -> Dict[str, Any]:
    """
    Search CrossRef for publication metadata.

    Args:
        query: Free-text search.
        rows:  Max results.

    Returns:
        Dict ``{"works": [{"title", "doi", "publisher", "type", "year"}]}``.

    Raises:
        ExternalAPIError: On failure.
    """
    url = f"{get_settings().crossref_base_url}/works"
    params = {"query": query, "rows": rows}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        works = []
        for item in data.get("message", {}).get("items", []):
            titles = item.get("title", ["Untitled"])
            year = None
            dp = item.get("published-print") or item.get("published-online")
            if dp and dp.get("date-parts"):
                year = dp["date-parts"][0][0] if dp["date-parts"][0] else None
            works.append({
                "title": titles[0] if titles else "Untitled",
                "doi": item.get("DOI", ""),
                "publisher": item.get("publisher", ""),
                "type": item.get("type", ""),
                "year": year,
            })
        return {"works": works}

    except Exception as exc:
        raise ExternalAPIError("crossref", message=str(exc)) from exc


_API_MAP = {
    "arxiv": fetch_arxiv,
    "semantic_scholar": fetch_semantic_scholar,
    "crossref": fetch_crossref,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregator Agent
# ═══════════════════════════════════════════════════════════════════════════════


class AggregatorAgent(BaseAgent):
    """
    Aggregate all results from different APIs.

    Responsibilities:
        1. Dispatch sub-questions to their assigned APIs concurrently.
        2. Normalise and collect responses as ``APIResult`` objects.
        3. Use the LLM to merge all results into a unified context string
           the Reasoning Agent can consume.
    """

    name = AgentName.AGGREGATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Aggregator Agent of an AI Research Assistant.\n\n"
            "You receive raw results from multiple research APIs "
            "(arXiv, Semantic Scholar, CrossRef).\n\n"
            "Your job:\n"
            "1. Merge overlapping information and deduplicate.\n"
            "2. Highlight the most relevant and recent findings.\n"
            "3. Produce a structured, factual summary (max ~800 words) "
            "   that a Reasoning Agent can use to build a final answer.\n\n"
            "Include paper titles and years when citing.\n"
            "Respond with the aggregated text only – no JSON, no markdown."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Call external APIs for each sub-question and synthesise results.

        Args:
            state: Must contain ``sub_questions`` from the Decomposer.

        Returns:
            ``{"api_results": list, "aggregated_context": str,
              "current_agent": str}``
        """
        sqs = state.sub_questions
        if not sqs:
            logger.warning("No sub-questions to aggregate")
            return {
                "api_results": [],
                "aggregated_context": "",
                "current_agent": self.name,
            }

        # Fire all API calls concurrently
        tasks = [self._call_api(sq) for sq in sqs]
        results: List[APIResult] = await asyncio.gather(*tasks)

        # Build raw context for LLM synthesis
        successful = [r for r in results if not r.error]
        raw = json.dumps(
            [r.model_dump() for r in successful],
            indent=2,
            default=str,
        )

        prompt = (
            f"Research query: {state.refined_query or state.original_query}\n\n"
            f"Raw API results ({len(successful)} successful, "
            f"{len(results) - len(successful)} failed):\n"
            f"{truncate(raw, 6000)}\n\n"
            "Synthesise into a coherent research context."
        )

        aggregated = await self.call_llm(prompt)

        logger.info(
            "Aggregation complete",
            extra={
                "total": len(results),
                "successful": len(successful),
                "failed": len(results) - len(successful),
            },
        )

        return {
            "api_results": results,
            "aggregated_context": aggregated,
            "current_agent": self.name,
        }

    @staticmethod
    async def _call_api(sq: SubQuestion) -> APIResult:
        """
        Dispatch a single sub-question to its assigned API.

        Returns an ``APIResult`` – error field populated on failure.
        """
        source = sq.api_source.lower().strip()
        fetcher = _API_MAP.get(source)

        if fetcher is None:
            return APIResult(
                source=source,
                query=sq.question,
                summary=f"No adapter for source '{source}'",
            )

        try:
            raw_data = await fetcher(sq.question)

            # Build human summary
            items = raw_data.get("papers", raw_data.get("works", []))
            lines = []
            for item in items[:5]:
                title = item.get("title", "Untitled")
                blurb = item.get("abstract") or item.get("summary") or ""
                lines.append(f"• {title}: {truncate(blurb, 200)}")

            return APIResult(
                source=source,
                query=sq.question,
                data=raw_data,
                summary="\n".join(lines) or "No results found.",
            )
        except ExternalAPIError as exc:
            logger.warning(
                "API call failed",
                extra={"source": source, "error": str(exc)},
            )
            return APIResult(
                source=source,
                query=sq.question,
                error=str(exc),
            )


async def aggregator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Aggregator."""
    return await AggregatorAgent()(state)
