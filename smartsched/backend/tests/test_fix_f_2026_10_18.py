"""FIX-F (2026-10-18): round-4 AS-20 / CH-12 findings (docs/testing/round4/2026-10-18-as20.md, -ch12.md).

* AS20-F02  the peak model counts only the weeks the published timetable covers: a board imported for weeks 1-2 of
  a 15-week term is not diluted by 13 empty weeks (Güz read 13 % at its real ~90 % peaks);
* AS20-F03  an academician (no planning.view) gets the campus peak cells for the find-room chip;
* AS20-F04  an advisor move can be applied in one call (date / start period, times follow) and undone;
* AS20-F11  reverting to the version that is already current writes no new "Geri dönüş" version;
* CH12-F01  the weekly booking chart covers the whole term when the calendar lists only some weeks.
"""

from __future__ import annotations

from datetime import date

from app.core import db as dbmod
from app.importers import normalize as n
from app.models import Assignment, ExamRequest, Term, Week
from app.services.grid import assignment_weeks
from sqlalchemy import delete, select

from tests.crbs_env import TODAY, env  # noqa: F401

PEAKS = "/api/v1/analytics/peaks"


async def _trim_board_to_weeks(run_id: int, keep: set[int]) -> None:
    """Make the published Bahar board look like the Güz import: placements only in ``keep`` weeks."""
    async with dbmod.get_session_factory()() as s:
        for a in list((await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()):
            ws = assignment_weeks(a)
            left = (ws & keep) if ws else set(keep)
            if not left:
                await s.delete(a)
                continue
            a.weeks = sorted(left)
            if a.week is not None and a.week not in left:
                a.week = min(left)
        await s.commit()


# ------------------------------------------------------------------------------------------------ AS20-F02


async def test_as20_f02_peaks_count_only_the_weeks_the_published_board_covers(env):  # noqa: F811
    full = (
        await env.client.get(PEAKS, params={"term_id": env.term_id, "group_by": "campus"}, headers=env.admin)
    ).json()
    full_p4 = next(c for c in full["cells"] if (c["day"], c["period"]) == (2, 4))["value"]
    await _trim_board_to_weeks(env.run_id, {1, 2})
    r = await env.client.get(PEAKS, params={"term_id": env.term_id, "group_by": "campus"}, headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    # 2 weeks of data: the empty weeks 3-15 are neither numerator nor denominator
    assert out["weeks"] == [1, 2] and out["confidence"] == "low"
    p4 = next(c for c in out["cells"] if (c["day"], c["period"]) == (2, 4))
    assert p4["n_weeks"] == 2
    assert p4["value"] > 0.6 * full_p4 and p4["value"] > 50, (p4, full_p4)
    assert out["peaks"], "the trimmed board still has its peak hours"


# ------------------------------------------------------------------------------------------------ AS20-F03


async def test_as20_f03_an_academician_gets_the_campus_peaks_for_find_room(env):  # noqa: F811
    _, ayse = await env.user("ayse.akademisyen@uni.edu.tr", role="TEACHER", firstname="Ayşe", lastname="Yılmaz")
    assert (await env.client.get(PEAKS, params={"term_id": env.term_id}, headers=ayse)).status_code == 403
    r = await env.client.get(f"{PEAKS}/campus", params={"term_id": env.term_id}, headers=ayse)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["group_by"] == "campus" and out["confidence"] != "none"
    assert {c["group"] for c in out["cells"]} == {"*"}
    assert out["peaks"] and all(c["value"] >= out["threshold_pct"] for c in out["peaks"])
    # aggregate only: no run labels or ids for a person without planning access
    assert "sources" not in out
    assert (await env.client.get(f"{PEAKS}/campus", params={"term_id": env.term_id})).status_code == 401


# ------------------------------------------------------------------------------------------------ AS20-F04


async def _exam(term_id: int, **kw) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        ex = ExamRequest(
            term_id=term_id, course_code=kw.pop("code", "PRO206"), course_name="Final", needs_room=True, **kw
        )
        s.add(ex)
        await s.commit()
        return int(ex.id)


async def test_as20_f04_apply_an_advisor_move_and_undo_it(env):  # noqa: F811
    p = n.PERIODS
    a = await _exam(
        env.term_id,
        date=date(2026, 6, 3),
        start_period=3,
        end_period=4,
        merge_key="PRO206",
        start_time=p[2].start,
        end_time=p[3].end,
    )
    b = await _exam(env.term_id, date=date(2026, 6, 3), start_period=3, end_period=5, merge_key="PRO206")
    url = "/api/v1/analytics/forecast/exams/advice/apply"
    body = {"term_id": env.term_id, "request_ids": [a, b], "date": "2026-06-01", "start_period": 5}
    # a viewer may not; a planner may
    _, ayse = await env.user("ayse.akademisyen@uni.edu.tr", role="TEACHER")
    assert (await env.client.post(url, json=body, headers=ayse)).status_code == 403
    r = await env.client.post(url, json=body, headers=env.planner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert sorted(out["applied"]) == sorted([a, b])
    assert out["undo"] == {
        "term_id": env.term_id,
        "request_ids": sorted([a, b]),
        "date": "2026-06-03",
        "start_period": 3,
    }
    assert out["message_tr"] and out["message_en"]
    async with dbmod.get_session_factory()() as s:
        ea, eb = await s.get(ExamRequest, a), await s.get(ExamRequest, b)
        assert ea is not None and eb is not None
        # each row keeps its own length; the clock times follow the period grid
        assert (ea.date, ea.start_period, ea.end_period) == (date(2026, 6, 1), 5, 6)
        assert (eb.date, eb.start_period, eb.end_period) == (date(2026, 6, 1), 5, 7)
        assert (ea.start_time, ea.end_time) == (p[4].start, p[5].end)
        assert eb.start_time is None
    r = await env.client.post(url, json=out["undo"], headers=env.planner)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        ea = await s.get(ExamRequest, a)
        assert ea is not None and (ea.date, ea.start_period, ea.end_period) == (date(2026, 6, 3), 3, 4)
        assert (ea.start_time, ea.end_time) == (p[2].start, p[3].end)
    # an id of another term, or an unknown one, changes nothing
    r = await env.client.post(url, json={**body, "request_ids": [a, 999_999]}, headers=env.planner)
    assert r.status_code == 404 and r.json()["detail"]["message_tr"]
    # a locked exam is not moved
    async with dbmod.get_session_factory()() as s:
        ea = await s.get(ExamRequest, a)
        assert ea is not None
        ea.status = "LOCKED"
        await s.commit()
    r = await env.client.post(url, json=body, headers=env.planner)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "exam_locked"


# ------------------------------------------------------------------------------------------------ CH12-F01


async def test_ch12_f01_weekly_chart_covers_the_term_when_the_calendar_lists_two_weeks(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    assert (await env.book(ayse, "A101", TODAY, "P1")).status_code == 201  # Mon 16 Feb, week 3
    async with dbmod.get_session_factory()() as s:
        await s.execute(delete(Week).where(Week.term_id == env.term_id, Week.index > 2))
        term = await s.get(Term, env.term_id)
        assert term is not None
        week_count = int(term.week_count or 0)
        await s.commit()
    assert week_count >= 14
    r = await env.client.get("/api/v1/bookings/stats/weekly", params={"term_id": env.term_id}, headers=env.admin)
    assert r.status_code == 200, r.text
    weeks = r.json()["weeks"]
    assert [w["week"] for w in weeks][:week_count] == list(range(1, week_count + 1))
    w3 = weeks[2]
    assert (w3["start"], w3["end"]) == ("2026-02-16", "2026-02-22") and w3["bookings"] == 1 and w3["partial"]
