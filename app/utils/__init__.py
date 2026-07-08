"""
Utilities Package.

Centralised cross-cutting concerns:
  • Structured JSON logging  (``get_logger``, ``setup_logging``)
  • Custom exception hierarchy (``AIResearcherError`` and children)
  • Enumerations              (``AgentName``, ``IntentType``, ``WorkflowStatus``)
  • Helper functions          (``gen_id``, ``timed``, ``truncate``, ``safe_json``)
"""

from app.utils.logger import get_logger, setup_logging
from app.utils.exceptions import (
    AIResearcherError,
    LLMProviderError,
    AgentExecutionError,
    GraphExecutionError,
    KnowledgeBaseError,
    ExternalAPIError,
    InputValidationError,
    PaperParseError,
)
from app.utils.constants import AgentName, IntentType, WorkflowStatus, APISource
from app.utils.helpers import gen_id, timed, truncate, safe_json

__all__ = [
    "get_logger", "setup_logging",
    "AIResearcherError", "LLMProviderError", "AgentExecutionError",
    "GraphExecutionError", "KnowledgeBaseError", "ExternalAPIError",
    "InputValidationError", "PaperParseError",
    "AgentName", "IntentType", "WorkflowStatus", "APISource",
    "gen_id", "timed", "truncate", "safe_json",
]
