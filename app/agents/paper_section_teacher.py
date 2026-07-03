"""
Paper Section Teacher — an extensive, tutor-style walkthrough of ONE section.

On demand (when a reader expands a section in the breakdown), this teaches that
section deeply: what it covers, the key ideas step by step, the intuition, and —
crucially — it explains any EQUATIONS (rendered as LaTeX) and FIGURES/CHARTS that
belong to that section, using the page-aware chunks + extracted figures.

Output is plain Markdown (with $$...$$ math), so it renders through the existing
Markdown + KaTeX pipeline. The section's figures are attached separately so the UI
can show the actual images alongside the teaching.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.utils.helpers import truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOP_K = 8
_MAX_CONTEXT = 5000


class PaperSectionTeacherAgent(BaseAgent):
    name = "paper_section_teacher"

    @property
    def system_prompt(self) -> str:
        return (
            "You are a patient expert tutor teaching ONE section of a research paper to a curious reader.\n"
            "Teach it EXTENSIVELY and clearly — do not just summarize.\n\n"
            "Your explanation MUST:\n"
            "1. Open with what this section is about and why it matters to the paper.\n"
            "2. Walk through the key ideas STEP BY STEP, explaining the how and the why (the intuition),\n"
            "   not just the what. Use short paragraphs and, where helpful, bullet lists.\n"
            "3. EQUATIONS: if the section contains any formula or mathematical relationship, present it as\n"
            "   display math using $$ ... $$ (valid KaTeX, no code fences), then explain what it means and\n"
            "   define each symbol in plain words. Inline math uses $ ... $.\n"
            "4. FIGURES/CHARTS/TABLES: for each figure listed in 'Figures available', explain what it shows,\n"
            "   how to read it, and the key takeaway. Refer to it by its label (e.g. 'Figure 2').\n"
            "5. End with a short 'Key takeaway' line.\n\n"
            "Use Markdown headings (###) to structure. Be thorough but do not invent facts that are not in\n"
            "the provided text. Output ONLY the Markdown lesson — no preamble, no JSON."
        )

    async def teach_section(
        self,
        session_id: str,
        section: str,
        summary: str = "",
    ) -> Dict[str, Any]:
        kb = get_kb()

        # Retrieve the section's most relevant chunks (with page numbers)
        query = f"{section}. {summary}".strip()
        hits = kb.search_with_meta(query, session_id=session_id, top_k=_TOP_K)
        body_hits = [h for h in hits if h.get("kind") != "figure_caption"]
        context = truncate("\n\n".join(h["text"] for h in body_hits), _MAX_CONTEXT) or "(no text found)"

        # Figures that live on this section's pages
        pages = {h["page_number"] for h in body_hits if h.get("page_number")}
        all_figs = kb.get_figures(session_id)
        section_figs = [f for f in all_figs if f.get("page") in pages]
        # Also pull captions the LLM should explain
        fig_caps = "\n".join(
            f"- {('Table' if f.get('kind') == 'table' else 'Figure')} on page {f['page']}: "
            f"{f.get('caption') or '(no caption)'}"
            for f in section_figs
        ) or "(none on this section's pages)"

        prompt = (
            f"Section to teach: \"{section}\"\n"
            f"One-line summary: {summary or '(none)'}\n\n"
            f"--- Relevant text from this section ---\n{context}\n\n"
            f"--- Figures available (explain each) ---\n{fig_caps}\n\n"
            "Teach this section now, following all the rules."
        )

        explanation = await self.call_llm(prompt)
        explanation = _strip_fences(explanation)

        logger.info(
            "Section taught",
            extra={"section": section[:40], "chunks": len(body_hits), "figures": len(section_figs)},
        )

        return {
            "section": section,
            "explanation": explanation,
            "figures": [
                {"fig_id": f["fig_id"], "page": f["page"],
                 "caption": f.get("caption", ""), "kind": f.get("kind", "figure")}
                for f in section_figs
            ],
            "pages": sorted(pages),
        }

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use teach_section() directly")


def _strip_fences(s: str) -> str:
    import re
    s = (s or "").strip()
    s = re.sub(r"^```(?:markdown)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()
