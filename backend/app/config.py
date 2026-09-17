import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cad_storage_root: Path = Path("./storage")
    database_url: str = "sqlite:///./storage/cadpilot.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    mcp_server_command: str = "uvx"
    mcp_server_args: str = "freecad-mcp --only-text-feedback"
    mcp_timeout_seconds: int = 180
    api_cors_origins: str = "http://localhost:3000"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    # Any OpenAI-compatible endpoint that implements the Responses API, e.g.
    # OpenRouter's "https://openrouter.ai/api/v1" with a model like
    # "openai/gpt-4.1-mini". Leave unset to use OpenAI's own endpoint.
    openai_base_url: str | None = None
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "cadpilot"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


def _configure_langsmith(settings: "Settings") -> None:
    """Mirror LangSmith settings into the process environment.

    LangGraph traces every node of a compiled graph automatically once
    `LANGSMITH_TRACING`/`LANGSMITH_API_KEY` are present in the environment;
    no per-node instrumentation is required. `pydantic-settings` only loads
    `.env` into this `Settings` object, not into `os.environ`, so the
    `langsmith` SDK (which reads `os.environ` directly) would never see keys
    that only live on `.env` without this. Safe to call repeatedly; `get_settings`
    calls it exactly once per process thanks to `lru_cache`.
    """
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    else:
        os.environ["LANGSMITH_TRACING"] = "false"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _configure_langsmith(settings)
    return settings
