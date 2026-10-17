"""Round-2 lane E (T-R2-27, T-R2-29, T-R2-30): pure helpers of the runs / calendar / analytics routes.

* a QUEUED or RUNNING run cancelled by hand records the actor's display name, not the e-mail (R2-M-17);
* an export filtered with ``?weeks=`` carries ``-haftaN`` whatever the run's horizon (R1-M-38 residue);
* the forced-move refusal speaks Turkish too (R1-S-24 / R2-M-18);
* the compare refusal names the real reason and each run's horizon (R2-M-21).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.api.v1 import analytics, calendar, runs


def _run(**kw: Any) -> Any:
    base = {"id": 8, "term_id": 1, "kind": "COURSE", "horizon": "TERM", "horizon_params": {}, "status": "FEASIBLE"}
    base.update(kw)
    return SimpleNamespace(**base)


def test_cancelled_by_uses_the_display_name() -> None:
    assert runs._cancelled_by(SimpleNamespace(full_name="Ayşe Tekin", username="atekin", email="a@x")) == "Ayşe Tekin"
    assert runs._cancelled_by(SimpleNamespace(full_name=None, username="atekin", email="a@x")) == "atekin"
    assert runs._cancelled_by(SimpleNamespace(full_name="", username=None, email="a@x")) == "a@x"
    assert runs._cancelled_by(None) == "a planner"


def test_week_suffix_names_the_exported_weeks_of_any_run() -> None:
    assert runs._week_suffix(_run(horizon="WEEK", horizon_params={"weeks": [4]})) == "-hafta4"
    assert runs._week_suffix(_run(horizon="WEEK", horizon_params={"weeks": [4, 5, 6]})) == "-hafta4-6"
    assert runs._week_suffix(_run()) == ""
    # a TERM run exported with ?weeks=4 (the sheets picked): the file says so (R1-M-38)
    assert runs._week_suffix(_run(), [4]) == "-hafta4"
    assert runs._week_suffix(_run(), [4, 6, 7, 8]) == "-hafta4-8"
    assert runs._week_suffix(_run(horizon="WEEK", horizon_params={"weeks": [3]}), [3]) == "-hafta3"


def test_force_refusal_has_a_turkish_sentence() -> None:
    for d in (runs.FORCE_ADMIN_ONLY, calendar.FORCE_ADMIN_ONLY):
        assert d["message"] == "moving despite a conflict is admin-only"
        assert d["message_tr"].startswith("Çakışmaya rağmen taşıma")
        assert d["code"] == "forbidden" and d["permission"] == "planning.admin"


def test_compare_refusal_names_the_reason_and_the_horizons() -> None:
    a = _run(id=8, term_id=1, horizon="TERM")
    b = _run(id=11, term_id=1, horizon="WEEK", horizon_params={"weeks": [3]}, kind="EXAM")
    d = analytics.compare_refusal(a, b, {1: "2026-BAHAR"})
    assert "#8" in d["tr"] and "#11" in d["tr"]
    assert "türleri farklı" in d["tr"] and "dönem" in d["tr"] and "3. hafta" in d["tr"]
    assert "ortak hafta" in d["tr"]
    assert "different kinds" in d["en"] and "week 3" in d["en"]
    c = _run(id=10, term_id=2)
    d2 = analytics.compare_refusal(a, c, {1: "2026-BAHAR", 2: "2026-GUZ"})
    assert "dönemleri farklı" in d2["tr"] and "2026-GUZ" in d2["tr"] and "2026-BAHAR" in d2["tr"]
