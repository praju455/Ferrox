from functools import lru_cache
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://ferrox:ferrox@localhost:5432/ferrox"
    test_database_url: str = "sqlite+pysqlite:///:memory:"
    internal_api_key: str | None = None
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "ferrox"
    jwt_audience: str = "ferrox-api"
    access_token_expire_minutes: int = Field(default=480, ge=5, le=10080)
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    llm_provider_order: str = "gemini,groq,openai"
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4o-mini"
    enable_grounded_enrichment: bool = False
    gemini_grounding_model: str = "gemini-2.5-flash"
    gemini_input_cost_per_million: float = 0.0
    gemini_output_cost_per_million: float = 0.0
    groq_input_cost_per_million: float = 0.0
    groq_output_cost_per_million: float = 0.0
    openai_input_cost_per_million: float = 0.0
    openai_output_cost_per_million: float = 0.0
    llm_timeout_seconds: int = 30
    scraper_timeout_seconds: int = 15
    max_source_chars: int = Field(default=120_000, ge=1_000)
    max_request_bytes: int = Field(default=25_000_000, ge=1_000_000)
    max_pdf_upload_bytes: int = Field(default=20_000_000, ge=1_000_000)
    object_storage_backend: str = "local"
    local_storage_path: str = ".data/objects"
    s3_bucket: str = "ferrox-sources"
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_force_path_style: bool = True
    s3_server_side_encryption: str | None = "AES256"
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    worker_poll_seconds: float = Field(default=2.0, gt=0, le=60)
    backup_interval_seconds: int = Field(default=86_400, ge=300)
    backup_retention_count: int = Field(default=14, ge=1, le=365)
    backup_prefix: str = "backups/postgres"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def provider_order(self) -> list[str]:
        return [item.strip().lower() for item in self.llm_provider_order.split(",") if item.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def llm_cost_rates(self, provider: str) -> tuple[float, float]:
        return (
            float(getattr(self, f"{provider}_input_cost_per_million", 0.0)),
            float(getattr(self, f"{provider}_output_cost_per_million", 0.0)),
        )


@lru_cache
def get_settings() -> Settings:
    env_file = None if os.getenv("FERROX_DISABLE_ENV_FILE") == "1" else ".env"
    return Settings(_env_file=env_file)
