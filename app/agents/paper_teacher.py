"""
Paper Teacher Agent — explains a paper like a patient, expert teacher.

Generates a structured lesson plan: big picture → concept chapters →
key takeaway. Each chapter has an explanation in plain English, an
analogy, and a single memorable takeaway. The goal is progressive
understanding — even a non-expert can follow.

Output schema:
  lesson_title      ← "{Paper Title}: A Complete Walkthrough"
  big_picture       ← what problem is being solved and why it matters
  prerequisite_knowledge ← what the reader needs to know going in
  chapters          ← ordered list of concept lessons
    number, title, explanation, analogy, key_takeaway
  how_it_all_fits   ← paragraph connecting all chapters together
  paper_in_one_sentence ← the simplest possible summary
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.utils.helpers import safe_json_parse, truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_PAPER_CHARS = 10_000


class PaperTeacherAgent(BaseAgent):

    name = "paper_teacher"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert professor who makes complex technical papers accessible to anyone.\n"
            "Your goal is to teach this paper the way a great teacher would: start with the big picture,\n"
            "build concepts progressively, use vivid analogies, and leave the student with a clear mental model.\n\n"
            "Given paper text, produce a structured lesson plan as ONLY valid JSON:\n\n"
            "{\n"
            '  "lesson_title": "A Complete Walkthrough of [paper title]",\n'
            '  "big_picture": "2-3 sentences: What problem does this paper solve? Why does it matter? Who cares?",\n'
            '  "prerequisite_knowledge": "What a reader needs to know before reading this paper (1 sentence, be honest)",\n'
            '  "chapters": [\n'
            '    {\n'
            '      "number": 1,\n'
            '      "title": "Short chapter title (3-6 words)",\n'
            '      "explanation": "Detailed teacher-style explanation of this concept. Write at least 3-4 sentences. Explain the HOW and WHY, not just the what. Use plain English.",\n'
            '      "analogy": "A vivid real-world analogy starting with \'Think of it like...\' or \'Imagine...\' that makes this concrete.",\n'
            '      "key_takeaway": "One sentence: the single most important thing to remember from this chapter."\n'
            '    }\n'
            '  ],\n'
            '  "how_it_all_fits": "A paragraph explaining how all the chapters connect — the narrative arc of the paper.",\n'
            '  "paper_in_one_sentence": "Explain the entire paper in one sentence a smart 15-year-old would understand."\n'
            "}\n\n"
            "Rules:\n"
            "- Generate 5-8 chapters covering the paper's main concepts in logical learning order.\n"
            "- Chapter 1 should always set the stage: the problem being solved.\n"
            "- Each chapter's explanation must be at least 3 sentences — don't be superficial.\n"
            "- Analogies must be concrete and memorable, not vague.\n"
            "- Write in second person ('You might wonder...', 'Notice that...').\n"
            "- Return ONLY valid JSON."
        )

    async def teach(
        self,
        paper_text: str,
        filename: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a teacher-style lesson plan for the paper.

        If summary is provided (from PaperSummarizerAgent), prepend key
        metadata so the teacher agent has richer context without re-reading
        the full text.
        """
        truncated = truncate(paper_text, _MAX_PAPER_CHARS)
        was_truncated = len(paper_text) > _MAX_PAPER_CHARS

        # Enrich context with summary metadata if available
        context_prefix = ""
        if summary:
            title    = summary.get("title", "")
            domain   = summary.get("domain", "")
            innov    = summary.get("core_innovation", "")
            concepts = summary.get("key_concepts", [])
            concept_names = ", ".join(c.get("name", "") for c in concepts[:8] if c.get("name"))
            context_prefix = (
                f"Paper: {title}\n"
                f"Domain: {domain}\n"
                f"Core innovation: {innov}\n"
                f"Key technical concepts: {concept_names}\n\n"
            )

        prompt = (
            f"{context_prefix}"
            f"{'[Note: paper truncated to first ~10 000 chars]' if was_truncated else ''}\n\n"
            f"Paper text:\n\n{truncated}\n\n"
            "Generate the complete teacher-style lesson plan JSON."
        )

        logger.info("Teaching paper", extra={"file": filename, "chars": len(paper_text)})

        raw = await self.call_llm(prompt)
        parsed = safe_json_parse(raw)

        if parsed and isinstance(parsed, dict):
            lesson = parsed
        else:
            logger.warning("PaperTeacher: failed to parse JSON, using fallback")
            lesson = {
                "lesson_title": f"Walkthrough of {filename or 'paper'}",
                "big_picture": raw[:300] if raw else "Unable to generate lesson.",
                "prerequisite_knowledge": "",
                "chapters": [],
                "how_it_all_fits": "",
                "paper_in_one_sentence": "",
            }

        # Ensure chapters is always a list
        if not isinstance(lesson.get("chapters"), list):
            lesson["chapters"] = []

        # Ensure each chapter has required fields
        for i, ch in enumerate(lesson["chapters"]):
            ch.setdefault("number", i + 1)
            ch.setdefault("title", f"Chapter {i + 1}")
            ch.setdefault("explanation", "")
            ch.setdefault("analogy", "")
            ch.setdefault("key_takeaway", "")

        logger.info("Lesson ready", extra={"chapters": len(lesson["chapters"])})
        return lesson

    async def execute(self, state: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise NotImplementedError("Use teach() directly")
