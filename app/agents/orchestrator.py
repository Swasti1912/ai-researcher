"""
Orchestrator Agent.

The entry-point of the LangGraph pipeline.  It validates the incoming
user query, bootstraps tracking fields (request_id, iteration), and
on re-entry from the Evaluator increments the iteration counter.

Flow position::

    ┌──────────────┐
    │ Orchestrator  │ ──→ Refiner ──→ …
    └──────────────┘
          ↑ (loop-back from Evaluator)
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent
from app.state import ResearchState
from app.utils.constants import AgentName, WorkflowStatus
from app.utils.exceptions import AgentExecutionError, InputValidationError
from app.utils.helpers import generate_request_id
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    """
    Validate user input and initialise / advance the workflow.

    Responsibilities:
        1. Reject empty or invalid queries.
        2. On first entry: assign a ``request_id``, set iteration to 1.
        3. On re-entry (from Evaluator loop-back): increment iteration.
        4. Optionally use the LLM to assess query scope.
    """

    name = AgentName.ORCHESTRATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Orchestrator of an AI Research Assistant.\n"
            "Assess the user's research query for validity and scope.\n\n"
            "Respond with a JSON object:\n"
            '{"is_valid": true, "scope": "narrow|medium|broad", '
            '"assessment": "brief note"}\n\n'
            "If the query is too vague or not a research question, "
            'set "is_valid" to false with an explanation.'
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """
        Validate input and bootstrap or advance the workflow state.

        Args:
            state: Current pipeline state.

        Returns:
            Dict with ``request_id``, ``iteration``, ``status``,
            ``current_agent`` updates.

        Raises:
            InputValidationError: When the query is empty.
        """
        if not state.original_query or not state.original_query.strip():
            raise InputValidationError(
                message="Query cannot be empty",
                detail="Provide a research question or upload a paper.",
            )

        is_reentry = state.iteration > 0

        if is_reentry:
            logger.info(
                "Orchestrator re-entry (evaluator loop-back)",
                extra={
                    "request_id": state.request_id,
                    "iteration": state.iteration + 1,
                },
            )
            return {
                "current_agent": self.name,
                "iteration": state.iteration + 1,
                "status": WorkflowStatus.LOOPING,
            }

        # First entry – optionally validate via LLM
        paper_note = ""
        if state.uploaded_paper_text:
            paper_note = (
                f"\n\n[Uploaded paper: {state.uploaded_paper_filename or 'N/A'}]\n"
                f"First 500 chars: {state.uploaded_paper_text[:500]}"
            )

        await self.call_llm(
            f"Research query: {state.original_query}{paper_note}\n\nAssess validity and scope."
        )

        rid = generate_request_id()
        logger.info(
            "Orchestrator initialised workflow",
            extra={
                "request_id": rid,
                "query_len": len(state.original_query),
                "has_paper": state.uploaded_paper_text is not None,
            },
        )

        return {
            "request_id": rid,
            "current_agent": self.name,
            "iteration": 1,
            "status": WorkflowStatus.RUNNING,
        }


async def orchestrator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node function for the Orchestrator."""
    return await OrchestratorAgent()(state)
