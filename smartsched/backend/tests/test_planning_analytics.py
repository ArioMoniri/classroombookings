"""Scenario comparison and utilisation heatmaps on the real 2026 Bahar and Final fixtures
(``tests/planning_analytics_support.py`` builds the databases: Bahar week 3 as run A and the same week with A's
busiest room closed on Wednesday as run B; the Final exam run A and B with the busiest exam room closed on one
date)."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import Block, Booking, BookingPeriod, BookingSchedule, ScheduleRun
from app.services.seed import seed_admin
from app.services.utilisation import capacity_band_of, day_profile, room_type_of
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import login
from tests.planning_analytics_support import build_bahar, build_final, copy_db


@pytest.fixture(scope="session")
def analytics_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("planning_analytics")


async def _client(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.headers.update(await login(c))
        yield c
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


@pytest.fixture
async def bahar(analytics_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    base, ids = await build_bahar(analytics_dir)
    async for c in _client(copy_db(base, tmp_path), tmp_path, monkeypatch):
        yield {"client": c, **ids}


@pytest.fixture
async def final(analytics_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    base, ids = await build_final(analytics_dir)
    async for c in _client(copy_db(base, tmp_path), tmp_path, monkeypatch):
        yield {"client": c, **ids}


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


# ------------------------------------------------------------------------------------------- unit


def test_day_profile_counts_gaps_and_blocks():
    assert day_profile({2, 3, 6, 7, 8}) == {"periods": 5, "gaps": 2, "longest_block": 3, "first": 2, "last": 8}
    assert day_profile(set())["periods"] == 0


def test_room_type_and_capacity_band():
    from app.models import Room

    r = Room(code="A204", display_name="A 204", capacity=156, exam_capacity=60, tags=["AMPHI", "PC"])
    assert room_type_of(r) == "AMPHI"
    assert capacity_band_of(r) == "151+" and capacity_band_of(r, exam=True) == "31–60"
    assert room_type_of(Room(code="X1", display_name="X 1", capacity=10, tags=[])) == "STANDARD"


# ------------------------------------------------------------------------------------------- scenario comparison


async def test_compare_bahar_room_closed_scenario(bahar):
    c = bahar["client"]
    r = await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "COURSE" and d["a"]["id"] == bahar["a"] and d["b"]["id"] == bahar["b"]
    m = {x["key"]: x for x in d["metrics"]}
    assert m["hard_score"]["a"] == 100 and m["hard_score"]["b"] == 100  # nothing relaxed in either scenario
    counts = d["classes"]["counts"]
    total = sum(v for k, v in counts.items() if k != "by_change")
    assert total == d["requests_in_scope"]
    assert counts["moved"] + counts["only_in_a"] + counts["only_in_b"] > 0  # closing the room changes things
    closed = bahar["closed_room"]
    # no class of B sits in the closed room on Wednesday; every moved class of A that used it now sits elsewhere
    for it in d["classes"]["moved"] + d["classes"]["only_in_b"]:
        if it["b"]["day"] == 3:
            assert closed not in it["b"]["room_ids"], it
        assert it["change"] in ("time", "room", "time_room", "weeks", "split")
        assert it["change_text"]["tr"] and it["change_text"]["en"]
    for it in d["classes"]["moved"]:
        assert (it["a"]["day"], it["a"]["start_period"], tuple(it["a"]["room_ids"])) != (
            it["b"]["day"],
            it["b"]["start_period"],
            tuple(it["b"]["room_ids"]),
        ) or it["a"]["weeks"] != it["b"]["weeks"]
    # placed / unplaced metrics follow the runs' own stats and point the right way
    assert m["placed"]["delta"] == m["placed"]["b"] - m["placed"]["a"]
    if m["placed"]["delta"] < 0:
        assert m["placed"]["better"] == "a" and m["unplaced"]["better"] == "a"
    # the closed room loses room-periods in B
    room_rows = {x["room_id"]: x for x in d["rooms"]["changed"]}
    assert closed in room_rows and room_rows[closed]["delta"]["occupied"] < 0
    assert d["rooms"]["weeks"] == [3]
    # rule by rule: every soft term of either run, with labels in both languages
    assert d["rules"] and all(x["label"]["tr"] and x["label"]["en"] for x in d["rules"])
    assert {x["rule"] for x in d["rules"]} >= {"min_capacity_waste"}
    # instructors: every changed row has its A / B profile and a delta that matches
    for row in d["instructors"]["rows"]:
        assert row["delta"]["periods_per_week"] == pytest.approx(
            row["b"]["periods_per_week"] - row["a"]["periods_per_week"]
        )
    assert d["headline"]["tr"].startswith(f"#{bahar['b']}") and d["headline"]["en"]


async def test_compare_is_deterministic_and_symmetric(bahar):
    c = bahar["client"]
    one = (await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"]})).json()
    two = (await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"]})).json()
    assert one == two
    rev = (await c.get("/api/v1/analytics/compare", params={"a": bahar["b"], "b": bahar["a"]})).json()
    assert rev["classes"]["counts"]["only_in_a"] == one["classes"]["counts"]["only_in_b"]
    assert rev["classes"]["counts"]["only_in_b"] == one["classes"]["counts"]["only_in_a"]
    assert rev["classes"]["counts"]["moved"] == one["classes"]["counts"]["moved"]


async def test_compare_csv_parts(bahar):
    c = bahar["client"]
    for part in ("classes", "instructors", "rooms", "rules", "metrics"):
        r = await c.get(
            "/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"], "format": "csv", "part": part}
        )
        assert r.status_code == 200, (part, r.text)
        assert r.headers["content-type"].startswith("text/csv")
        assert f"-{part}.csv" in r.headers["content-disposition"]
        rows = _rows(r.text)
        if part == "metrics":
            assert {x["metric"] for x in rows} >= {"hard_score", "soft_score", "placed"}
        if part == "classes":
            d = (await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"]})).json()
            n = sum(d["classes"]["counts"][k] for k in ("moved", "only_in_a", "only_in_b"))
            assert len(rows) == n


async def test_compare_refuses_bad_pairs(bahar):
    c = bahar["client"]
    r = await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["a"]})
    assert r.status_code == 422 and r.json()["detail"]["tr"]
    r = await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": 99999})
    assert r.status_code == 404
    async with dbmod.get_session_factory()() as s:
        q = ScheduleRun(term_id=bahar["term_id"], kind="COURSE", status="QUEUED", horizon="WEEK", params={})
        x = ScheduleRun(term_id=bahar["term_id"], kind="EXAM", status="FEASIBLE", horizon="TERM", params={})
        s.add_all([q, x])
        await s.commit()
        qid, xid = q.id, x.id
    r = await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": qid})
    assert r.status_code == 409 and "QUEUED" in r.json()["detail"]["en"]
    r = await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": xid})
    assert r.status_code == 422


async def test_compare_final_exam_runs(final):
    c = final["client"]
    r = await c.get("/api/v1/analytics/compare", params={"a": final["exam_run"], "b": final["exam_run_b"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "EXAM"
    closed = final["exam_closed"]
    for it in d["classes"]["moved"] + d["classes"]["only_in_b"]:
        if closed["date"] in (it["b"].get("dates") or []):
            assert closed["room_id"] not in it["b"]["room_ids"], it
    moved_out = [
        it
        for it in d["classes"]["moved"]
        if closed["room_id"] in it["a"]["room_ids"] and closed["date"] in it["a"]["dates"]
    ]
    assert moved_out or d["classes"]["counts"]["only_in_a"]  # the exams of the closed room went somewhere (or out)
    # named exam instructors: exams per day in A and B
    for row in d["instructors"]["rows"]:
        assert row["a_dates"] != row["b_dates"]
    assert d["rooms"]["weeks"] and len(d["rooms"]["weeks"]) > 1  # the whole exam period


# ------------------------------------------------------------------------------------------- room heatmaps


async def test_room_heatmap_of_a_run_by_building(bahar):
    c = bahar["client"]
    r = await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": bahar["b"], "group_by": "building"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "run" and d["weeks"] == [3] and d["axis"] == "day"
    assert [c_["day"] for c_ in d["columns"]][:5] == [1, 2, 3, 4, 5]
    assert len(d["periods"]) == 18 and d["periods"][0]["start"]
    occ = sum(row["total"]["occupied"] for row in d["rows"])
    assert occ == d["overall"]["total"]["occupied"] > 0
    for row in d["rows"]:
        assert len(row["cells"]) == len(d["columns"]) * 18
        assert sum(x["occupied"] for x in row["cells"]) == row["total"]["occupied"]
        t = row["total"]
        free = t["capacity"] - t["blocked"]
        assert t["pct"] == pytest.approx(round(100 * t["occupied"] / free, 1) if free else 0.0)
        assert row["label"]["tr"].endswith("blok") and row["label"]["en"].startswith("Building")


async def test_room_heatmap_closed_room_is_empty_on_wednesday(bahar):
    c = bahar["client"]
    d = (await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": bahar["b"], "group_by": "room"})).json()
    row = next(x for x in d["rows"] if bahar["closed_room"] in x["room_ids"])
    wed = next(x for x in row["by_col"] if x["col"] == "d3")
    assert wed["occupied"] == 0
    a = (await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": bahar["a"], "group_by": "room"})).json()
    row_a = next(x for x in a["rows"] if bahar["closed_room"] in x["room_ids"])
    assert next(x for x in row_a["by_col"] if x["col"] == "d3")["occupied"] > 0


@pytest.mark.parametrize("group_by", ["room_type", "capacity_band"])
async def test_room_heatmap_groupings_partition_the_rooms(bahar, group_by):
    c = bahar["client"]
    d = (
        await c.get(
            "/api/v1/analytics/heatmap/rooms", params={"run_id": bahar["a"], "group_by": group_by, "rooms": True}
        )
    ).json()
    ids = [i for row in d["rows"] for i in row["room_ids"]]
    assert len(ids) == len(set(ids)) == d["overall"]["rooms"]
    for row in d["rows"]:
        assert len(row["room_rows"]) == row["rooms"]
        assert sum(x["total"]["occupied"] for x in row["room_rows"]) == row["total"]["occupied"]


async def test_room_heatmap_csv(bahar):
    c = bahar["client"]
    params = {"run_id": bahar["a"], "group_by": "capacity_band"}
    d = (await c.get("/api/v1/analytics/heatmap/rooms", params=params)).json()
    r = await c.get("/api/v1/analytics/heatmap/rooms", params={**params, "format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = _rows(r.text)
    assert len(rows) == len(d["rows"]) * len(d["columns"]) * 18
    assert sum(int(x["occupied"]) for x in rows) == d["overall"]["total"]["occupied"]
    assert {"pct", "blocked", "capacity", "group_label_tr"} <= set(rows[0])


async def test_room_heatmap_live_board_with_blocks_and_bookings(final):
    """The live board of Bahar (week 13 published): a term block and a booking count, as blocked / occupied."""
    c = final["client"]
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, final["teach_run"])
        assert run is not None
        from app.models import Assignment
        from sqlalchemy import select

        used = {
            (int(r), a.day, p)
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars()
            for r in a.room_ids or []
            for p in range(a.start_period, a.end_period + 1)
        }
        room = 1
        free = [p for p in range(1, 19) if (room, 5, p) not in used]
        sched = BookingSchedule(name="Gün")
        s.add(sched)
        await s.flush()
        per = BookingPeriod(
            schedule_id=sched.id,
            name="1",
            time_start=dt.time(8, 30),
            time_end=dt.time(9, 10),
            days=[1, 2, 3, 4, 5],
            start_period=free[0],
            end_period=free[0],
        )
        s.add(per)
        await s.flush()
        friday = dt.date(2026, 2, 16) + dt.timedelta(weeks=12, days=4)  # week 13, Friday
        s.add(
            Booking(
                term_id=final["bahar_id"],
                period_id=per.id,
                room_id=room,
                date=friday,
                start_period=free[0],
                end_period=free[0],
                status="BOOKED",
            )
        )
        s.add(
            Block(
                term_id=final["bahar_id"],
                room_id=room,
                day=5,
                start_period=free[1],
                end_period=free[1],
                weeks=[13],
                label="HAZIRLIK",
            )
        )
        await s.commit()
    d = (
        await c.get("/api/v1/analytics/heatmap/rooms", params={"term_id": final["bahar_id"], "group_by": "room"})
    ).json()
    assert d["source"] == "board" and d["weeks"] == [13]
    assert [x["run_id"] for x in d["runs"]] == [final["teach_run"]]
    assert d["counted"]["bookings"] == 1 and d["counted"]["blocks"] == 1
    row = next(x for x in d["rows"] if room in x["room_ids"])
    cell = {(x["col"], x["period"]): x for x in row["cells"]}
    assert cell[("d5", free[0])]["occupied"] == 1
    assert cell[("d5", free[1])]["blocked"] == 1 and cell[("d5", free[1])]["occupied"] == 0
    off = (
        await c.get(
            "/api/v1/analytics/heatmap/rooms",
            params={"term_id": final["bahar_id"], "group_by": "room", "bookings": False, "blocks": False},
        )
    ).json()
    row = next(x for x in off["rows"] if room in x["room_ids"])
    assert row["total"]["occupied"] == next(x for x in d["rows"] if room in x["room_ids"])["total"]["occupied"] - 1
    assert row["total"]["blocked"] == 0


async def test_room_heatmap_bookings_unmapped_without_term_dates(bahar):
    c = bahar["client"]
    async with dbmod.get_session_factory()() as s:
        sched = BookingSchedule(name="Gün")
        s.add(sched)
        await s.flush()
        per = BookingPeriod(
            schedule_id=sched.id,
            name="1",
            time_start=dt.time(8, 30),
            time_end=dt.time(9, 10),
            start_period=1,
            end_period=1,
        )
        s.add(per)
        await s.flush()
        s.add(
            Booking(
                term_id=bahar["term_id"],
                period_id=per.id,
                room_id=1,
                date=dt.date(2026, 3, 4),
                start_period=1,
                end_period=1,
            )
        )
        await s.commit()
    d = (await c.get("/api/v1/analytics/heatmap/rooms", params={"term_id": bahar["term_id"]})).json()
    assert [n["code"] for n in d["notes"]] == ["bookings_unmapped"]
    assert d["notes"][0]["text"]["tr"] and d["counted"]["bookings"] == 0


async def test_room_heatmap_exam_run_uses_dates(final):
    c = final["client"]
    d = (await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": final["exam_run"]})).json()
    assert d["kind"] == "EXAM" and d["axis"] == "date" and len(d["weeks"]) > 1
    dates = [col["date"] for col in d["columns"]]
    assert all(dates) and dates == sorted(dates) and len(set(dates)) == len(dates)
    assert d["overall"]["total"]["occupied"] > 0
    assert sum(x["occupied"] for x in d["overall"]["by_col"]) == d["overall"]["total"]["occupied"]


async def test_room_heatmap_errors(bahar):
    c = bahar["client"]
    assert (await c.get("/api/v1/analytics/heatmap/rooms")).status_code == 422
    assert (await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": 99999})).status_code == 404
    assert (await c.get("/api/v1/analytics/heatmap/rooms", params={"term_id": 99999})).status_code == 404
    r = await c.get("/api/v1/analytics/heatmap/rooms", params={"run_id": bahar["a"], "group_by": "faculty"})
    assert r.status_code == 422


# ------------------------------------------------------------------------------------------- instructor load


async def test_instructor_heatmap(bahar):
    c = bahar["client"]
    r = await c.get("/api/v1/analytics/heatmap/instructors", params={"run_id": bahar["a"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["weeks"] == [3] and d["instructors_total"] > 100
    for row in d["rows"][:50]:
        assert sum(x["weeks"] for x in row["cells"]) == pytest.approx(row["periods_per_week"])
        assert row["max_gaps_day"] <= row["gaps_per_week"] or row["gaps_per_week"] == 0
    peak = max(d["matrix"], key=lambda x: x["instructors"])
    assert 0 < peak["pct"] <= 100
    # the published run of the term is the default source
    board = (await c.get("/api/v1/analytics/heatmap/instructors", params={"term_id": bahar["term_id"]})).json()
    assert board["run_id"] == bahar["a"] and board["source"] == "board"
    name = d["rows"][0]["name"]
    filt = (await c.get("/api/v1/analytics/heatmap/instructors", params={"run_id": bahar["a"], "q": name})).json()
    assert filt["rows"] and all(name.casefold() in x["name"].casefold() for x in filt["rows"])
    csv_r = await c.get("/api/v1/analytics/heatmap/instructors", params={"run_id": bahar["a"], "format": "csv"})
    rows = _rows(csv_r.text)
    assert len(rows) == sum(max(1, len(x["cells"])) for x in d["rows"])


async def test_instructor_heatmap_needs_a_course_run(final):
    c = final["client"]
    r = await c.get("/api/v1/analytics/heatmap/instructors", params={"run_id": final["exam_run"]})
    assert r.status_code == 409 and r.json()["detail"]["tr"]
