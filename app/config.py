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

    # LLM provider — Groq primary, optional Gemini fallback
    llm_provider: str = "groq"
    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"   # Groq-hosted model
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # OpenAI — preferred primary when set (funded key → no free-tier daily wall,
    # high concurrency). Falls back to Groq then Gemini.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Gemini fallback — used automatically when a Groq call fails (rate limit,
    # bad key, timeout). Inactive unless google_api_key is set.
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Feature flags. Persistence/Library is shared across all visitors on a
    # single-tenant deployment, so it's disabled there until per-user auth
    # exists. Local dev keeps it on. Set ENABLE_LIBRARY=false in production.
    enable_library: bool = True

    # Retention for on-disk (persisted) Library papers, in hours. The idle
    # sweeper deletes persisted papers (memory + Qdrant + storage) older than
    # this so a durable deployment doesn't accumulate data forever. 0 = keep
    # forever. Explicit logout always wipes a user's data immediately.
    persisted_retention_hours: float = 48.0

    # Auth (Google OAuth / OIDC). Auth is ACTIVE only when a client id is set —
    # so local dev runs open, and the deployment gates the whole app behind
    # login. Each logged-in user gets a private, session-scoped library that is
    # wiped on logout.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    session_secret: str = "dev-insecure-session-secret-change-me"
    # Public base URL for OAuth callbacks (e.g. https://<space>.hf.space).
    # Needed because HF's proxy hides the external scheme/host from the app.
    oauth_redirect_base: str = ""

    @property
    def auth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    # External APIs
    semantic_scholar_api_key: str = ""
    arxiv_base_url: str = "https://export.arxiv.org/api/query"
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
    session_max_age_hours: float = 2.0           # in-memory TTL (persisted papers are never auto-deleted)

    # Persistent storage (P2). When qdrant_url == ":memory:", vectors are stored
    # on disk under qdrant_path so they survive a restart. NOTE: on-disk Qdrant
    # takes an exclusive single-process lock — run one worker, no --reload.
    data_dir: str = "./data"
    qdrant_path: str = ""                        # defaults to {data_dir}/qdrant when empty

    @property
    def cors_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton – only created once per process."""
    return Settings()
