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
            "You are an expert at reading academic papers and producing EDUCATIONAL visualizations.\n\n"
            "Given paper excerpts, return ONLY valid JSON with FOUR visualization objects.\n\n"
            "{\n"
            '  "architecture_diagram": {\n'
            '    "title": "e.g. Transformer Architecture or System Pipeline",\n'
            '    "nodes": [\n'
            '      {\n'
            '        "id": "n1",\n'
            '        "label": "Short component name",\n'
            '        "type": "input|embedding|attention|feedforward|normalization|encoder|decoder|conv|pooling|output|linear|general",\n'
            '        "layer": 0,\n'
            '        "description": "What this component does + key dimensions/params if known"\n'
            '      }\n'
            '    ],\n'
            '    "edges": [\n'
            '      {"source": "n1", "target": "n2", "label": "e.g. 512-dim, residual, or empty"}\n'
            '    ]\n'
            '  },\n'
            '  "concept_map": {\n'
            '    "nodes": [\n'
            '      {"id": "c1", "label": "Short concept", "type": "concept|finding|method|theory", "description": "1-sentence explanation"}\n'
            '    ],\n'
            '    "edges": [\n'
            '      {"source": "c1", "target": "c2", "label": "enables|uses|influences|leads to|compares to"}\n'
            '    ]\n'
            '  },\n'
            '  "method_flow": {\n'
            '    "nodes": [\n'
            '      {"id": "s1", "label": "Step name", "description": "What was done"}\n'
            '    ],\n'
            '    "edges": [{"source": "s1", "target": "s2"}]\n'
            '  },\n'
            '  "charts": [\n'
            '    {"type": "bar", "title": "Chart title", "data": [{"name": "Label", "value": 42}]}\n'
            '  ]\n'
            "}\n\n"
            "ARCHITECTURE DIAGRAM RULES (most important — read carefully):\n"
            "- Assign each node a 'layer' integer: 0 = input/raw data, increasing numbers = deeper processing.\n"
            "- Nodes on the SAME layer (same integer) are shown SIDE BY SIDE horizontally.\n"
            "- Model architecture papers (Transformer, BERT, CNN, RNN, GAN, etc.): extract the ACTUAL component stack.\n"
            "  Example Transformer layers: 0=Input Tokens, 1=Embeddings+Positional, 2=Multi-Head Attention,\n"
            "  3=Add & Norm, 4=Feed-Forward, 5=Add & Norm, 6=Output (repeat encoder for decoder).\n"
            "- Non-model papers: show the system pipeline stages as layers (data collection → processing → analysis → output).\n"
            "- Include REAL dimensions/params in descriptions and edge labels when mentioned in the paper.\n"
            "- Use 6-14 nodes. Keep labels SHORT (2-4 words). Descriptions explain the WHY.\n"
            "- Parallel components (e.g., Q/K/V projections, multiple attention heads) = same layer number.\n\n"
            "CONCEPT MAP RULES:\n"
            "- 6-12 nodes. Focus on ideas, not architecture components (those go in architecture_diagram).\n"
            "- Edge labels must be verbs: enables, uses, influences, motivates, extends, contrasts with.\n\n"
            "METHOD FLOW RULES:\n"
            "- 4-8 sequential steps of the experimental/research methodology.\n\n"
            "CHARTS RULES:\n"
            "- Only include if the paper contains REAL numbers/scores/percentages. Empty [] if none.\n\n"
            "Return ONLY the JSON object. No markdown fences, no explanation."
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
            "model architecture components layers encoder decoder attention embedding",
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

        # ── Call 1: architecture diagram (focused prompt) ────────────────────
        arch_prompt = (
            f"Paper excerpts:\n\n{context}\n\n"
            "Extract ONLY the architecture_diagram as JSON. "
            "Return ONLY this JSON object, nothing else:\n"
            '{"architecture_diagram": {"title": "...", "nodes": [...], "edges": [...]}}'
        )
        arch_raw = await self.call_llm(arch_prompt)
        arch_parsed = safe_json_parse(arch_raw) or {}

        # ── Call 2: concept map + method flow ────────────────────────────────
        rest_prompt = (
            f"Paper excerpts:\n\n{context}\n\n"
            "Return ONLY this compact JSON (max 6 concept nodes, max 5 method steps, "
            "labels ≤4 words, descriptions ≤8 words, no trailing text):\n"
            '{"concept_map":{"nodes":[{"id":"c1","label":"...","type":"concept|finding|method|theory","description":"..."}],'
            '"edges":[{"source":"c1","target":"c2","label":"enables"}]},'
            '"method_flow":{"nodes":[{"id":"s1","label":"...","description":"..."}],'
            '"edges":[{"source":"s1","target":"s2"}]},'
            '"charts":[{"type":"bar","title":"...","data":[{"name":"...","value":0}]}]}'
        )
        rest_raw = await self.call_llm(rest_prompt)
        rest_parsed = safe_json_parse(rest_raw) or {}

        parsed = {**arch_parsed, **rest_parsed}

        if not parsed:
            logger.warning("Visualizer: failed to parse JSON from both calls, returning empty")
            return _empty_viz()

        # Validate and fill defaults
        result = {
            "architecture_diagram": _validate_arch(parsed.get("architecture_diagram", {})),
            "concept_map": _validate_graph(parsed.get("concept_map", {})),
            "method_flow": _validate_graph(parsed.get("method_flow", {})),
            "charts": _validate_charts(parsed.get("charts", [])),
        }

        logger.info(
            "Visualization complete",
            extra={
                "arch": len(result["architecture_diagram"]["nodes"]),
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
    return {
        "architecture_diagram": {"title": "", "nodes": [], "edges": []},
        "concept_map": {"nodes": [], "edges": []},
        "method_flow": {"nodes": [], "edges": []},
        "charts": [],
    }


def _validate_graph(g: Any) -> Dict[str, Any]:
    if not isinstance(g, dict):
        return {"nodes": [], "edges": []}
    return {
        "nodes": g.get("nodes", []) if isinstance(g.get("nodes"), list) else [],
        "edges": g.get("edges", []) if isinstance(g.get("edges"), list) else [],
    }


def _validate_arch(a: Any) -> Dict[str, Any]:
    if not isinstance(a, dict):
        return {"title": "", "nodes": [], "edges": []}
    nodes = a.get("nodes", []) if isinstance(a.get("nodes"), list) else []
    # Ensure each node has a layer int
    for n in nodes:
        if not isinstance(n.get("layer"), int):
            n["layer"] = 0
    return {
        "title": a.get("title", ""),
        "nodes": nodes,
        "edges": a.get("edges", []) if isinstance(a.get("edges"), list) else [],
    }


def _validate_charts(charts: Any) -> List[Dict[str, Any]]:
    if not isinstance(charts, list):
        return []
    valid = []
    for c in charts:
        if isinstance(c, dict) and c.get("data") and isinstance(c["data"], list):
            valid.append(c)
    return valid
