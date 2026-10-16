"""P2 conflict resolver after publishing, on the real Bahar 2026 board (``tests/crbs_env``).

Story: the planning office has not published the Bahar board yet (the imported grid run is taken off the booking
grid), teachers book 30 rooms anyway (A-24 ``confirm_unpublished``) on slots the board holds and the planner books a
4-week series for a teacher on a weekly class's slot. Then the board is published: every one of those bookings is a
conflict, the resolver offers a room / period / day or says why not, a batch apply of all of them is atomic and
fast, and each owner gets one digest."""

from __future__ import annotations

import time
from collections import Counter
from datetime import date, timedelta

from app.core import db as dbmod
from app.models import Assignment, AuditEvent, Booking, InAppNotification, NotificationOutbox, ScheduleRun
from app.models.conflicts import BookingConflict
from sqlalchemy import func, select, update

from tests.crbs_env import env  # noqa: F401
from tests.wave2_support import exam_run_id

C = "/api/v1/bookings/conflicts"


async def _unpublish(run_id: int) -> None:
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == run_id).values(is_active=False))
        await s.commit()


async def _board_slots(run_id: int, d_from: date, d_to: date) -> list[tuple[int, date, int]]:
    """(room id, date, period) of single-room classes of the board, one per (room, date), spread over the days."""
    async with dbmod.get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Assignment)
                .where(Assignment.run_id == run_id, Assignment.date.between(d_from, d_to))
                .order_by(Assignment.date, Assignment.start_period, Assignment.id)
            )
        ).scalars()
        seen: set[tuple[int, date]] = set()
        out = []
        for a in rows:
            if len(a.room_ids or []) != 1 or a.start_period < 2:
                continue
            key = (int(a.room_ids[0]), a.date)
            if key in seen:
                continue
            seen.add(key)
            out.append((int(a.room_ids[0]), a.date, a.start_period))
        return out


async def _weekly_slot(run_id: int, weeks: list[date]) -> tuple[int, int] | None:
    """(room id, period) a class of the board holds on every date of ``weeks`` (same weekday)."""
    async with dbmod.get_session_factory()() as s:
        held: Counter[tuple[int, int]] = Counter()
        for d in weeks:
            rows = (
                await s.execute(select(Assignment).where(Assignment.run_id == run_id, Assignment.date == d))
            ).scalars()
            for key in {(int(a.room_ids[0]), a.start_period) for a in rows if len(a.room_ids or []) == 1}:
                held[key] += 1
        full = sorted(k for k, v in held.items() if v == len(weeks))
        return full[0] if full else None


async def test_publishing_opens_the_resolver_and_a_batch_apply_is_atomic(env):  # noqa: F811
    users = [await env.user(f"ogretmen{i}@uni.edu.tr") for i in range(3)]
    await _unpublish(env.run_id)
    by_id = {v: k for k, v in env.rooms.items()}
    made: list[int] = []
    for rid, d, p in await _board_slots(env.run_id, date(2026, 2, 17), date(2026, 3, 13)):
        if len(made) == 30:
            break
        _, headers = users[len(made) % 3]
        r = await env.book(headers, by_id[rid], d, f"P{p}", confirm_unpublished=True, notes="Kulüp toplantısı")
        if r.status_code == 201:
            made.append(r.json()["id"])
    assert len(made) == 30
    weds = [date(2026, 2, 18) + timedelta(weeks=i) for i in range(4)]
    room_p = await _weekly_slot(env.run_id, weds)
    assert room_p is not None
    s_room, s_period = room_p
    uid0 = users[0][0]
    r = await env.client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": s_room,
            "period_id": env.periods[f"P{s_period}"],
            "date": weds[0].isoformat(),
            "start": weds[0].isoformat(),
            "end": weds[-1].isoformat(),
            "user_id": uid0,
        },
        headers=env.planner,
    )
    assert r.status_code == 201, r.text
    series_id = r.json()["series_id"]
    assert len(r.json()["created"]) == 4

    # publishing the board opens the resolver
    r = await env.client.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200, r.text
    r = await env.client.get(f"{C}/summary", headers=env.planner)
    run_sum = next(x for x in r.json()["runs"] if x["run_id"] == env.run_id)
    assert run_sum["open"] == 34 and run_sum["series"] == 1
    assert run_sum["message_tr"] == "Yayınlanan programla çakışan 34 rezervasyon (1 seri) · Çöz"
    _, teacher = users[1]
    assert (await env.client.get(f"{C}/summary", headers=teacher)).status_code == 403

    r = await env.client.get(f"{C}/{env.run_id}/plan", headers=env.planner)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["open"] == 34 and len(plan["groups"]) == 31
    series = next(g for g in plan["groups"] if g["series_id"] == series_id)
    assert len(series["conflicts"]) == 4 and series["default_scope"] == "one"
    for g in plan["groups"]:
        moves = [o for o in g["options"] if o["kind"].startswith("move_")]
        assert moves or g["no_room_reason"]["tr"].startswith("Yayınlanan programla çakıştı, uygun oda bulunamadı")
        assert {"cancel"} <= {o["kind"] for o in g["options"]}
        assert "override" not in {o["kind"] for o in g["options"]}  # the planner is not planning.admin
        for c in g["conflicts"]:
            assert c["held"]["label"]  # what the board puts there (course code)
    room_opts = [o for g in plan["groups"] for o in g["options"] if o["kind"] == "move_room"]
    assert room_opts and all(
        o["room_id"] != g["room_id"] for g in plan["groups"] for o in g["options"] if o["kind"] == "move_room"
    )

    # the suggestions (distinct rooms per slot), the rest cancelled; one invalid item rolls every item back
    r = await env.client.post(f"{C}/{env.run_id}/auto", headers=env.planner)
    assert r.status_code == 200, r.text
    auto = r.json()
    good = [*auto["items"]]
    good += [
        {"conflict_id": u["conflict_id"], "action": "cancel", "reason": "Uygun oda yok"} for u in auto["unresolved"]
    ]
    assert len(good) == 34 and len(auto["items"]) >= 20
    bad = [*good, {"conflict_id": good[0]["conflict_id"] + 100000, "action": "cancel"}]
    r = await env.client.post(f"{C}/{env.run_id}/apply", json={"items": bad}, headers=env.planner)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_items"
    assert "hiçbir değişiklik yapılmadı" in r.json()["detail"]["message_tr"]
    async with dbmod.get_session_factory()() as s:
        n_open = (
            await s.execute(
                select(func.count()).where(BookingConflict.run_id == env.run_id, BookingConflict.status == "OPEN")
            )
        ).scalar_one()
        assert n_open == 34
        assert (await s.get(Booking, made[0])).notes == "Kulüp toplantısı"

    # the planner may not keep a clashing booking (administrator only)
    r = await env.client.post(
        f"{C}/{env.run_id}/apply",
        json={"items": [{"conflict_id": good[0]["conflict_id"], "action": "override", "reason": "x"}]},
        headers=env.planner,
    )
    assert r.status_code == 409 and r.json()["detail"]["problems"][0]["code"] == "override_forbidden"

    # dry run, then the batch: under 2 s, all applied
    r = await env.client.post(f"{C}/{env.run_id}/apply", json={"items": good, "dry_run": True}, headers=env.planner)
    assert r.status_code == 200 and r.json()["dry_run"] is True, r.text
    t0 = time.perf_counter()
    r = await env.client.post(f"{C}/{env.run_id}/apply", json={"items": good}, headers=env.planner)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    out = r.json()
    assert elapsed < 2.0, elapsed
    assert len(out["moved"]) + len(out["cancelled"]) == 34
    assert out["notified"] == 3 and out["unnotified"] == 0
    # nothing clashes with the published board any more
    r = await env.client.get("/api/v1/bookings/conflicts", params={"term_id": env.term_id}, headers=env.planner)
    left = {x["booking_id"] for x in r.json()}
    assert not (left & set(made))
    async with dbmod.get_session_factory()() as s:
        statuses = Counter(
            (await s.execute(select(BookingConflict.status).where(BookingConflict.run_id == env.run_id))).scalars()
        )
        assert statuses == {"RESOLVED": 34}
        # one digest per owner: in-app + e-mail, not one per booking
        uid_a = users[0][0]
        notes = list(
            (
                await s.execute(
                    select(InAppNotification).where(
                        InAppNotification.user_id == uid_a, InAppNotification.kind == "booking.conflict_resolved"
                    )
                )
            ).scalars()
        )
        assert len(notes) == 1
        assert notes[0].title.startswith("Rezervasyonlarınız yeni programa göre güncellendi: 14 değişiklik")
        assert len(notes[0].body.splitlines()) == 14 and "→" in notes[0].body
        mails = (
            await s.execute(
                select(func.count()).where(
                    NotificationOutbox.user_id == uid_a, NotificationOutbox.kind == "booking_conflict_resolved"
                )
            )
        ).scalar_one()
        assert mails == 1
        acts = Counter((await s.execute(select(AuditEvent.action))).scalars())
        assert acts["booking_conflict.detect"] == 1 and acts["booking_conflict.resolve"] >= 1
        assert acts["booking.move"] + acts["booking.cancel"] >= 1

    # idempotent: the same payload again changes nothing and sends nothing
    r = await env.client.post(f"{C}/{env.run_id}/apply", json={"items": good}, headers=env.planner)
    assert r.status_code == 200 and r.json()["moved"] == [] and len(r.json()["already"]) == len(good)
    async with dbmod.get_session_factory()() as s:
        n = (
            await s.execute(
                select(func.count()).where(
                    InAppNotification.user_id == uid_a, InAppNotification.kind == "booking.conflict_resolved"
                )
            )
        ).scalar_one()
        assert n == 1

    # a run that is not published has no plan
    r = await env.client.get(f"{C}/{await exam_run_id(env.term_id)}/plan", headers=env.planner)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "plan_stale"


async def test_auto_suggestions_and_admin_override(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    await _unpublish(env.run_id)
    by_id = {v: k for k, v in env.rooms.items()}
    ids = []
    for rid, d, p in (await _board_slots(env.run_id, date(2026, 2, 17), date(2026, 2, 20)))[:6]:
        r = await env.book(ayse, by_id[rid], d, f"P{p}", confirm_unpublished=True)
        if r.status_code == 201:
            ids.append(r.json()["id"])
    assert len(ids) >= 4
    r = await env.client.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200
    r = await env.client.post(f"{C}/{env.run_id}/auto", headers=env.planner)
    assert r.status_code == 200, r.text
    auto = r.json()
    assert auto["dry_run"] is True and len(auto["items"]) + len(auto["unresolved"]) == len(ids)
    assert all(i["action"].startswith("move_") for i in auto["items"])
    # nothing changed by the suggestion
    async with dbmod.get_session_factory()() as s:
        assert (await s.execute(select(func.count()).where(BookingConflict.status == "OPEN"))).scalar_one() == len(ids)
    # the administrator keeps one booking with a reason (IGNORED), the plan shows the override option
    plan = (await env.client.get(f"{C}/{env.run_id}/plan", headers=env.admin)).json()
    g = plan["groups"][0]
    assert any(o["kind"] == "override" and o["admin_only"] for o in g["options"])
    cid = g["conflicts"][0]["conflict_id"]
    r = await env.client.post(
        f"{C}/{env.run_id}/apply", json={"items": [{"conflict_id": cid, "action": "override"}]}, headers=env.admin
    )
    assert r.status_code == 409 and r.json()["detail"]["problems"][0]["code"] == "reason"
    r = await env.client.post(
        f"{C}/{env.run_id}/apply",
        json={"items": [{"conflict_id": cid, "action": "override", "reason": "Dekanlık onaylı etkinlik"}]},
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()["kept"] == [cid]
    async with dbmod.get_session_factory()() as s:
        c = await s.get(BookingConflict, cid)
        assert c.status == "IGNORED" and c.resolution["reason"] == "Dekanlık onaylı etkinlik"
        b = await s.get(Booking, c.booking_id)
        assert b.status == "BOOKED"
    # re-scan finds nothing new
    r = await env.client.post(f"{C}/{env.run_id}/detect", headers=env.planner)
    assert r.status_code == 200 and r.json()["new"] == 0
