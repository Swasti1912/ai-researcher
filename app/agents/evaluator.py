"""
Evaluator Agent.

Quality gate that critically scores the Reasoning Agent's output.
If the answer does not meet the quality threshold, signals the
Orchestrator to loop back for another iteration.

Flow position::

    Reasoning ──→ **Evaluator** ──→ END  (if satisfactory)
                                 ──→ Orchestrator (loop back)
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent
from app.state import EvaluationResult, ResearchState
from app.utils.constants import AgentName, WorkflowStatus
from app.utils.helpers import truncate
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EvaluatorAgent(BaseAgent):
    """
    Evaluate the quality of the synthesised research answer.

    Responsibilities:
        1. Score on four axes: relevance, completeness, accuracy, clarity.
        2. Produce a composite ``quality_score`` (0.0 – 1.0).
        3. Decide ``is_satisfactory`` (≥ 0.7 passes).
        4. If not satisfactory, flag ``needs_refinement`` with suggestions.
    """

    name = AgentName.EVALUATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Evaluator Agent of an AI Research Assistant.\n\n"
            "Critically assess the provided research answer against "
            "these criteria:\n"
            "  1. Relevance   – Does it address the question?\n"
            "  2. Completeness – Are all aspects covered?\n"
            "  3. Accuracy     – Are claims supported by data?\n"
            "  4. Clarity      – Is it well-structured and readable?\n\n"
            "Scoring:\n"
            "  quality_score: 0.0–1.0 (>= 0.7 passes)\n"
            "  is_satisfactory: true if quality_score >= 0.7\n"
            "  needs_refinement: true if another iteration would help\n\n"
            "Return ONLY valid JSON with keys: is_satisfactory (bool), "
            "quality_score (float), feedback (string), "
            "needs_refinement (bool), suggestions (list of strings)."
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Score the reasoning output and decide whether to loop back.

        Args:
            state: Must contain ``reasoning_output`` and ``refined_query``.

        Returns:
            Dict with ``evaluation``, ``final_answer``, ``status``,
            ``current_agent``.
        """
        query = state.refined_query or state.original_query
        answer = state.reasoning_output

        prompt = (
            f"Research question:\n\"{query}\"\n\n"
            f"Generated answer (truncated):\n{truncate(answer, 4000)}\n\n"
            f"Current iteration: {state.iteration} / {state.max_iterations}\n\n"
            "Evaluate this answer against the quality criteria."
        )

        evaluation = await self.call_llm_structured(prompt, EvaluationResult)

        # Force acceptance if we've exhausted iterations
        if state.iteration >= state.max_iterations:
            evaluation.is_satisfactory = True
            evaluation.needs_refinement = False
            logger.info(
                "Max iterations reached – forcing acceptance",
                extra={"iteration": state.iteration},
            )

        # Determine final status and answer
        if evaluation.is_satisfactory:
            status = WorkflowStatus.COMPLETED
            final_answer = answer
        else:
            status = WorkflowStatus.RUNNING
            final_answer = ""

        logger.info(
            "Evaluation complete",
            extra={
                "score": evaluation.quality_score,
                "satisfactory": evaluation.is_satisfactory,
                "needs_refinement": evaluation.needs_refinement,
                "iteration": state.iteration,
            },
        )

        return {
            "evaluation": evaluation,
            "final_answer": final_answer,
            "status": status,
            "current_agent": self.name,
        }


async def evaluator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Evaluator."""
    return await EvaluatorAgent()(state)
