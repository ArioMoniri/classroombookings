from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    solver_default_time_limit: float | None = None
    solver_workers: int | None = None
    solver_weights: dict[str, Any] | None = None
    ui_language: str | None = None
    timezone: str | None = None
    extra: dict[str, Any] | None = None


class TestAiIn(BaseModel):
    api_key: str | None = None  # transient: tested but not saved
    model: str | None = None


class TestAiOut(BaseModel):
    ok: bool
    model: str | None = None
    detail: str
    used_key: str  # "transient" | "stored" | "none"
