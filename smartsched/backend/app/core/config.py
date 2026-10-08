"""Application settings (pydantic-settings). All values can come from the environment or a .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SmartSched"
    environment: str = Field(default="dev", description="dev | test | prod")
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./smartsched.db"
    create_tables_on_startup: bool = True

    app_secret: str = Field(
        default="change-me-change-me-change-me-change-me",
        description="Master secret: JWT signing + Fernet key derivation for encrypted settings",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    admin_email: str | None = None
    admin_password: str | None = None

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"

    solver_default_time_limit: float = 60.0
    solver_workers: int = 8

    upload_dir: str = "./uploads"

    # Ingestion Council (docs/universal/ARCHITECTURE.md "Settings")
    council_ai: bool = Field(default=True, description="use Claude in the council when an API key is configured")
    council_model: str = Field(default="", description="model for the council; '' = the anthropic_model setting")
    council_fast_model: str = Field(
        default="", description="model for vision transcription and the judge; '' = council_model"
    )
    council_review_threshold: float = Field(default=0.75, description="below this confidence an item needs review")
    council_step_timeout_s: float = 300.0
    council_job_token_budget: int = Field(default=600_000, description="input+output tokens per job; then heuristic")
    council_max_files: int = 25
    council_max_file_mb: int = 15
    council_self_consistency: int = Field(default=1, description="model votes per sheet (majority)")
    council_judge_sample: int = Field(default=12, description="records per file checked by the model judge; 0 = off")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
