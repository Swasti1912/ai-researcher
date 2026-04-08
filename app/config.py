"""
Application Configuration.

Loads all settings from environment / .env file via Pydantic Settings.
Access the immutable, cached singleton through ``get_settings()``.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )

    # LLM provider — "groq" or "openai"
    llm_provider: str = "groq"
    groq_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 1.0
    llm_max_tokens: int = 4000   # free tier limit ~8k TPM; keep output headroom for input tokens

    # External APIs
    semantic_scholar_api_key: str = ""
    arxiv_base_url: str = "http://export.arxiv.org/api/query"
    crossref_base_url: str = "https://api.crossref.org"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Pipeline
    max_iterations: int = 3
    request_timeout: int = 180

    # Qdrant vector store
    # Set qdrant_url=":memory:" for local dev (no Docker needed).
    # For production point to your Qdrant instance, e.g. "http://localhost:6333"
    qdrant_url: str = ":memory:"
    qdrant_collection: str = "paper_chunks"
    embedding_model: str = "all-MiniLM-L6-v2"   # 384-dim, ~80 MB, runs locally
    session_max_age_hours: float = 2.0           # auto-clean sessions older than this

    @property
    def cors_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton – only created once per process."""
    return Settings()
