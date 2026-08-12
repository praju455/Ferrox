from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://ferrox:ferrox@localhost:5432/ferrox"
    test_database_url: str = "sqlite+pysqlite:///:memory:"
    internal_api_key: str | None = None
    llm_provider_order: str = "gemini,groq,openai"
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 30
    scraper_timeout_seconds: int = 15
    max_source_chars: int = Field(default=120_000, ge=1_000)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def provider_order(self) -> list[str]:
        return [item.strip().lower() for item in self.llm_provider_order.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
