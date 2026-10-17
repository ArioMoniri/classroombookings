"""AS-04: season booking overlays and slot-level exam holds, on the real Bahar 2026 import (``tests/crbs_env``; weeks
17-18 are "Final 1 - 7 Haziran" / "Final 8 - 14 Haziran", kind EXAM) with a published exam run built from the real
Final 2026 list (``final_planlama_listesi_2026_v2.xlsx``: every dated row with a definitive room).

Real rows: Final list row 329, BP 244 on Thursday 4 June 2026 P9-P10 in A 105 (a PC lab) and row 333, BP 116 the
same day P6-P8 in A 105. With ``slots`` and a one-period buffer A 105 is held P5-P11 that day; P12 stays bookable.
"""

from __future__ import annotations

from datetime import date

from app.core import db as dbmod
from app.models import Assignment, ScheduleRun
from app.services import booking_policies as bp
from sqlalchemy import select, update

from tests.crbs_env import env  # noqa: F401

POL = "/api/v1/booking-policies"
JUNE4 = date(2026, 6, 4)


async def _publish_final_exam_run(env, parsed_exam_list) -> int:  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        await s.execute(
            update(ScheduleRun)
            .where(ScheduleRun.term_id == env.term_id, ScheduleRun.kind == "EXAM")
            .values(is_active=False)
        )
        run = ScheduleRun(
            term_id=env.term_id, kind="EXAM", horizon="TERM", status="FEASIBLE", is_active=True, label="Final 2026"
        )
        s.add(run)
        await s.flush()
        n = 0
        for r in parsed_exam_list.rows:
            codes = [c for c in getattr(r.definitive, "room_codes", []) if c in env.rooms]
            if r.date is None or not codes or not r.periods.start_period:
                continue
            s.add(
                Assignment(
                    run_id=run.id,
                    day=r.date.isoweekday(),
                    date=r.date,
                    start_period=r.periods.start_period,
                    end_period=r.periods.end_period,
                    room_ids=[env.rooms[c] for c in codes],
                    label=r.course_code,
                )
            )
            n += 1
        await s.commit()
        assert n > 500
        return run.id


async def test_as_04_slots_hold_only_exam_room_periods(env, parsed_exam_list):  # noqa: F811
    row = next(r for r in parsed_exam_list.rows if r.row == 329)
    assert (row.course_code, row.date, row.periods.start_period, row.periods.end_period) == ("BP244", JUNE4, 9, 10)
    assert "A105" in row.definitive.room_codes
    await _publish_final_exam_run(env, parsed_exam_list)
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "slots", "buffer_periods": 1}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "slots" and r.json()["buffer_periods"] == 1 and r.json()["slots_effect"] == "request"
    # in the exam slot: a request (owner default: holds are requests)
    r = await env.book(ayse, "A105", JUNE4, "P10")
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    # the buffer period after the exam is held too
    r = await env.client.get(
        f"{POL}/effective",
        params={"room_id": env.rooms["A105"], "date": JUNE4.isoformat(), "period_id": env.periods["P11"]},
        headers=ayse,
    )
    assert r.json()["verdict"] == "request"
    v = next(x for x in r.json()["violations"] if x["rule"] == "exam_period")
    assert "sınav" in v["message_tr"] and v["exam_slot"] == {"start": 9, "end": 10, "buffer": 1}
    # two periods after the exam: bookable under slots
    r = await env.book(ayse, "A105", JUNE4, "P12")
    assert r.status_code == 201, r.text
    # ... and refused under closed (the whole exam week)
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "closed"}, headers=env.admin)
    assert r.status_code == 200
    r = await env.book(ayse, "A105", JUNE4, "P13")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_exam_period"
    # slots with effect refuse
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "slots", "slots_effect": "refuse"}, headers=env.admin)
    assert r.status_code == 200
    r = await env.book(ayse, "A105", JUNE4, "P9")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_exam_period"
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "slots", "buffer_periods": 9}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["message_tr"]


async def test_as_04_b7_freed_room_periods(env, parsed_exam_list):  # noqa: F811
    await _publish_final_exam_run(env, parsed_exam_list)
    async with dbmod.get_session_factory()() as s:
        out = await bp.slot_hold_summary(s, env.term_id, buffer_periods=1)
    assert out["closed_room_periods"] > out["held_room_periods"] > 0
    assert out["freed_room_periods"] == out["closed_room_periods"] - out["held_room_periods"] > 0
    assert out["exam_run_id"] and out["rooms"] >= 10
    # no exam room-period is bookable under slots: every exam assignment's periods are held
    async with dbmod.get_session_factory()() as s:
        held = await bp.exam_slot_index(s, env.term_id, 1)
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == out["exam_run_id"]))).scalars())
    for a in rows:
        for rid in a.room_ids:
            for p in range(a.start_period, a.end_period + 1):
                assert held.covers(int(rid), a.date, p, p) is not None


async def test_as_04_profile_overlay_caps_pc_labs_only_in_exam_weeks(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    body = {
        "key": "final-pc",
        "name_tr": "Final haftası",
        "name_en": "Final week",
        "applies_to": [{"season": "*", "period_kind": "EXAM"}],
        "booking_overlays": [{"scope": "tag:PC", "max_active_bookings": 2}],
    }
    r = await env.client.post("/api/v1/seasons/profiles", json=body, headers=env.admin)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    june9, june10, june11 = date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)
    # a draft does nothing: three June PC bookings ... the third is checked after activation
    assert (await env.book(ayse, "A103", june9, "P13")).status_code == 201
    assert (await env.book(ayse, "A104", june10, "P13")).status_code == 201
    assert (await env.client.post(f"/api/v1/seasons/profiles/{pid}/activate", headers=env.admin)).status_code == 200
    r = await env.book(ayse, "A105", june11, "P13")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "policy_max_active"
    assert d["message_tr"].startswith("Final haftası profili (Sınav dönemi): ") and "en fazla 2" in d["message_tr"]
    assert d["message_en"].startswith("Final week profile (Exam period): ")
    assert d["why"]["source"] == "season_profile" and d["why"]["profile"] == "profile:final-pc@1"
    # lecture weeks are not capped; a non-PC room in June is not either
    assert (await env.book(ayse, "A105", date(2026, 2, 18), "P13")).status_code == 201
    assert (await env.book(ayse, "A101", june11, "P13")).status_code == 201
    # the "Neden?" view lists the overlay
    r = await env.client.get(
        f"{POL}/effective",
        params={"room_id": env.rooms["A105"], "date": june11.isoformat(), "period_id": env.periods["P13"]},
        headers=ayse,
    )
    eff = r.json()
    assert eff["verdict"] == "refuse"
    assert eff["season_overlays"][0]["profile"] == "profile:final-pc@1"
    assert eff["season_overlays"][0]["period_kind"] == "EXAM"
    # administrators are not bound
    assert (await env.book(env.admin, "A105", june11, "P14")).status_code == 201
