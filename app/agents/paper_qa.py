"""
Paper Q&A Agent — deep-dive technical explanations.

Answers questions about an uploaded paper with:
  • RAG retrieval from the paper's own chunks (scoped by session_id)
  • Concurrent arXiv + Semantic Scholar search for external context
  • Structured JSON response including follow-up question suggestions
    so the user can naturally dive deeper without knowing what to ask next.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.agents.aggregator import fetch_arxiv, fetch_semantic_scholar
from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOP_K_CHUNKS = 6
_MAX_CHUNK_CHARS = 500
_MAX_EXT_PAPERS = 4


class PaperQAAgent(BaseAgent):
    """
    Answer detailed questions about an uploaded paper.

    Returns a structured response with:
      - answer           : detailed, cited explanation
      - paper_evidence   : direct quotes/paraphrases from the paper
      - related_papers   : external papers found via arXiv / Semantic Scholar
      - confidence       : high | medium | low
      - follow_up_questions : 3 suggested next questions to go deeper
    """

    name = "paper_qa"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert research mentor helping someone deeply understand "
            "a technical paper they have uploaded.\n\n"
            "You receive:\n"
            "  • The user's question\n"
            "  • Relevant excerpts from the paper (RAG passages)\n"
            "  • Related external papers from arXiv / Semantic Scholar\n\n"
            "Your response must:\n"
            "1. Answer in DEPTH — explain the concept fully, not just surface-level.\n"
            "   For technical concepts: describe how it works step by step, include\n"
            "   any relevant equations or algorithms in plain English, and explain\n"
            "   the intuition behind design choices.\n"
            "2. Ground every claim in the paper: use [Paper] to cite the uploaded paper,\n"
            "   or the title for external sources.\n"
            "3. Structure long answers with headers (### Section) for readability.\n"
            "4. Bridge to the bigger picture: how does this concept fit into the\n"
            "   broader research landscape?\n"
            "5. Suggest 3 follow-up questions that would naturally help the user\n"
            "   go one level deeper on this topic.\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            '  "answer": "Your detailed, well-structured explanation (use ### headers for sections)",\n'
            '  "paper_evidence": ["Direct quote or close paraphrase from the paper", ...],\n'
            '  "related_papers": [{"title": "...", "relevance": "Why it relates"}, ...],\n'
            '  "confidence": "high|medium|low",\n'
            '  "follow_up_questions": [\n'
            '    "Specific follow-up question 1 to go deeper",\n'
            '    "Specific follow-up question 2 on a related subtopic",\n'
            '    "Specific follow-up question 3 connecting to broader context"\n'
            '  ]\n'
            "}\n\n"
            "If the paper does not cover the question, say so clearly and rely on external sources."
        )

    async def answer(
        self,
        question: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Answer *question* using RAG over the paper + external API search.

        Returns dict with: answer, paper_evidence, related_papers,
        confidence, follow_up_questions, rag_chunks_used, external_papers_found.
        """
        kb = get_kb()

        # 1. RAG: retrieve relevant chunks (with page metadata) scoped to this session
        rag_hits: List[Dict[str, Any]] = []
        if session_id or kb.chunk_count > 0:
            rag_hits = kb.search_with_meta(question, session_id=session_id, top_k=_TOP_K_CHUNKS)
        rag_chunks = [h["text"] for h in rag_hits]
        rag_pages = [h["page_number"] for h in rag_hits if h.get("page_number")]

        rag_text = (
            "\n---\n".join(truncate(c, _MAX_CHUNK_CHARS) for c in rag_chunks)
            if rag_chunks
            else "(No relevant passages found in the uploaded paper)"
        )

        # 2. External search: arXiv + Semantic Scholar concurrently
        arxiv_data, ss_data = await asyncio.gather(
            _safe_fetch(fetch_arxiv, question, _MAX_EXT_PAPERS),
            _safe_fetch(fetch_semantic_scholar, question, _MAX_EXT_PAPERS),
        )
        ext_papers = _format_external(arxiv_data, ss_data)

        logger.info(
            "PaperQA inputs ready",
            extra={"rag_chunks": len(rag_chunks), "has_external": bool(ext_papers)},
        )

        # 3. LLM synthesis
        prompt = (
            f'User question:\n"{question}"\n\n'
            f"--- Relevant passages from the uploaded paper ---\n{rag_text}\n\n"
            f"--- Related external papers ---\n{ext_papers}\n\n"
            "Produce a detailed, cited answer with follow-up questions."
        )

        raw = await self.call_llm(prompt)
        parsed = safe_json_parse(raw)

        if parsed and isinstance(parsed, dict):
            result = parsed
        else:
            logger.warning("PaperQA: failed to parse JSON, salvaging answer text")
            result = {
                "answer": _salvage_answer(raw),
                "paper_evidence": [],
                "related_papers": [],
                "confidence": "medium",
                "follow_up_questions": [],
            }

        # The model sometimes nests the answer as an object/array (or returns
        # malformed JSON we salvaged above). Always hand the UI clean prose —
        # never a raw JSON blob.
        result["answer"] = _as_text(result.get("answer", "")).strip()

        # Ensure follow_up_questions is always a list of strings
        fuq = result.get("follow_up_questions", [])
        if not isinstance(fuq, list):
            fuq = []
        result["follow_up_questions"] = [q for q in fuq if isinstance(q, str)][:3]

        # Attach a best-effort source page to each evidence quote so the UI can
        # jump to it in the PDF. Evidence is free-text, so match by overlap.
        result["paper_evidence"] = _attach_pages(result.get("paper_evidence", []), rag_hits)
        result["rag_pages"] = rag_pages

        result["rag_chunks_used"] = len(rag_chunks)
        result["external_papers_found"] = len([l for l in ext_papers.splitlines() if l.strip()])
        return result

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use answer() directly")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _unescape(s: str) -> str:
    return (s.replace("\\n", "\n").replace("\\t", "\t")
             .replace('\\"', '"').replace("\\\\", "\\"))


def _as_text(val: Any) -> str:
    """Flatten a string / list / dict answer into readable markdown prose."""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "\n\n".join(_as_text(v) for v in val if v is not None)
    if isinstance(val, dict):
        return "\n\n".join(_as_text(v) for v in val.values() if v is not None)
    return str(val)


def _salvage_answer(raw: str) -> str:
    """
    Best-effort readable text when the LLM's reply isn't valid JSON.

    The flaky model sometimes emits e.g. ``{"answer": {"### Heading", "body…"}}``
    (invalid JSON). Rather than dumping that blob into the chat, pull the answer
    field's quoted fragments and join them into prose.
    """
    import re

    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()

    if s.lstrip().startswith("{") and '"answer"' in s:
        m = re.search(
            r'"answer"\s*:\s*(.*?)'
            r'(?:,\s*"(?:paper_evidence|related_papers|confidence|follow_up_questions)"\s*:|\}\s*$)',
            s, re.DOTALL,
        )
        if m:
            chunk = m.group(1).strip()
            # A single quoted string → the answer directly.
            if chunk.startswith('"') and chunk.rstrip().endswith('"') and chunk.count('"') == 2:
                return _unescape(chunk.strip().strip('"'))
            # Otherwise collect every quoted fragment and join.
            parts = re.findall(r'"((?:[^"\\]|\\.)*)"', chunk)
            if parts:
                text = "\n\n".join(_unescape(p) for p in parts if p.strip())
                if text.strip():
                    return text
            cleaned = chunk.strip("{}[]\" \n")
            if cleaned:
                return _unescape(cleaned)
    return s


def _attach_pages(evidence: Any, rag_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Turn evidence (list of quote strings) into ``[{"text", "page"}]`` by matching
    each quote to the retrieved chunk with the highest text overlap. Falls back to
    the top-ranked chunk's page. Idempotent if evidence is already objects.
    """
    if not isinstance(evidence, list):
        return []
    top_page = None
    for h in rag_hits:
        if h.get("page_number"):
            top_page = h["page_number"]
            break

    out: List[Dict[str, Any]] = []
    for item in evidence:
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        if not text.strip():
            continue
        page = item.get("page") if isinstance(item, dict) else None
        if not page:
            probe = text.strip()[:60].lower()
            best_page, best_len = top_page, 0
            for h in rag_hits:
                ct = (h.get("text") or "").lower()
                if probe and probe in ct and len(ct) > best_len:
                    best_page, best_len = h.get("page_number") or top_page, len(ct)
            page = best_page
        out.append({"text": text, "page": page})
    return out


async def _safe_fetch(fetcher, query: str, limit: int) -> Dict[str, Any]:
    try:
        return await fetcher(query, limit)
    except Exception as exc:
        logger.warning("External fetch failed", extra={"err": str(exc)})
        return {}


def _format_external(arxiv: Dict[str, Any], ss: Dict[str, Any]) -> str:
    lines: List[str] = []
    for p in arxiv.get("papers", []):
        lines.append(f"[arXiv] {p.get('title','')}: {truncate(p.get('summary') or '', 150)}")
    for p in ss.get("papers", []):
        lines.append(f"[S2] {p.get('title','')} ({p.get('year','')}): {truncate(p.get('abstract') or '', 150)}")
    return "\n".join(lines) if lines else "(No external papers found)"
