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

import re
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOP_K = 10          # RAG chunks to feed the LLM
_MAX_CHARS = 8000    # total context chars sent to LLM


# Prompt that turns paper content into a set of Mermaid diagrams.
# We use a delimited text format (NOT JSON) because Mermaid code is full of
# quotes, brackets and newlines that break JSON escaping.
_MERMAID_PROMPT = """You are an expert at explaining research papers with clear DIAGRAMS.

Paper excerpts:
{context}

Create 3 to 4 Mermaid.js diagrams that VISUALLY EXPLAIN this paper's key ideas.
Use ONLY `flowchart TD`, `flowchart LR`, or `sequenceDiagram` (do NOT use mindmap).
Pick the most illuminating diagrams for THIS paper, e.g.:
  - The core method / pipeline as a flowchart (how data flows through the approach)
  - The model architecture as a flowchart with stages (input to output)
  - How the key concepts relate to each other as a flowchart
  - A step-by-step process as a sequenceDiagram (if there are actors/steps over time)

STRICT MERMAID RULES (follow exactly or it will not render):
1. Each diagram MUST start with one of: flowchart TD, flowchart LR, sequenceDiagram, or mindmap.
2. Node ids are simple alphanumerics (A, B, n1). Put ALL human text in double-quoted labels:
   CORRECT:  A["Multi-Head Attention"] --> B["Add and Norm"]
   WRONG:    A[Multi-Head Attention (8 heads)] --> B
3. NEVER put parentheses ( ), colons, or slashes inside a label. Use plain words: "8 heads" not "(8 heads)".
4. Edges: A --> B   or labelled:  A -->|"projects to"| B
5. Flowcharts: 5 to 10 nodes. You may group stages with subgraphs, but NEVER point an
   edge directly at a subgraph — connect to a node INSIDE it:
   CORRECT:
     B["Embeddings"] --> C["Self-Attention"]
     subgraph Encoder
       C["Self-Attention"] --> D["Feed Forward"]
     end
   WRONG:  B --> subgraph Encoder
6. One edge per line. Do NOT chain like A --> B --> C on a single line; write two lines.
7. sequenceDiagram: use  participant U as User  then  U->>M: message text
8. No markdown, no HTML, no comments, no mindmap.

OUTPUT FORMAT — return each diagram as a block in EXACTLY this shape, blocks separated by a line
containing only three equals signs (===). Do NOT wrap anything in JSON or code fences:

TITLE: <short title>
DESC: <one sentence describing what this diagram shows>
TYPE: flowchart
MERMAID:
flowchart TD
  A["Input"] --> B["Process"]
  B --> C["Output"]
===
TITLE: <next diagram title>
DESC: ...
TYPE: sequence
MERMAID:
sequenceDiagram
  participant U as User
  U->>S: request

Begin now. Output ONLY the blocks."""


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

        # ── Call 1: Mermaid concept & workflow diagrams (delimited text) ─────
        diagrams_raw = await self.call_llm(_MERMAID_PROMPT.format(context=context))
        concept_diagrams = _parse_diagram_blocks(diagrams_raw)

        # ── Call 2: numeric result charts (JSON) ────────────────────────────
        charts_prompt = (
            f"Paper excerpts:\n\n{context}\n\n"
            "Extract ONLY numeric results as bar/pie charts. If the paper reports "
            "specific numbers/scores/percentages, return them. If none, return an empty list.\n"
            "Return ONLY this JSON, nothing else:\n"
            '{"charts":[{"type":"bar","title":"...","data":[{"name":"...","value":0}]}]}'
        )
        charts_raw = await self.call_llm(charts_prompt)
        charts_parsed = safe_json_parse(charts_raw) or {}

        # Validate and fill defaults (legacy graph fields kept empty for API compat)
        result = {
            "concept_diagrams": concept_diagrams,
            "charts": _validate_charts(charts_parsed.get("charts", [])),
            "architecture_diagram": {"title": "", "nodes": [], "edges": []},
            "concept_map": {"nodes": [], "edges": []},
            "method_flow": {"nodes": [], "edges": []},
        }

        if not result["concept_diagrams"] and not result["charts"]:
            logger.warning("Visualizer: no diagrams or charts parsed")

        logger.info(
            "Visualization complete",
            extra={
                "diagrams": len(result["concept_diagrams"]),
                "charts": len(result["charts"]),
            },
        )
        return result

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use visualize() directly")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _empty_viz() -> Dict[str, Any]:
    return {
        "concept_diagrams": [],
        "charts": [],
        "architecture_diagram": {"title": "", "nodes": [], "edges": []},
        "concept_map": {"nodes": [], "edges": []},
        "method_flow": {"nodes": [], "edges": []},
    }


# Diagram types we accept from the model
_DIAGRAM_TYPES = {"flowchart", "sequence", "mindmap", "graph", "architecture", "workflow"}


def _parse_diagram_blocks(raw: str) -> List[Dict[str, Any]]:
    """
    Parse the delimited diagram format:

        TITLE: ...
        DESC: ...
        TYPE: flowchart
        MERMAID:
        <mermaid code ...>
        ===
        TITLE: ...

    Robust to quotes/newlines in the Mermaid code (unlike JSON).
    """
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    # Strip any stray outer code fences
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    blocks = re.split(r"\n\s*={3,}\s*\n", text)
    out: List[Dict[str, Any]] = []
    for block in blocks:
        if "MERMAID:" not in block.upper():
            continue
        title, desc, dtype = "Diagram", "", "flowchart"
        # Split header (TITLE/DESC/TYPE) from the mermaid code
        parts = re.split(r"MERMAID:\s*\n?", block, maxsplit=1, flags=re.IGNORECASE)
        head = parts[0]
        code = parts[1] if len(parts) > 1 else ""
        for line in head.splitlines():
            m = re.match(r"\s*(TITLE|DESC|TYPE)\s*:\s*(.+)", line, re.IGNORECASE)
            if not m:
                continue
            key, val = m.group(1).upper(), m.group(2).strip()
            if key == "TITLE":
                title = val[:120]
            elif key == "DESC":
                desc = val[:300]
            elif key == "TYPE":
                v = val.lower().split()[0] if val else "flowchart"
                dtype = v if v in _DIAGRAM_TYPES else "flowchart"
        code = _sanitize_mermaid(code)
        if code:
            out.append({"title": title, "description": desc, "type": dtype, "mermaid": code})
    return out[:6]


def _sanitize_mermaid(code: str) -> str:
    """
    Light cleanup of common LLM Mermaid mistakes so it parses client-side:
      - strip ``` fences
      - normalise escaped newlines
      - ensure a valid diagram header exists
    """
    import re
    s = code.strip()
    # Strip markdown code fences
    s = re.sub(r"^```(?:mermaid)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    # Convert any literal "\n" sequences into real newlines
    if "\\n" in s and "\n" not in s:
        s = s.replace("\\n", "\n")
    # Must start with a recognised diagram declaration
    first = s.lstrip().split("\n", 1)[0].strip().lower()
    valid_starts = ("flowchart", "graph", "sequencediagram", "mindmap",
                    "classdiagram", "statediagram", "erdiagram", "journey")
    if not first.startswith(valid_starts):
        return ""

    # Fix the common LLM mistake: `X --> subgraph Name` (invalid). Convert to a
    # proper `subgraph Name` and re-attach the edge to the first inner node.
    if "--> subgraph" in s or "-->subgraph" in s:
        s = _fix_subgraph_edges(s)
    # Split chained edges `A --> B --> C` into separate statements (more robust).
    s = _split_chained_edges(s)
    return s


def _split_chained_edges(code: str) -> str:
    out: List[str] = []
    for line in code.split("\n"):
        # Only split plain chained edges (avoid labelled edges that contain '|')
        if line.count("-->") >= 2 and "|" not in line:
            indent = line[: len(line) - len(line.lstrip())]
            segs = [seg.strip() for seg in line.split("-->")]
            for i in range(len(segs) - 1):
                if segs[i] and segs[i + 1]:
                    out.append(f"{indent}{segs[i]} --> {segs[i + 1]}")
        else:
            out.append(line)
    return "\n".join(out)


def _fix_subgraph_edges(code: str) -> str:
    lines = code.split("\n")
    out: List[str] = []
    pending_src: Optional[str] = None
    for line in lines:
        m = re.match(r"^(\s*)(\w+)\s*-->\s*subgraph\s+(.+)$", line)
        if m:
            indent, src, name = m.groups()
            pending_src = src
            out.append(f"{indent}subgraph {name}")
            continue
        if pending_src:
            nm = re.match(r"^\s*(\w+)", line)
            if nm:
                out.append(line)
                out.append(f"{pending_src} --> {nm.group(1)}")
                pending_src = None
                continue
        out.append(line)
    return "\n".join(out)


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
