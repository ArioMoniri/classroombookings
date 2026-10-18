"""A new audience's delta sheet still says "Güncellendi" when a text the person already saw changed (F-WG-1)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.services.welcome import _sheet_trigger


class _Settings:
    def __init__(self, versions: dict[str, int]) -> None:
        self.versions = versions

    def content_version(self, aud: str) -> int:
        return self.versions.get(aud, 0)


def _row(items: dict[str, Any]) -> Any:
    return SimpleNamespace(state="done", snoozed_until=None, items=items)


NOW = datetime(2026, 2, 16, 8, 0, tzinfo=UTC)


def test_delta_is_updated_when_a_seen_audience_text_changed() -> None:
    row = _row({"audiences": ["teacher"], "versions": {"teacher": 1}})
    trig = _sheet_trigger(row, ["teacher", "staff"], _Settings({"teacher": 2}), NOW)  # type: ignore[arg-type]
    assert trig is not None
    assert trig["kind"] == "delta" and trig["audiences"] == ["staff"] and trig["updated"] is True


def test_delta_is_not_updated_when_nothing_seen_changed() -> None:
    row = _row({"audiences": ["teacher"], "versions": {"teacher": 2}})
    trig = _sheet_trigger(row, ["teacher", "staff"], _Settings({"teacher": 2, "staff": 5}), NOW)  # type: ignore[arg-type]
    assert trig is not None
    assert trig["kind"] == "delta" and trig["updated"] is False
