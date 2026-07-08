"""
Evaluator Agent.

Quality gate: scores the Reasoning Agent's output on relevance,
completeness, accuracy, and clarity.  If the quality score is below
0.7, signals the Orchestrator to loop back.

Position: Reasoning → **Evaluator** → END or → Orchestrator (loop).
"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.nodes.base import BaseAgent
from app.state import EvaluationResult, ResearchState
from app.utils.constants import AgentName, WorkflowStatus
from app.utils.helpers import truncate
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Evaluator(BaseAgent):
    """
    Evaluate answer quality and control the feedback loop.

    Behaviour:
      1. Score on relevance, completeness, accuracy, clarity.
      2. Composite quality_score 0-1 (>= 0.7 = pass).
      3. If below threshold AND iterations remain → loop back.
      4. At max iterations → force acceptance.
    """

    name = AgentName.EVALUATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Evaluator Agent of an AI Research Assistant.\n\n"
            "Assess the answer on: relevance, completeness, accuracy, clarity.\n"
            "quality_score: 0.0–1.0 (>= 0.7 passes).\n\n"
            "Return ONLY JSON: {is_satisfactory: bool, quality_score: float, "
            "feedback: str, needs_refinement: bool, suggestions: [str]}"
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Score the answer and decide loop-back."""
        q = state.refined_query or state.original_query
        prompt = (
            f'Question: "{q}"\n\n'
            f"Answer (truncated):\n{truncate(state.reasoning_output, 4000)}\n\n"
            f"Iteration {state.iteration}/{state.max_iterations}. Evaluate."
        )

        ev = await self.call_llm_structured(prompt, EvaluationResult)

        # Safety: force pass at max iterations
        if state.iteration >= state.max_iterations:
            ev.is_satisfactory = True
            ev.needs_refinement = False
            _log.info("Max iter reached – forcing pass")

        status = WorkflowStatus.COMPLETED if ev.is_satisfactory else WorkflowStatus.RUNNING
        final = state.reasoning_output if ev.is_satisfactory else ""

        _log.info("Eval", extra={"score": ev.quality_score, "pass": ev.is_satisfactory, "iter": state.iteration})
        return {"evaluation": ev, "final_answer": final, "status": status, "current_agent": self.name}


async def evaluator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Evaluator()(state)
