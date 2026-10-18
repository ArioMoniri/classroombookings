"""FIX-A council term matching (e2e results 2026-10-18, council note 2; orchestrator decision 2026-10-18).

The Güz 2026/2027 workbooks make the planner propose ``2026-2027-GUZ``; the stack seeds the same term as
``2026-GUZ`` "Güz 2026-27" (``scripts/record/setup_api.py``). Before a term is created the group is matched to an
existing term by its season words (Güz / GUZ / Fall, Turkish letters folded) and its year or date range, the
academic year written either way; the review asks only when two terms qualify.

Real data: ``guz_derslik_planlama_2026_2027_v2.xlsx`` and ``guz_derslikler_takvimi_2026_2027.xlsx``; the seeded
term is imported from the same Güz grid, as the stack does."""

from __future__ import annotations

from datetime import date

import pytest
from app.core.db import get_session_factory
from app.council.term_match import calendar_year, matches, term_season
from app.importers.weekly_grid import import_weekly_grid
from app.models import Term
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import GUZ_GRID, GUZ_LIST
from tests.council.test_formats_api import upload


def _term(code: str, name: str, kind: str = "REGULAR", start: date | None = None, end: date | None = None) -> Term:
    return Term(code=code, name=name, kind=kind, start_date=start, end_date=end)


GUZ_GROUP = {
    "key": "FALL:2026-2027",
    "code": "2026-2027-GUZ",
    "name": "2026 Güz",
    "year": 2026,
    "start_date": "2026-09-21",
    "end_date": "2026-12-27",
}


@pytest.mark.parametrize(
    ("code", "name", "ok"),
    [
        ("2026-GUZ", "Güz 2026-27", True),
        ("2026-2027-GUZ", "2026-2027 Güz", True),
        ("2026-FALL", "Fall 2026", True),
        ("GÜZ-2026/2027", "GÜZ 2026/2027", True),  # NBSP and the dotted capital fold
        ("2027-GUZ", "Güz 2027-28", False),  # the next academic year
        ("2026-BAHAR", "Bahar 2026", False),
        ("2026-FINAL", "Final 2026", False),
    ],
)
def test_a_guz_group_matches_the_name_variants_of_its_term(code: str, name: str, ok: bool) -> None:
    assert matches(GUZ_GROUP, _term(code, name)) is ok


def test_dates_decide_over_the_year_and_rule_out_a_term_elsewhere_in_time() -> None:
    elsewhere = _term("2026-GUZ", "Güz 2026-27", start=date(2025, 9, 22), end=date(2025, 12, 28))
    assert not matches(GUZ_GROUP, elsewhere)
    inside = _term("GUZ", "Güz dönemi", start=date(2026, 9, 21), end=date(2027, 1, 10))  # no year written
    assert matches(GUZ_GROUP, inside)


def test_season_and_year_read_turkish_and_english() -> None:
    assert term_season("2026-GUZ", "Güz 2026-27") == "FALL"
    assert term_season("2026-BÜT", None) == "BUT"
    assert calendar_year("SPRING", "2025-2026 Bahar") == 2026
    assert calendar_year("FALL", "2026/2027 Güz") == 2026


async def _seed(code: str, name: str) -> int:
    async with get_session_factory()() as s:
        await import_weekly_grid(s, GUZ_GRID, code, year=2026, term_name=name)
        await s.commit()
        return int((await s.execute(select(Term.id).where(Term.code == code))).scalar_one())


async def _terms() -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(Term))).scalar_one())


async def _decide_blocking(client, h, job_id: int, *, skip_kinds: tuple[str, ...] = ()) -> None:  # type: ignore[no-untyped-def]
    items = (await client.get(f"/api/v1/council/jobs/{job_id}/review", headers=h)).json()["items"]
    todo = [
        {"id": it["id"], "action": "reject" if it["kind"] == "merge" else "accept"}
        for it in items
        if it["blocking"] and it["decision"] is None and it["kind"] not in skip_kinds
    ]
    if todo:
        r = await client.post(f"/api/v1/council/jobs/{job_id}/review", headers=h, json={"decisions": todo})
        assert r.status_code == 200, r.text


@pytest.mark.parametrize(("seeded", "name"), [("2026-GUZ", "Güz 2026-27"), ("2026-2027-GUZ", "Güz 2026-2027")])
async def test_the_guz_workbooks_commit_into_the_seeded_term(client, seeded: str, name: str) -> None:  # type: ignore[no-untyped-def]
    h = await login(client)
    tid = await _seed(seeded, name)
    before = await _terms()
    job = await upload(client, h, (GUZ_LIST.name, GUZ_LIST.read_bytes()), (GUZ_GRID.name, GUZ_GRID.read_bytes()))
    groups = job["plan"]["groups"]
    assert len(groups) == 1, groups
    assert groups[0]["code"] == seeded and groups[0]["term_id"] == tid
    await _decide_blocking(client, h, job["id"])
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0})
    assert r.status_code == 200, r.text
    assert r.json()["term_code"] == seeded and r.json()["term_created"] is False
    assert await _terms() == before  # no 2026-2027-GUZ next to it


async def test_two_matching_terms_are_asked_in_the_review(client) -> None:  # type: ignore[no-untyped-def]
    h = await login(client)
    await _seed("2026-GUZ", "Güz 2026-27")
    async with get_session_factory()() as s:
        s.add(_term("2026-FALL", "Fall 2026", start=date(2026, 9, 21), end=date(2027, 1, 10)))
        await s.commit()
    before = await _terms()
    job = await upload(client, h, (GUZ_LIST.name, GUZ_LIST.read_bytes()))
    g = job["plan"]["groups"][0]
    assert {c["code"] for c in g["term_candidates"]} == {"2026-GUZ", "2026-FALL"}
    assert "term_id" not in g
    items = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()["items"]
    plan_item = next(it for it in items if it["kind"] == "plan")
    assert plan_item["blocking"] is True and plan_item["decision"] is None
    assert {c["code"] for c in plan_item["term_candidates"]} == {"2026-GUZ", "2026-FALL"}
    await _decide_blocking(client, h, job["id"], skip_kinds=("plan",))
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "review_pending"
    value = {**plan_item["current"], "code": "2026-FALL"}
    r = await client.post(
        f"/api/v1/council/jobs/{job['id']}/review",
        headers=h,
        json={"decisions": [{"id": plan_item["id"], "action": "edit", "value": value}]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"group": 0})
    assert r.status_code == 200, r.text
    assert r.json()["term_code"] == "2026-FALL" and r.json()["term_created"] is False
    assert await _terms() == before
