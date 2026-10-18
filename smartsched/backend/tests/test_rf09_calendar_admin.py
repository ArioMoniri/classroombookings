"""RF-09 backend (audit Part B "Period grid", "Term week calendar"; fix list 9): admins edit the university's period
grid (the clock times of P1-P18) and a term's week calendar through audited routes.

* ``GET /period-grid`` (signed in) / ``PUT /period-grid`` / ``DELETE /period-grid`` (``setup.schedules``): 18 periods,
  each ``start < end``, in order and not overlapping; Turkish input (``08.30``, NBSP) is read; the stored grid is the
  one the importers, find-room, feeds and exports read (``normalize.PERIODS``, also in the parse child process);
  booking periods made with "from grid" (``P<n>``, same times) follow the change; audited ``period_grid.update`` /
  ``period_grid.reset``.
* ``PATCH /terms/{id}/weeks/{index}``: one week's kind / label / start date (``Tatil`` / ``Sınav`` / ``Ders`` /
  ``Bütünleme`` or the codes), marked ``edited`` so a board re-import keeps it (tests/test_rf06_reimport.py);
  ``PUT /terms/{id}/weeks`` validates kinds the same way and marks the weeks it changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import time

import pytest
from app.core import db as dbmod
from app.core.safe_files import run_isolated
from app.importers import normalize as n
from app.models import AuditEvent, Week
from app.services import period_grid
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import make_user

API = "/api/v1"
DEFAULT = [(f"{p.start:%H:%M}", f"{p.end:%H:%M}") for p in n.DEFAULT_PERIODS]


@pytest.fixture(autouse=True)
def _default_grid() -> Iterator[None]:
    n.set_period_grid(None)
    yield
    n.set_period_grid(None)


def _body(times: list[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    return {"periods": [{"start": s, "end": e} for s, e in times]}


async def test_period_grid_round_trip_is_audited_and_reaches_every_reader(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    got = (await client.get(f"{API}/period-grid", headers=admin)).json()
    assert got["source"] == "default" and len(got["periods"]) == 18
    assert got["periods"][0] == {"index": 1, "start": "08:30", "end": "09:10", "label": "08:30-09:10"}

    # a booking schedule made from the grid, as /admin/schedules does
    sid = (await client.post(f"{API}/booking-admin/schedules", json={"name": "Ders saatleri"}, headers=admin)).json()[
        "id"
    ]
    r = await client.post(f"{API}/booking-admin/schedules/{sid}/periods/from-grid", headers=admin)
    assert r.status_code == 200, r.text

    # the faculty starts at 08.00 from next term (dotted time, NBSP as pasted from the senate's circular)
    times = [("08.00", "08:40 "), *DEFAULT[1:]]
    r = await client.put(f"{API}/period-grid", json=_body(times), headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "setting" and out["periods"][0]["start"] == "08:00" and out["periods"][0]["end"] == "08:40"
    assert out["booking_periods_updated"] == 1

    assert n.PERIODS[0].start == time(8, 0) and n.time_range_to_periods(time(8, 0), time(8, 40)).start_period == 1
    assert (await run_isolated(n.period_grid_times))[0] == ("08:00", "08:40")  # the parse child reads it too
    sched = (await client.get(f"{API}/booking-admin/schedules/{sid}", headers=admin)).json()
    p1 = next(p for p in sched["periods"] if p["name"] == "P1")
    assert p1["time_start"].startswith("08:00") and p1["time_end"].startswith("08:40")

    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "period_grid.update"))).scalar_one()
    assert ev.actor_type == "user" and ev.before["periods"][0] == ["08:30", "09:10"]
    assert ev.after["periods"][0] == ["08:00", "08:40"]

    # another worker (defaults in memory) picks the stored grid up
    n.set_period_grid(None)
    async with dbmod.get_session_factory()() as s:
        assert await period_grid.refresh(s) is True
    assert n.PERIODS[0].start == time(8, 0)

    r = await client.delete(f"{API}/period-grid", headers=admin)
    assert r.status_code == 200 and r.json()["source"] == "default" and n.PERIODS[0].start == time(8, 30)


async def test_period_grid_refuses_bad_grids_in_turkish(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    r = await client.put(f"{API}/period-grid", json=_body(DEFAULT[:17]), headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "period_grid_count"
    assert "18" in r.json()["detail"]["message_tr"]

    overlap = list(DEFAULT)
    overlap[2] = ("09:50", "10:50")  # P3 starts before P2 ends (10:00)
    r = await client.put(f"{API}/period-grid", json=_body(overlap), headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "period_grid_order"
    assert "P3" in r.json()["detail"]["message_tr"]

    backwards = list(DEFAULT)
    backwards[0] = ("09:10", "08:30")
    r = await client.put(f"{API}/period-grid", json=_body(backwards), headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "period_grid_order"

    unreadable = list(DEFAULT)
    unreadable[0] = ("sabah", "09:10")
    r = await client.put(f"{API}/period-grid", json=_body(unreadable), headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "period_grid_time"
    assert n.PERIODS[0].start == time(8, 30)  # nothing applied

    _uid, teacher = await make_user(client, admin, "ogretmen@uni.edu.tr")
    assert (await client.get(f"{API}/period-grid", headers=teacher)).status_code == 200
    assert (await client.put(f"{API}/period-grid", json=_body(DEFAULT), headers=teacher)).status_code == 403


async def test_week_calendar_edits_validate_turkish_kinds_and_mark_weeks(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    term = (await client.post(f"{API}/terms", json={"code": "2026-GUZ", "name": "2026 Güz"}, headers=admin)).json()
    r = await client.put(
        f"{API}/terms/{term['id']}/weeks",
        json=[{"index": 1, "kind": "LECTURE"}, {"index": 2, "kind": "ders"}, {"index": 3, "kind": "Sınav"}],
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert [(w["index"], w["kind"]) for w in r.json()] == [(1, "LECTURE"), (2, "LECTURE"), (3, "EXAM")]
    assert all(w["edited"] for w in r.json())

    r = await client.patch(f"{API}/terms/{term['id']}/weeks/2", json={"kind": "TATİL"}, headers=admin)
    assert r.status_code == 200 and r.json()["kind"] == "HOLIDAY"
    r = await client.patch(f"{API}/terms/{term['id']}/weeks/2", json={"kind": "yarım gün"}, headers=admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "week_kind_invalid"
    assert "Tatil" in r.json()["detail"]["message_tr"]
    r = await client.patch(f"{API}/terms/{term['id']}/weeks/9", json={"kind": "HOLIDAY"}, headers=admin)
    assert r.status_code == 404
    r = await client.put(f"{API}/terms/{term['id']}/weeks", json=[{"index": 1, "kind": "x"}], headers=admin)
    assert r.status_code == 422

    async with dbmod.get_session_factory()() as s:
        w2 = (await s.execute(select(Week).where(Week.term_id == term["id"], Week.index == 2))).scalar_one()
        assert w2.edited is True
        events = list(
            (await s.execute(select(AuditEvent).where(AuditEvent.entity_type == "term_week"))).scalars()
        )
    assert any(e.action == "term_week.update" and e.actor_type == "user" for e in events)
