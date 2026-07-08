"""
State Module.

Defines ``ResearchState`` — the typed dataclass that flows through
every LangGraph node — along with Pydantic sub-models for structured
agent outputs (IntentResult, SubQuestion, APIResult, EvaluationResult).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pydantic sub-models ──────────────────────────────────────────────────────


class IntentResult(BaseModel):
    """Output of the Intent classification agent."""
    primary_intent: str = Field(..., description="why/how/when/what/comparison/methodology/survey/general")
    confidence: float = Field(..., ge=0.0, le=1.0)
    research_domain: str = Field(default="")
    sub_intents: List[str] = Field(default_factory=list)


class SubQuestion(BaseModel):
    """Single decomposed sub-question from the Decomposer."""
    id: str
    question: str
    api_source: str = "arxiv"
    priority: int = Field(default=1, ge=1, le=5)


class APIResult(BaseModel):
    """Normalised external API result."""
    source: str
    query: str = ""
    data: Any = None
    summary: str = ""
    error: Optional[str] = None


class EvaluationResult(BaseModel):
    """Quality-gate output from the Evaluator."""
    is_satisfactory: bool
    quality_score: float = Field(..., ge=0.0, le=1.0)
    feedback: str = ""
    needs_refinement: bool = False
    suggestions: List[str] = Field(default_factory=list)


# ── Main graph state ─────────────────────────────────────────────────────────


@dataclass
class ResearchState:
    """
    Central state flowing through every LangGraph node.

    Each agent reads what it needs and returns a dict of updates;
    LangGraph merges them back automatically.
    """

    # User inputs
    request_id: str = ""
    original_query: str = ""
    uploaded_paper_text: Optional[str] = None
    uploaded_paper_filename: Optional[str] = None

    # Orchestrator book-keeping
    current_agent: str = ""
    iteration: int = 0
    max_iterations: int = 3
    status: str = "pending"
    error_message: Optional[str] = None

    # Refiner
    refined_query: str = ""

    # Intent
    intent: Optional[IntentResult] = None

    # Decomposer
    sub_questions: List[SubQuestion] = field(default_factory=list)

    # Aggregator
    api_results: List[APIResult] = field(default_factory=list)
    aggregated_context: str = ""

    # Reasoning
    reasoning_output: str = ""
    visualizations: List[Dict[str, Any]] = field(default_factory=list)
    rag_references: List[str] = field(default_factory=list)

    # Evaluator
    evaluation: Optional[EvaluationResult] = None

    # Final
    final_answer: str = ""

    # Observability trace
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)

    # ── Serialisation ────────────────────────────────────────────────

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict safe for JSON API responses."""
        # Ensure rag_references is always List[str]
        safe_refs = []
        for r in self.rag_references:
            if isinstance(r, str):
                safe_refs.append(r)
            elif isinstance(r, dict):
                safe_refs.append(r.get("title") or r.get("text") or str(r))
            else:
                safe_refs.append(str(r))

        return {
            "request_id": self.request_id,
            "status": self.status,
            "original_query": self.original_query,
            "refined_query": self.refined_query,
            "intent": self.intent.model_dump() if self.intent else None,
            "sub_questions": [s.model_dump() for s in self.sub_questions],
            "api_results": [a.model_dump() for a in self.api_results],
            "aggregated_context": self.aggregated_context,
            "reasoning_output": self.reasoning_output,
            "visualizations": self.visualizations if isinstance(self.visualizations, list) else [],
            "rag_references": safe_refs,
            "evaluation": self.evaluation.model_dump() if self.evaluation else None,
            "final_answer": self.final_answer,
            # Map internal name → API name (ResearchResp uses "error" not "error_message")
            "error": self.error_message,
            "agent_trace": self.agent_trace,
        }
