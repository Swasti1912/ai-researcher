"""
Paper Visualizer Agent.

Reads the uploaded paper (via RAG) and extracts structured data for
three visualization types:

  1. Concept Map   – key concepts/entities and their relationships
  2. Method Flow   – the paper's methodology as a step-by-step graph
  3. Results Chart – numerical findings for bar/pie charts (if any)

Usage::

    from app.agents.paper_visualizer import PaperVisualizerAgent
    agent = PaperVisualizerAgent()
    viz = await agent.visualize(session_id="abc123")
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOP_K = 10          # RAG chunks to feed the LLM
_MAX_CHARS = 8000    # total context chars sent to LLM


class PaperVisualizerAgent(BaseAgent):
    """
    Extract concept maps, method flows, and result charts from a paper.
    """

    name = "paper_visualizer"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert at reading academic research papers and extracting "
            "structured information for visualization.\n\n"
            "Given paper excerpts, extract THREE things and return ONLY valid JSON "
            "(no markdown, no explanation):\n\n"
            "{\n"
            '  "concept_map": {\n'
            '    "nodes": [\n'
            '      {"id": "c1", "label": "Short concept name", "type": "concept|finding|method|theory", "description": "1-sentence explanation"}\n'
            '    ],\n'
            '    "edges": [\n'
            '      {"source": "c1", "target": "c2", "label": "relationship verb (e.g. enables, uses, influences, leads to)"}\n'
            '    ]\n'
            '  },\n'
            '  "method_flow": {\n'
            '    "nodes": [\n'
            '      {"id": "s1", "label": "Step name", "description": "What was done in this step"}\n'
            '    ],\n'
            '    "edges": [\n'
            '      {"source": "s1", "target": "s2"}\n'
            '    ]\n'
            '  },\n'
            '  "charts": [\n'
            '    {\n'
            '      "type": "bar",\n'
            '      "title": "Chart title",\n'
            '      "data": [{"name": "Category", "value": 42}]\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "Rules:\n"
            "- concept_map: 6-12 nodes, keep labels SHORT (2-4 words). Connect meaningful relationships.\n"
            "- method_flow: 4-8 sequential steps. If the paper has no clear methodology, infer from the paper structure.\n"
            "- charts: Only include if the paper contains REAL numbers/percentages/scores. Empty array [] if none.\n"
            "- All node ids must be unique strings.\n"
            "- Return ONLY the JSON object, nothing else."
        )

    async def visualize(
        self, session_id: str
    ) -> Dict[str, Any]:
        """
        Extract visualization data for the paper in *session_id*.

        Args:
            session_id: Qdrant session scope for this paper.

        Returns:
            Dict with keys: concept_map, method_flow, charts.
        """
        kb = get_kb()

        # Pull broad coverage chunks — use multiple queries to get different parts
        queries = [
            "main concepts contributions key ideas",
            "methodology research design procedure steps",
            "results findings numbers statistics conclusions",
        ]
        seen, chunks = set(), []
        for q in queries:
            for chunk in kb.search(q, session_id=session_id, top_k=4):
                if chunk not in seen:
                    seen.add(chunk)
                    chunks.append(chunk)

        if not chunks:
            return _empty_viz()

        context = truncate("\n\n---\n\n".join(chunks), _MAX_CHARS)

        logger.info(
            "Visualizing paper",
            extra={"session_id": session_id, "chunks": len(chunks), "chars": len(context)},
        )

        prompt = (
            f"Paper excerpts:\n\n{context}\n\n"
            "Extract the concept map, method flow, and result charts as JSON."
        )

        raw = await self.call_llm(prompt)
        parsed = safe_json_parse(raw)

        if not parsed or not isinstance(parsed, dict):
            logger.warning("Visualizer: failed to parse JSON, returning empty")
            return _empty_viz()

        # Validate and fill defaults
        result = {
            "concept_map": _validate_graph(parsed.get("concept_map", {})),
            "method_flow": _validate_graph(parsed.get("method_flow", {})),
            "charts": _validate_charts(parsed.get("charts", [])),
        }

        logger.info(
            "Visualization complete",
            extra={
                "concepts": len(result["concept_map"]["nodes"]),
                "steps": len(result["method_flow"]["nodes"]),
                "charts": len(result["charts"]),
            },
        )
        return result

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use visualize() directly")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _empty_viz() -> Dict[str, Any]:
    return {"concept_map": {"nodes": [], "edges": []}, "method_flow": {"nodes": [], "edges": []}, "charts": []}


def _validate_graph(g: Any) -> Dict[str, Any]:
    if not isinstance(g, dict):
        return {"nodes": [], "edges": []}
    return {
        "nodes": g.get("nodes", []) if isinstance(g.get("nodes"), list) else [],
        "edges": g.get("edges", []) if isinstance(g.get("edges"), list) else [],
    }


def _validate_charts(charts: Any) -> List[Dict[str, Any]]:
    if not isinstance(charts, list):
        return []
    valid = []
    for c in charts:
        if isinstance(c, dict) and c.get("data") and isinstance(c["data"], list):
            valid.append(c)
    return valid
