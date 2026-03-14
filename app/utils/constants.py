"""
Application-wide Enumerations.

Canonical names, types, and statuses used by agents, state, and API.
"""
from __future__ import annotations

from enum import Enum


class AgentName(str, Enum):
    """Every agent node in the pipeline."""
    ORCHESTRATOR = "orchestrator"
    REFINER      = "refiner"
    INTENT       = "intent"
    DECOMPOSER   = "decomposer"
    AGGREGATOR   = "aggregator"
    REASONING    = "reasoning"
    EVALUATOR    = "evaluator"


class IntentType(str, Enum):
    """Classified intent categories."""
    WHY         = "why"
    HOW         = "how"
    WHEN        = "when"
    WHAT        = "what"
    WHO         = "who"
    COMPARISON  = "comparison"
    METHODOLOGY = "methodology"
    SURVEY      = "survey"
    GENERAL     = "general"


class WorkflowStatus(str, Enum):
    """Lifecycle of a single research run."""
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    LOOPING   = "looping"


class APISource(str, Enum):
    """External data sources the Decomposer can assign."""
    ARXIV             = "arxiv"
    SEMANTIC_SCHOLAR  = "semantic_scholar"
    CROSSREF          = "crossref"
    WEB_SEARCH        = "web_search"
