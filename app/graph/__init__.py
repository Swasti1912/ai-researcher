"""
LangGraph Workflow Definition.

Compiles the directed state graph matching the architecture diagram::

    Orchestrator → Refiner → Intent → Decomposer → Aggregator
                                                       ↓
                                                   Reasoning → Evaluator
                                                       ↑           │
                                                       └───────────┘
                                                      (loop if score < 0.7)

The ``_should_continue`` function on the Evaluator's outgoing edge
decides between END and looping back to the Orchestrator.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents import (
    aggregator_node, decomposer_node, evaluator_node,
    intent_node, orchestrator_node, reasoning_node, refiner_node,
)
from app.state import ResearchState
from app.utils.constants import WorkflowStatus
from app.utils.logger import get_logger

_log = get_logger(__name__)


def _should_continue(state: ResearchState) -> str:
    """
    Conditional edge after Evaluator.

    Returns ``"end"`` to terminate or ``"orchestrator"`` to loop.
    """
    if state.status == WorkflowStatus.COMPLETED:
        return "end"
    if state.iteration >= state.max_iterations:
        return "end"
    if state.evaluation and state.evaluation.needs_refinement:
        _log.info("Loop back", extra={"rid": state.request_id, "iter": state.iteration, "score": state.evaluation.quality_score})
        return "orchestrator"
    return "end"


def build_graph() -> StateGraph:
    """Construct and compile the research pipeline graph."""
    g = StateGraph(ResearchState)

    g.add_node("orchestrator", orchestrator_node)
    g.add_node("refiner",      refiner_node)
    g.add_node("intent",       intent_node)
    g.add_node("decomposer",   decomposer_node)
    g.add_node("aggregator",   aggregator_node)
    g.add_node("reasoning",    reasoning_node)
    g.add_node("evaluator",    evaluator_node)

    g.set_entry_point("orchestrator")
    g.add_edge("orchestrator", "refiner")
    g.add_edge("refiner",      "intent")
    g.add_edge("intent",       "decomposer")
    g.add_edge("decomposer",   "aggregator")
    g.add_edge("aggregator",   "reasoning")
    g.add_edge("reasoning",    "evaluator")

    g.add_conditional_edges("evaluator", _should_continue, {"end": END, "orchestrator": "orchestrator"})

    compiled = g.compile()
    _log.info("Graph compiled")
    return compiled


_g = None


def get_graph():
    """Singleton compiled graph."""
    global _g
    if _g is None:
        _g = build_graph()
    return _g
