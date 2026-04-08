"""
Custom Exception Hierarchy.

All application errors extend ``AIResearcherError`` so callers can
catch broadly or narrow to specific failure modes.

Hierarchy::

    AIResearcherError
    ├── LLMProviderError
    ├── AgentExecutionError
    ├── GraphExecutionError
    ├── KnowledgeBaseError
    ├── ExternalAPIError
    ├── InputValidationError
    └── PaperParseError
"""
from __future__ import annotations

from typing import Optional


class AIResearcherError(Exception):
    """Root exception for the AI Researcher application."""

    def __init__(
        self,
        message: str = "Internal error",
        detail: Optional[str] = None,
        *,
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """JSON-serialisable representation for API responses."""
        return {
            "error": type(self).__name__,
            "message": self.message,
            "detail": self.detail,
        }


class LLMProviderError(AIResearcherError):
    """LLM call failed (timeout, auth, rate limit)."""

    def __init__(self, message: str = "LLM error", detail: Optional[str] = None, *, provider: str = "openai") -> None:
        self.provider = provider
        super().__init__(message, detail, status_code=502)


class AgentExecutionError(AIResearcherError):
    """An individual agent node failed."""

    def __init__(self, agent_name: str, message: str = "Agent failed", detail: Optional[str] = None) -> None:
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}", detail, status_code=500)


class GraphExecutionError(AIResearcherError):
    """The LangGraph workflow encountered an unrecoverable failure."""
    pass


class KnowledgeBaseError(AIResearcherError):
    """RAG ingestion or retrieval failure."""
    pass


class ExternalAPIError(AIResearcherError):
    """Third-party research API returned an error."""

    def __init__(self, api_name: str, message: str = "API error", detail: Optional[str] = None, *, http_status: Optional[int] = None) -> None:
        self.api_name = api_name
        self.http_status = http_status
        super().__init__(f"[{api_name}] {message}", detail, status_code=502)


class InputValidationError(AIResearcherError):
    """User input failed validation."""

    def __init__(self, message: str = "Invalid input", detail: Optional[str] = None) -> None:
        super().__init__(message, detail, status_code=422)


class PaperParseError(AIResearcherError):
    """Uploaded paper could not be parsed."""

    def __init__(self, message: str = "Paper parse failed", detail: Optional[str] = None) -> None:
        super().__init__(message, detail, status_code=400)
