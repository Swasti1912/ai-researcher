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
            "Teach it EXTENSIVELY, elaborately, and clearly — this is a deep lesson, NOT a summary. Aim for a\n"
            "thorough multi-part explanation a motivated beginner could learn the section from.\n\n"
            "Your explanation MUST:\n"
            "1. Open with what this section is about and why it matters to the paper's overall story.\n"
            "2. Build up the necessary intuition first — motivate the problem, then introduce ideas in a\n"
            "   logical order. Assume the reader is smart but new to this; define jargon the first time it\n"
            "   appears, and use analogies or concrete mini-examples to make abstract ideas tangible.\n"
            "3. Walk through the key ideas STEP BY STEP, explaining the how and the WHY (the reasoning and\n"
            "   design choices), not just the what. Use short paragraphs, and bullet lists where helpful.\n"
            "4. EQUATIONS: if the section contains any formula or mathematical relationship, present it as\n"
            "   display math using $$ ... $$ (valid KaTeX, no code fences), then explain what it means,\n"
            "   define each symbol in plain words, and give the intuition for why it takes that form.\n"
            "   Inline math uses $ ... $.\n"
            "5. FIGURES/CHARTS/TABLES: for each figure listed in 'Figures available', explain what it shows,\n"
            "   how to read it (axes/legend/columns), and the key takeaway. Refer to it by its label\n"
            "   (e.g. 'Figure 2'). Tell the reader they can click a figure for a deeper, image-based explanation.\n"
            "6. Call out any subtle points, common misconceptions, or limitations mentioned in the text.\n"
            "7. End with a short '### Key takeaways' list (2–4 bullets).\n\n"
            "Use Markdown headings (###) to structure into a few labelled parts. Be thorough and elaborate,\n"
            "but do NOT invent facts that are not supported by the provided text. Output ONLY the Markdown\n"
            "lesson — no preamble, no JSON."
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
