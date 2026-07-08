"""
Figure Explainer — explains ONE figure/table/chart from a paper using vision.

The reader clicks a figure; we send the *actual figure image* plus the paper's
text that surrounds/references it to a vision-capable model, which explains what
the figure shows and what it means in context. Supports follow-up questions
(a short conversation scoped to that one figure).

Output is Markdown (with $$...$$ math) so it renders through the existing
Markdown + KaTeX pipeline.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.knowledge_base import get_kb
from app.utils.helpers import truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOP_K = 8
_MAX_CONTEXT = 4000


class FigureExplainerAgent(BaseAgent):
    name = "figure_explainer"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert who explains ONE figure, chart, or table from a research "
            "paper to a curious reader. You are given the actual figure image plus the "
            "paper's text that references or surrounds it.\n\n"
            "Explain in clear Markdown (use $$...$$ for any math). Cover, as relevant:\n"
            "1. What kind of figure it is and what it shows at a glance.\n"
            "2. READ the figure: axes, units, legend, labels, curves/bars, trends, "
            "comparisons, and any notable values you can actually see.\n"
            "3. What it means in the context of THIS paper — connect it to what the "
            "surrounding text says about it.\n"
            "4. The key takeaway: why this figure matters to the paper's argument.\n\n"
            "Be specific and grounded in BOTH the image and the provided context. Never "
            "invent numbers you cannot see. If the image is unavailable (caption-only "
            "table), explain from the caption and context. Keep strictly to THIS figure."
        )

    def _context(self, session_id: str, caption: str, page: Optional[int]) -> str:
        kb = get_kb()
        query = caption or (f"figure on page {page}" if page else "figure")
        try:
            hits = kb.search_with_meta(query=query, session_id=session_id, top_k=_TOP_K)
        except Exception:
            hits = []
        # Prefer text that lives on the figure's own page.
        same = [h for h in hits if h.get("page_number") == page]
        other = [h for h in hits if h.get("page_number") != page]
        ordered = same + other
        return truncate("\n\n".join(h.get("text", "") for h in ordered), _MAX_CONTEXT) \
            or "(no surrounding text found)"

    async def explain(
        self,
        session_id: str,
        fig_id: str,
        question: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, str]:
        kb = get_kb()
        fig = kb.get_figure(session_id, fig_id)
        if not fig:
            raise ValueError(f"Figure '{fig_id}' not found")

        caption = (fig.get("caption") or "").strip()
        page = fig.get("page")
        png = fig.get("png")
        context = self._context(session_id, caption, page)

        text_block = (
            f"Figure caption: {caption or '(none provided)'}\n"
            f"Page in paper: {page}\n\n"
            f"--- Paper text that references / surrounds this figure ---\n{context}\n"
        )
        if question:
            text_block += (
                f"\nThe reader asks about this figure:\n\"{question}\"\n"
                "Answer their question using the figure image and the context above."
            )
        else:
            text_block += "\nExplain this figure now, following all the rules."

        content: List[Dict[str, Any]] = [{"type": "text", "text": text_block}]
        if png:
            b64 = base64.b64encode(png).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

        messages: List[Any] = [SystemMessage(content=self.system_prompt)]
        # Prior turns so follow-up questions have the conversation context.
        for turn in (history or [])[-6:]:
            role, c = turn.get("role"), turn.get("content", "")
            if not c:
                continue
            messages.append(HumanMessage(content=c) if role == "user" else AIMessage(content=c))
        messages.append(HumanMessage(content=content))

        resp = await self._llm.ainvoke(messages)
        explanation = (getattr(resp, "content", "") or "").strip()
        logger.info("Figure explained", extra={
            "session_id": session_id, "fig_id": fig_id,
            "has_image": bool(png), "followup": bool(question),
        })
        return {"fig_id": fig_id, "explanation": explanation}

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use explain() directly")
