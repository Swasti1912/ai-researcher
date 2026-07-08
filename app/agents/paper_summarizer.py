"""
Paper Summarizer Agent — deep technical understanding.

Produces a rich, structured summary designed for readers who want to
fully understand a technical paper, not just skim it.

Output schema:
  title, authors, domain, technical_depth,
  core_innovation,          ← the single key idea
  tldr,                     ← one sentence
  abstract_summary,         ← 2-3 sentences
  section_breakdown,        ← [{section, summary}] per major section
  key_concepts,             ← [{name, definition, importance}] glossary
  methodology,
  key_results,
  limitations,
  future_work,
  prior_work_comparison     ← how this differs from what came before
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_PAPER_CHARS = 12_000


class PaperSummarizerAgent(BaseAgent):

    name = "paper_summarizer"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert academic paper analyst specialising in deeply understanding "
            "technical research papers and making them accessible.\n\n"
            "Given paper text, produce a RICH, DETAILED structured analysis. "
            "Return ONLY valid JSON — no markdown, no explanation — with this exact schema:\n\n"
            "{\n"
            '  "title": "Exact paper title",\n'
            '  "authors": "Author list as string",\n'
            '  "domain": "Research domain (e.g. NLP, Computer Vision, RL)",\n'
            '  "technical_depth": "beginner|intermediate|expert",\n'
            '  "core_innovation": "The single most important new idea in 1-2 sentences. What did they invent/discover that nobody had before?",\n'
            '  "tldr": "One sentence capturing the paper in plain English",\n'
            '  "abstract_summary": "3-4 sentence expanded summary",\n'
            '  "section_breakdown": [\n'
            '    {"section": "Introduction", "summary": "What this section covers and why it matters"}\n'
            '  ],\n'
            '  "key_concepts": [\n'
            '    {\n'
            '      "name": "Short concept name (2-4 words)",\n'
            '      "definition": "Clear 1-2 sentence definition as used in this paper",\n'
            '      "importance": "Why this concept is central to understanding the paper"\n'
            '    }\n'
            '  ],\n'
            '  "methodology": "Detailed description of the approach — techniques, datasets, experimental setup, evaluation metrics",\n'
            '  "key_results": "Specific findings with numbers where available",\n'
            '  "limitations": "Honest assessment of what the paper does not address or gets wrong",\n'
            '  "future_work": "Directions the authors suggest or that are obvious next steps",\n'
            '  "prior_work_comparison": "How this paper differs from or improves on previous approaches"\n'
            "}\n\n"
            "Rules:\n"
            "- key_concepts: extract 6-10 concepts. For technical papers include ALL major technical terms.\n"
            "- section_breakdown: cover every major section you can identify (Introduction, Related Work, Method, Experiments, Conclusion, etc.).\n"
            "- Be precise and factual — quote specific numbers, model names, dataset names.\n"
            "- technical_depth: 'beginner' if anyone can read it, 'expert' if it needs deep domain knowledge.\n"
            "- Return ONLY the JSON object."
        )

    async def summarize(
        self,
        paper_text: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        truncated = truncate(paper_text, _MAX_PAPER_CHARS)
        was_truncated = len(paper_text) > _MAX_PAPER_CHARS

        prompt = (
            f"{'[Note: paper truncated to first ~12 000 chars]' if was_truncated else ''}\n\n"
            f"Paper text:\n\n{truncated}\n\n"
            "Produce the detailed structured JSON analysis."
        )

        logger.info(
            "Summarising paper",
            extra={"file": filename, "chars": len(paper_text), "truncated": was_truncated},
        )

        raw = await self.call_llm(prompt)
        parsed = safe_json_parse(raw)

        if parsed and isinstance(parsed, dict):
            # Smaller LLMs sometimes embed the full JSON inside a text field.
            # Detect: if core_innovation or tldr looks like a JSON object, try
            # parsing it — that's the real summary.
            for field in ("core_innovation", "tldr", "abstract_summary"):
                val = parsed.get(field, "")
                if isinstance(val, str) and val.strip().startswith("{"):
                    inner = safe_json_parse(val.strip())
                    if isinstance(inner, dict) and "title" in inner and "core_innovation" in inner:
                        parsed = inner
                        break
                elif isinstance(val, dict) and "title" in val:
                    parsed = val
                    break
            summary = parsed
        else:
            logger.warning("Failed to parse structured summary, using fallback")
            summary = {
                "title": filename or "Unknown",
                "authors": "Unknown",
                "domain": "",
                "technical_depth": "intermediate",
                "core_innovation": raw[:200] if raw else "",
                "tldr": raw[:200] if raw else "Summary unavailable",
                "abstract_summary": raw[:500] if raw else "",
                "section_breakdown": [],
                "key_concepts": [],
                "methodology": "",
                "key_results": "",
                "limitations": "",
                "future_work": "",
                "prior_work_comparison": "",
            }

        # Ensure key_concepts is always a list
        if not isinstance(summary.get("key_concepts"), list):
            summary["key_concepts"] = []
        if not isinstance(summary.get("section_breakdown"), list):
            summary["section_breakdown"] = []

        logger.info("Summary complete", extra={"title": summary.get("title")})
        return summary

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use summarize() directly")
