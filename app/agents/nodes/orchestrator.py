"""
Orchestrator Agent.

Entry point of the pipeline.  Validates the user query, assigns a
request ID on first entry, and increments the iteration counter
on loop-back from the Evaluator.

Position: first node; receives loop-back edge from Evaluator.
"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.nodes.base import BaseAgent
from app.state import ResearchState
from app.utils.constants import AgentName, WorkflowStatus
from app.utils.exceptions import InputValidationError
from app.utils.helpers import gen_id
from app.utils.logger import get_logger

_log = get_logger(__name__)


class _Orchestrator(BaseAgent):
    """
    Validate user input and initialise or advance the workflow.

    Behaviour on **first entry**:
      1. Reject empty queries.
      2. Assign ``request_id``, set ``iteration = 1``.
      3. (Optional) call the LLM to assess query validity / scope.

    Behaviour on **re-entry** (Evaluator loop-back):
      1. Increment ``iteration``.
      2. Mark status as ``LOOPING``.
    """

    name = AgentName.ORCHESTRATOR

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Orchestrator of an AI Research Assistant.\n"
            "Briefly assess the user's research query for validity.\n"
            "Reply with JSON: {\"valid\": true/false, \"scope\": \"narrow|medium|broad\", \"note\": \"...\"}"
        )

    async def execute(self, state: ResearchState) -> Dict[str, Any]:
        """Validate and bootstrap / advance the pipeline."""
        if not state.original_query or not state.original_query.strip():
            raise InputValidationError("Query is empty")

        # Re-entry from evaluator
        if state.iteration > 0:
            _log.info("Re-entry", extra={"iter": state.iteration + 1, "rid": state.request_id})
            return {"current_agent": self.name, "iteration": state.iteration + 1, "status": WorkflowStatus.LOOPING}

        # First entry
        paper = ""
        if state.uploaded_paper_text:
            paper = f"\n[Paper: {state.uploaded_paper_filename or '?'}] {state.uploaded_paper_text[:400]}"
        await self.call_llm(f"Query: {state.original_query}{paper}\nAssess validity.")

        rid = gen_id()
        _log.info("Workflow initialised", extra={"rid": rid})
        return {"request_id": rid, "current_agent": self.name, "iteration": 1, "status": WorkflowStatus.RUNNING}


async def orchestrator_node(state: ResearchState) -> Dict[str, Any]:
    """LangGraph node wrapper."""
    return await _Orchestrator()(state)
