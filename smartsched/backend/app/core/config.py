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
    solver_max_time_limit: float = 3600.0  # POST /runs params.time_limit_s upper bound
    solver_max_workers: int = 16
    # job control (review M6/M13)
    run_heartbeat_s: float = 15.0  # liveness beat of QUEUED/RUNNING runs and import jobs
    run_stale_after_s: float = 90.0  # a beat older than this (other boot) = orphaned at startup
    run_wall_clock_factor: float = 3.0  # a run may take factor * time_limit_s + margin wall-clock seconds
    run_wall_clock_margin_s: float = 180.0
    run_cancel_grace_s: float = 30.0  # wait this long for a stopped search to return
    max_active_runs_per_user: int = 3  # QUEUED + RUNNING runs one user may have (429 above)
    sqlite_busy_timeout_ms: int = 15_000

    upload_dir: str = "./uploads"

    # safe upload intake (app/core/safe_files.py, review B1)
    upload_max_mb: float = 25.0  # any single upload (413 above)
    zip_max_uncompressed_mb: float = 50.0  # whole .xlsx/.docx expanded
    zip_max_member_mb: float = 20.0  # one part (sharedStrings.xml, a sheet) expanded
    zip_max_ratio: float = 100.0  # expanded / compressed (checked above 2 MiB expanded)
    sheet_max_rows: int = 20_000
    sheet_max_cols: int = 1024
    parse_isolation: str = Field(default="process", description="process (rlimit child) | thread")
    parse_memory_mb: int = 2048  # RLIMIT_AS of the parse child
    parse_timeout_s: float = 300.0

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
