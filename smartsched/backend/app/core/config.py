"""Application settings (pydantic-settings). All values can come from the environment or a .env file."""

from __future__ import annotations

import importlib.metadata
import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_APP_SECRET = "change-me-change-me-change-me-change-me"
MIN_SECRET_LEN = 32
MIN_ADMIN_PASSWORD_LEN = 12
#: environments that skip the production checks; every other value (only ``prod`` is valid) is checked
RELAXED_ENVIRONMENTS = frozenset({"dev", "test"})
#: a secret containing one of these (case-insensitive, Turkish I folded) is a placeholder (no-placeholder M2)
SECRET_PLACEHOLDER_MARKERS = ("changeme", "change-me", "__generate__", "secret")
#: an admin password that is one of these words, optionally followed by digits/punctuation only (M3)
_ADMIN_PLACEHOLDER = re.compile(r"(?:admin|change-?me|__generate__|password|parola|sifre|şifre)[\W\d_]*")
PACKAGE_NAME = "smartsched-backend"

Environment = Literal["dev", "test", "prod"]


def _fold(value: str) -> str:
    """Trim (incl. NBSP) and lower-case with the Turkish I's folded to ``i`` (``ADMİN``/``admın`` -> ``admin``)."""
    return value.strip().replace("İ", "i").replace("I", "i").replace("ı", "i").lower()


def secret_problem(value: str | None) -> str | None:
    """Why ``value`` cannot be a production APP_SECRET / JWT_SECRET (``None`` when it can)."""
    if not value:
        return "is not set"
    folded = _fold(value)
    if folded == _fold(DEFAULT_APP_SECRET) or any(m in folded for m in SECRET_PLACEHOLDER_MARKERS):
        return "is a placeholder/default value"
    if len(value.strip()) < MIN_SECRET_LEN:
        return f"is shorter than {MIN_SECRET_LEN} characters"
    return None


def admin_password_problem(value: str | None) -> str | None:
    """Why ``value`` cannot seed the production admin (``None`` when it can or nothing is seeded)."""
    if value is None or value == "":
        return None  # nothing to seed
    folded = _fold(value)
    if _ADMIN_PLACEHOLDER.fullmatch(folded) or any(m in folded for m in ("changeme", "change-me", "__generate__")):
        return "is a placeholder value"
    if len(value.strip()) < MIN_ADMIN_PASSWORD_LEN:
        return f"is shorter than {MIN_ADMIN_PASSWORD_LEN} characters"
    return None


def app_version() -> str:
    """The installed package version (pyproject ``[project] version``), not a hard-coded string."""
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:  # source tree without ``pip install``
        return "0+unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SmartSched"
    #: dev | test | prod; anything else fails at start-up (no-placeholder M2). Trimmed and case-folded.
    environment: Environment = "dev"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./smartsched.db"
    create_tables_on_startup: bool = True

    app_secret: str = Field(
        default=DEFAULT_APP_SECRET,
        description="Master secret: JWT signing + Fernet key derivation for encrypted settings",
    )
    #: JWT signing key (review M9). Required in prod (>= 32 chars, not APP_SECRET); dev/test fall back to
    #: APP_SECRET when unset. APP_SECRET keeps encrypting stored API keys (Fernet) and sealing studio runs.
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    metrics_token: str | None = None  # bearer token for scraping /metrics without a user session
    jwt_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    #: proxy hops whose X-Forwarded-For is believed (docs/SECURITY.md F3 / F8): loopback and the Docker bridge
    #: range the compose network is allocated from. uvicorn reads the same variable (docker-entrypoint.sh).
    forwarded_allow_ips: str = "127.0.0.1,::1,172.16.0.0/12"
    #: how browsers reach the panel (deploy/.env.example PUBLIC_URL); calendar feed links and OAuth redirect URIs
    #: are built from it unless the admin setting integrations.public_url overrides it
    public_url: str | None = None

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
    run_wall_clock_factor: float = 5.0  # a run may take factor * time_limit_s + margin wall-clock seconds
    run_wall_clock_margin_s: float = 300.0  # segmented term solves run several CP-SAT stages
    run_cancel_grace_s: float = 30.0  # wait this long for a stopped search to return
    max_active_runs_per_user: int = 3  # QUEUED + RUNNING runs one user may have (429 above)
    sqlite_busy_timeout_ms: int = 15_000

    upload_dir: str = "./uploads"
    #: KVKK guard of recording / test stacks (app/core/kvkk_guard.py, FIX-J E2EA-F01): refuse uploads that still
    #: carry full person names or are a raw seed workbook. Only honoured in dev / test; scripts/record/stack.sh
    #: turns it on and points ``kvkk_names_file`` at its saved name list (outside the repository).
    kvkk_upload_guard: bool = False
    kvkk_names_file: str | None = None
    #: HB-23b helper file router: classify stages the bytes encrypted for 10 minutes under a key that lives only in
    #: the person's ``upload_token`` (docs/design/v3/helper-file-router.md §6.3). ``HELPER_FILE_STAGE=off``: nothing
    #: is staged and the target page asks the browser to send the same File object again.
    helper_file_stage: bool = True

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
    council_max_job_mb: int = Field(default=50, description="all files of one job (nginx client_max_body_size 50m)")
    council_self_consistency: int = Field(default=1, description="model votes per sheet (majority)")
    council_judge_sample: int = Field(default=12, description="records per file checked by the model judge; 0 = off")

    @field_validator("environment", mode="before")
    @classmethod
    def _normalise_environment(cls, value: Any) -> Any:
        return _fold(value) if isinstance(value, str) else value

    @property
    def is_relaxed(self) -> bool:
        """dev / test: production secret and admin-password checks are skipped."""
        return self.environment in RELAXED_ENVIRONMENTS

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def signing_key(self) -> str:
        return self.jwt_secret or self.app_secret

    def insecure_reasons(self) -> list[str]:
        """Why this configuration must not run in production (empty when it may). Runs for every
        environment except an explicit ``dev`` / ``test``."""
        out: list[str] = []
        if self.is_relaxed:
            return out
        for name, value in (("APP_SECRET", self.app_secret), ("JWT_SECRET", self.jwt_secret)):
            problem = secret_problem(value)
            if problem:
                out.append(f"{name} {problem}")
        if self.jwt_secret and self.jwt_secret == self.app_secret:
            out.append("JWT_SECRET must differ from APP_SECRET")
        problem = admin_password_problem(self.admin_password)
        if problem:
            out.append(
                f"ADMIN_PASSWORD {problem} (at least {MIN_ADMIN_PASSWORD_LEN} characters, not a default; "
                "leave it empty once the admin exists)"
            )
        return out


def assert_secure(settings: Settings) -> None:
    """Refuse to start in production with a default, short or shared secret (forged admin JWTs)."""
    reasons = settings.insecure_reasons()
    if reasons:
        raise RuntimeError(
            f"refusing to start with ENVIRONMENT={settings.environment}: "
            + "; ".join(reasons)
            + " (generate them with `openssl rand -base64 48`, see smartsched/deploy/.env.example)"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
