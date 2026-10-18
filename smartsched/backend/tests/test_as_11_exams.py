"""AS-11: exam-period demand on Final 2026 (``final_planlama_listesi_2026_v2.xlsx``).

* peak day Wednesday 3 June 2026 (98 sittings: a shared exam counts once), peak-to-mean 1.67 ± 0.01 over the
  weekdays of the exam weeks (AS20-F13, re-baselined 2026-10-18 by FIX-G from 126 exam-list rows, 1.86);
* **B7**: the ``slots`` hold frees room-periods against the whole-week closure, with no exam room-period bookable;
* ``GET /analytics/forecast/exams`` from the imported exam list: the peak slot's seats stay within the exam-capacity
  sum; without bookings in exam weeks the booking part says ``none`` + needs.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.core.db import get_session_factory
from app.importers.exam_list import import_exam_list
from app.importers.room_master import import_room_master
from app.models import Term
from app.services import backtest as bt
from sqlalchemy import select

from tests.api_fixtures import login
from tests.conftest import EXAM_LIST, FIXTURES


def test_as_11_peak_day_and_ratio(parsed_exam_list):
    r = bt.exam_day_load(parsed_exam_list)
    assert r.passed, r.metrics
    assert r.metrics["peak_day"] == "2026-06-03" and r.metrics["peak_exams"] == 98
    assert r.metrics["peak_to_mean"] == pytest.approx(1.67, abs=0.01)
    assert r.metrics["peak_label"]["tr"] == "3 Haziran 2026 Çarşamba"


def test_as_11_b7_slots_free_room_periods(parsed_exam_list):
    r = bt.b7_slot_holds(parsed_exam_list)
    assert r.passed, r.metrics
    assert r.metrics["freed_room_periods"] > 0 and r.metrics["exam_room_periods_bookable"] == 0
    assert r.metrics["held_room_periods"] < r.metrics["closed_room_periods"]


async def test_as_11_exam_forecast_api(client):
    h = await login(client)
    async with get_session_factory()() as s:
        await import_room_master(s, FIXTURES / "room_master.csv")
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
        await s.commit()
        tid = (await s.execute(select(Term.id).where(Term.code == "2026-FINAL"))).scalar_one()
    r = await client.get("/api/v1/analytics/forecast/exams", params={"term_id": tid}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["method"] == "requests" and out["confidence"] == "high"
    assert out["peak_day"] == date(2026, 6, 3).isoformat()
    assert out["peak_slot"]["seats"] <= out["peak_slot"]["exam_capacity"]
    assert out["peak_slot"]["invigilators"] >= 1
    assert out["bookings"]["confidence"] == "none" and out["bookings"]["needs"]["tr"]
    assert out["holds"]["exam_run_id"] is None  # no exam run yet: nothing is held


async def test_as_11_empty_term(client):
    h = await login(client)
    async with get_session_factory()() as s:
        t = Term(code="2027-FINAL", name="2027 Final", kind="FINAL")
        s.add(t)
        await s.commit()
        tid = t.id
    out = (await client.get("/api/v1/analytics/forecast/exams", params={"term_id": tid}, headers=h)).json()
    assert out["confidence"] == "none" and out["needs"]["tr"] and out["days"] == []
