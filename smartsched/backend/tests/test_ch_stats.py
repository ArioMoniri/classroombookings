"""Chart aggregates CH-07, CH-10, CH-11 (docs/design/v3/charts.md "CH-07 … CH-11 notes"; the frontend parses exactly
these shapes in ``smartsched/frontend/src/lib/api/stats.ts``). All three routes are read-only.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00, Bahar week 3). The term runs 2 Feb - 28 Jun
2026 with 19 week rows: weeks 1-15 lectures, 16 "Yaz Dönemi", 17-18 "Final" (EXAM), 19 "BÜT 22 - 24 Haziran"
(MAKEUP). A 101 and A 102 are free at P1 on the days booked here; PSY 262 (instructor Ezgi Soncu Büyükişcan) is on the
published board on Mondays P7-P9.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core import db as dbmod
from app.importers import normalize as n
from app.models import ApprovalRequest, AuditEvent, Booking, Instructor, Term
from app.services import chart_stats
from sqlalchemy import select, update

from tests.cal_support import link_instructor, psy262
from tests.crbs_env import TODAY, env  # noqa: F401

IST = ZoneInfo("Europe/Istanbul")
WEEKLY = "/api/v1/bookings/stats/weekly"
DAILY = "/api/v1/audit/stats/daily"
LOAD = "/api/v1/me/load"
APPR = "/api/v1/approvals"


# --------------------------------------------------------------------------------------------------
# CH-07 bookings per week + booking request outcomes
# --------------------------------------------------------------------------------------------------


async def _people(env):  # type: ignore[no-untyped-def]  # noqa: F811
    _, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    return gozde, aid, ayse


async def _submitted_at(request_id: int, when_utc: datetime) -> None:
    """The submission time of a request (rows store naive UTC; the fixture clock is not the wall clock)."""
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ApprovalRequest).where(ApprovalRequest.id == request_id).values(requested_at=when_utc))
        await s.commit()


async def _weekly_activity(env):  # type: ignore[no-untyped-def]  # noqa: F811
    """Three live bookings, one cancelled; four requests: approved, rejected, pending, withdrawn."""
    c = env.client
    gozde, _, ayse = await _people(env)
    assert (await env.book(ayse, "A101", TODAY, "P1", notes="FZT 132 telafi")).status_code == 201  # week 3
    assert (await env.book(ayse, "A102", date(2026, 2, 19), "P1")).status_code == 201  # week 3
    assert (await env.book(ayse, "A102", date(2026, 2, 26), "P1")).status_code == 201  # week 4
    r = await env.book(ayse, "A101", date(2026, 2, 17), "P1")
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/bookings/{r.json()['id']}/cancel", json={"reason": "Ders iptal"}, headers=ayse)
    assert r.status_code in (200, 204), r.text
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    assert r.status_code == 200, r.text
    for d in (date(2026, 3, 5), date(2026, 3, 12), date(2026, 3, 19), date(2026, 3, 26)):
        r = await env.book(ayse, "A102", d, "P1", notes="Telafi dersi")
        assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    mine = sorted((await c.get(f"{APPR}/mine", headers=ayse)).json(), key=lambda x: x["id"])
    ids = [m["id"] for m in mine]
    assert len(ids) == 4
    r = await c.post(f"{APPR}/{ids[0]}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 200, r.text
    r = await c.post(
        f"{APPR}/{ids[1]}/decide",
        json={"decision": "reject", "reason_code": "policy", "reason": "Bölüm sınavı var"},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"{APPR}/{ids[3]}/withdraw", json={}, headers=ayse)
    assert r.status_code == 200, r.text
    # submitted Mon 16 Feb 09:00, Sun 22 Feb 23:59 and Mon 23 Feb 00:30 (Istanbul), withdrawn one on Tue 17 Feb
    await _submitted_at(ids[0], datetime(2026, 2, 16, 6, 0))
    await _submitted_at(ids[1], datetime(2026, 2, 22, 20, 59))
    await _submitted_at(ids[2], datetime(2026, 2, 22, 21, 30))
    await _submitted_at(ids[3], datetime(2026, 2, 17, 7, 0))
    return ids


async def _recount(term_id: int, weeks: list[dict]) -> tuple[list[int], list[dict[str, int]]]:  # type: ignore[type-arg]
    """Independent SQL recount: live BOOKED rows by date; requests by Istanbul submission day, current status."""
    async with dbmod.get_session_factory()() as s:
        days = list(
            (
                await s.execute(select(Booking.date).where(Booking.term_id == term_id, Booking.status == "BOOKED"))
            ).scalars()
        )
        reqs = (
            await s.execute(
                select(ApprovalRequest.requested_at, ApprovalRequest.status).where(ApprovalRequest.term_id == term_id)
            )
        ).all()
    bookings, outcomes = [], []
    for w in weeks:
        lo, hi = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
        bookings.append(sum(1 for d in days if lo <= d <= hi))
        cnt: Counter[str] = Counter()
        for at, st in reqs:
            local = at.replace(tzinfo=UTC).astimezone(IST).date()
            if lo <= local <= hi:
                cnt[st] += 1
        outcomes.append({"approved": cnt["APPROVED"], "rejected": cnt["REJECTED"], "pending": cnt["PENDING"]})
    return bookings, outcomes


async def test_ch_07_weekly_counts_equal_a_sql_recount_on_the_bahar_term(env):  # noqa: F811
    await _weekly_activity(env)
    r = await env.client.get(WEEKLY, params={"term_id": env.term_id}, headers=env.admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["term_id"] == env.term_id
    assert (body["from"], body["to"], body["today"]) == ("2026-02-02", "2026-06-28", "2026-02-16")
    weeks = body["weeks"]
    assert [w["week"] for w in weeks] == list(range(1, 20))
    assert set(weeks[0]) == {"week", "start", "end", "exam", "partial", "bookings", "requests"}
    assert (weeks[0]["start"], weeks[0]["end"]) == ("2026-02-02", "2026-02-08")
    assert (weeks[16]["start"], weeks[18]["start"]) == ("2026-06-01", "2026-06-22")
    bookings, outcomes = await _recount(env.term_id, weeks)
    assert [w["bookings"] for w in weeks] == bookings
    assert [w["requests"] for w in weeks] == outcomes
    # week 3: two live bookings (the cancelled one is gone), the approved request (submitted Mon 09:00) and the one
    # rejected at Sun 23:59; week 4: one booking + the request sent at 00:30 Monday (Istanbul, 21:30 UTC Sunday)
    assert weeks[2]["bookings"] == 2 and weeks[2]["requests"] == {"approved": 1, "rejected": 1, "pending": 0}
    assert weeks[3]["bookings"] == 1 and weeks[3]["requests"] == {"approved": 0, "rejected": 0, "pending": 1}
    # the approved request became a live booking on Thu 5 Mar (week 5); the withdrawn one counts nowhere
    assert weeks[4]["bookings"] == 1
    assert sum(sum(w["requests"].values()) for w in weeks) == 3
    assert sum(w["bookings"] for w in weeks) == 4


async def test_ch_07_exam_weeks_come_from_the_term_calendar_and_today_marks_the_partial_week(env):  # noqa: F811
    weeks = (await env.client.get(WEEKLY, params={"term_id": env.term_id}, headers=env.admin)).json()["weeks"]
    assert [w["week"] for w in weeks if w["exam"]] == [17, 18, 19]  # Final 1-7, 8-14 Haziran, BÜT
    assert [w["week"] for w in weeks if w["partial"]] == [3]  # Monday 16 Feb 2026 is inside week 3


async def test_ch_07_a_week_cut_off_by_the_term_end_is_partial_and_ends_on_that_day(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(Term).where(Term.id == env.term_id).values(end_date=date(2026, 6, 24)))
        await s.commit()
    body = (await env.client.get(WEEKLY, params={"term_id": env.term_id}, headers=env.admin)).json()
    last = body["weeks"][-1]
    assert (last["week"], last["start"], last["end"], last["partial"], last["exam"]) == (
        19,
        "2026-06-22",
        "2026-06-24",
        True,
        True,
    )
    assert body["to"] == "2026-06-24"


async def test_ch_07_needs_the_export_permission_and_a_known_term(env):  # noqa: F811
    _, teacher = await env.user("ogretmen.istatistik@uni.edu.tr")
    r = await env.client.get(WEEKLY, params={"term_id": env.term_id}, headers=teacher)
    assert r.status_code == 403, r.text
    r = await env.client.get(WEEKLY, params={"term_id": 999_999}, headers=env.admin)
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "term_not_found" and detail["message_tr"] == "Dönem bulunamadı."
    assert (await env.client.get(WEEKLY, params={"term_id": env.term_id})).status_code == 401


# --------------------------------------------------------------------------------------------------
# CH-10 audit events per day (Europe/Istanbul)
# --------------------------------------------------------------------------------------------------


def _ist(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> datetime:
    """An Istanbul wall-clock time as the naive UTC the audit table stores."""
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST).astimezone(UTC).replace(tzinfo=None)


async def _events_at(*stamps: datetime) -> None:
    async with dbmod.get_session_factory()() as s:
        for i, ts in enumerate(stamps):
            s.add(
                AuditEvent(
                    ts=ts,
                    actor_label="Gözde Ayrancıgil",
                    action="booking.create",
                    entity_type="booking",
                    entity_id=str(900_000 + i),
                    reversible=False,
                )
            )
        await s.commit()


async def test_ch_10_days_are_istanbul_days_zero_filled_and_match_the_list_filter(env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(chart_stats, "utcnow", lambda: _ist(2026, 10, 13, 15, 0).replace(tzinfo=UTC))
    # 23:59:59 on Mon 12 Oct and 00:00 on Tue 13 Oct (Istanbul) are one UTC day (20:59:59 / 21:00 on the 12th)
    await _events_at(_ist(2026, 10, 12, 23, 59, 59), _ist(2026, 10, 13, 0, 0), _ist(2026, 10, 13, 14, 0))
    await _events_at(_ist(2026, 9, 13, 23, 59))  # one day before the 30-day window
    r = await env.client.get(DAILY, headers=env.admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["from"], body["to"]) == ("2026-09-14", "2026-10-13")
    days = body["days"]
    assert len(days) == 30 and [d["day"] for d in days] == [
        (date(2026, 9, 14) + timedelta(days=i)).isoformat() for i in range(30)
    ]
    by = {d["day"]: d["events"] for d in days}
    assert by["2026-10-12"] == 1 and by["2026-10-13"] == 2
    assert sum(by.values()) == 3 and by["2026-09-14"] == 0
    # a click on a column filters the list to that Istanbul day: the same events
    lst = await env.client.get("/api/v1/audit", params={"from": "2026-10-13", "to": "2026-10-13"}, headers=env.admin)
    assert lst.status_code == 200 and len(lst.json()["items"]) == 2, lst.text
    lst = await env.client.get("/api/v1/audit", params={"from": "2026-10-12", "to": "2026-10-12"}, headers=env.admin)
    assert len(lst.json()["items"]) == 1
    r = await env.client.get(DAILY, params={"days": 7}, headers=env.admin)
    assert [d["day"] for d in r.json()["days"]][0] == "2026-10-07" and len(r.json()["days"]) == 7


async def test_ch_10_counts_real_events_of_today(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    assert (await env.book(ayse, "A101", TODAY, "P1")).status_code == 201
    today = datetime.now(IST).date().isoformat()
    body = (await env.client.get(DAILY, params={"days": 1}, headers=env.admin)).json()
    assert body["from"] == body["to"] == today
    lst = (
        await env.client.get("/api/v1/audit", params={"from": today, "to": today, "limit": 500}, headers=env.admin)
    ).json()
    assert body["days"] == [{"day": today, "events": len(lst["items"])}] and len(lst["items"]) >= 1


async def test_ch_10_needs_audit_view_and_a_sane_range(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    assert (await env.client.get(DAILY, headers=ayse)).status_code == 403
    assert (await env.client.get(DAILY, params={"days": 0}, headers=env.admin)).status_code == 422
    assert (await env.client.get(DAILY, params={"days": 91}, headers=env.admin)).status_code == 422
    assert (await env.client.get(DAILY)).status_code == 401


# --------------------------------------------------------------------------------------------------
# CH-11 my weekly teaching load (own linked instructor record only)
# --------------------------------------------------------------------------------------------------


async def _board_cells(env, instructor_id: int) -> dict[int, set[int]]:  # type: ignore[no-untyped-def]  # noqa: F811
    """Independent recount: the published board's (day, period) cells of the instructor's courses."""
    from app.models import Assignment, Course, Section, SectionInstructor

    async with dbmod.get_session_factory()() as s:
        codes = {
            n.course_key(c)
            for c in (
                await s.execute(
                    select(Course.code)
                    .join(Section, Section.course_id == Course.id)
                    .join(SectionInstructor, SectionInstructor.section_id == Section.id)
                    .where(SectionInstructor.instructor_id == instructor_id, Section.term_id == env.term_id)
                )
            ).scalars()
        }
        rows = (
            await s.execute(select(Assignment).where(Assignment.run_id == env.run_id, Assignment.archived.is_(False)))
        ).scalars()
        cells: dict[int, set[int]] = {}
        for a in rows:
            keys = {n.course_key(str(c)) for c in a.course_codes or []} or {n.course_key(a.label or "")}
            if keys & codes:
                cells.setdefault(a.day, set()).update(range(a.start_period, a.end_period + 1))
    return cells


async def test_ch_11_my_load_is_the_published_board_of_my_own_instructor_record(env):  # noqa: F811
    p = await psy262(env)
    uid, ezgi = await env.user("ezgi.soncu@uni.edu.tr", firstname="Ezgi", lastname="Soncu Büyükişcan")
    await link_instructor(uid, p.instructor_id)
    r = await env.client.get(LOAD, headers=ezgi)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"linked", "instructor_id", "term_id", "run_id", "days", "total_periods"}
    assert body["linked"] is True and body["instructor_id"] == p.instructor_id
    assert body["term_id"] == env.term_id and body["run_id"] == env.run_id
    assert [d["day"] for d in body["days"]] == [1, 2, 3, 4, 5, 6, 7]
    cells = await _board_cells(env, p.instructor_id)
    assert {d["day"]: d["periods"] for d in body["days"]} == {d: len(cells.get(d, set())) for d in range(1, 8)}
    mon = body["days"][0]
    assert {7, 8, 9} <= cells[1] and mon["periods"] >= 3  # PSY 262 Mondays P7-P9 (13:30-15:50)
    grid = {i + 1: p_ for i, p_ in enumerate(n.PERIODS)}
    minutes = {
        d: sum(
            (datetime.combine(TODAY, grid[k].end) - datetime.combine(TODAY, grid[k].start)).seconds // 60
            for k in cells.get(d, set())
        )
        for d in range(1, 8)
    }
    assert {d["day"]: d["minutes"] for d in body["days"]} == minutes
    assert body["total_periods"] == sum(d["periods"] for d in body["days"])
    same = (await env.client.get(LOAD, params={"term_id": env.term_id}, headers=ezgi)).json()
    assert same == body


async def test_ch_11_a_user_never_sees_another_instructors_load(env):  # noqa: F811
    p = await psy262(env)
    async with dbmod.get_session_factory()() as s:
        other = (
            (await s.execute(select(Instructor.id).where(Instructor.id != p.instructor_id).order_by(Instructor.id)))
            .scalars()
            .first()
        )
    assert other is not None
    uid_e, ezgi = await env.user("ezgi.soncu@uni.edu.tr", firstname="Ezgi", lastname="Soncu Büyükişcan")
    uid_o, okan = await env.user("okan.diger@uni.edu.tr", firstname="Okan", lastname="Işık")
    await link_instructor(uid_e, p.instructor_id)
    await link_instructor(uid_o, other)
    mine = (await env.client.get(LOAD, headers=okan)).json()
    assert mine["linked"] is True and mine["instructor_id"] == other
    # no parameter picks someone else's record
    r = await env.client.get(LOAD, params={"instructor_id": p.instructor_id, "user_id": uid_e}, headers=okan)
    assert r.status_code == 200 and r.json()["instructor_id"] == other and r.json() == mine
    cells = await _board_cells(env, other)
    assert mine["total_periods"] == sum(len(v) for v in cells.values())


async def test_ch_11_without_an_instructor_record_the_load_is_empty_and_unlinked(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    body = (await env.client.get(LOAD, headers=ayse)).json()
    assert body == {
        "linked": False,
        "instructor_id": None,
        "term_id": env.term_id,
        "run_id": None,
        "days": [],
        "total_periods": 0,
    }
    assert (await env.client.get(LOAD)).status_code == 401
    r = await env.client.get(LOAD, params={"term_id": 999_999}, headers=ayse)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "term_not_found"


async def test_ch_11_no_published_run_means_no_run_and_no_days(env):  # noqa: F811
    p = await psy262(env)
    uid, ezgi = await env.user("ezgi.soncu@uni.edu.tr", firstname="Ezgi", lastname="Soncu Büyükişcan")
    await link_instructor(uid, p.instructor_id)
    from app.models import ScheduleRun

    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()
    body = (await env.client.get(LOAD, headers=ezgi)).json()
    assert body["linked"] is True and body["instructor_id"] == p.instructor_id
    assert body["run_id"] is None and body["days"] == [] and body["total_periods"] == 0
