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

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
