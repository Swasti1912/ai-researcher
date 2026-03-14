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

    # LLM
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

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

    @property
    def cors_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton – only created once per process."""
    return Settings()
