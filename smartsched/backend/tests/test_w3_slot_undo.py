"""Wave 3 W3-SLOT (quick-reserve.md §9): ``POST /bookings`` and ``POST /bookings/multi/{id}/create`` name the
``booking.create`` audit event of every booking they made (``audit_event_id``), so quick reserve's "Geri al" is the
real P7 undo (``POST /audit/{id}/undo``), recorded as an undo, not as a user cancellation."""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

DAY = date(2026, 2, 17)


async def test_w3_slot_single_create_names_its_audit_event_and_undo_cancels(env):  # noqa: F811
    _, teacher = await env.user("w3slot-undo@example.edu")
    r = await env.book(teacher, "A101", DAY, "P1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body["audit_event_id"], int)
    u = await env.client.post(f"/api/v1/audit/{body['audit_event_id']}/undo", headers=teacher)
    assert u.status_code == 200, u.text
    mine = (await env.client.get("/api/v1/bookings/mine", headers=teacher)).json()
    assert all(b["id"] != body["id"] for b in mine)
    # the slot is free again: the same booking can be made once more
    assert (await env.book(teacher, "A101", DAY, "P1")).status_code == 201


async def test_w3_slot_multi_create_names_an_event_per_booking(env):  # noqa: F811
    _, teacher = await env.user("w3slot-undo2@example.edu")
    grid = (
        await env.client.get(
            "/api/v1/bookings/grid", params={"display": "day", "date": DAY.isoformat()}, headers=teacher
        )
    ).json()
    order = {p["id"]: i for i, p in enumerate(grid["periods"])}
    free: dict[int, list[int]] = {}
    for s in grid["slots"]:
        if s["status"] == "available" and s.get("allow_single"):
            free.setdefault(s["room_id"], []).append(order[s["period_id"]])
    room, idx = next(
        (r, i) for r, ix in free.items() for i in sorted(ix) if i + 1 in ix
    )  # two consecutive free periods in one room
    slots = [{"date": DAY.isoformat(), "period_id": grid["periods"][i]["id"], "room_id": room} for i in (idx, idx + 1)]
    sel = await env.client.post("/api/v1/bookings/multi", json={"slots": slots}, headers=teacher)
    assert sel.status_code == 201, sel.text
    choices = [{"mbs_id": s["mbs_id"]} for s in sel.json()["slots"]]
    made = await env.client.post(
        f"/api/v1/bookings/multi/{sel.json()['id']}/create", json={"type": "single", "slots": choices}, headers=teacher
    )
    assert made.status_code == 200, made.text
    created = made.json()["created"]
    assert len(created) == 2
    events = [b["audit_event_id"] for b in created]
    assert all(isinstance(e, int) for e in events) and len(set(events)) == 2
    for e in events:
        assert (await env.client.post(f"/api/v1/audit/{e}/undo", headers=teacher)).status_code == 200
    mine = (await env.client.get("/api/v1/bookings/mine", headers=teacher)).json()
    assert not {b["id"] for b in created} & {b["id"] for b in mine}


async def test_w3_slot_my_totals_count_live_bookings_and_pending_apart(env):  # noqa: F811
    """Round-3 academician: "1 etkin · bu dönem 3 · toplam 3" next to one listed booking. Rejected, withdrawn and
    expired requests are not bookings; a pending request is shown apart (``totals.pending``)."""
    from app.core import db as dbmod
    from app.models import Booking

    _, teacher = await env.user("w3slot-totals@example.edu")
    day = date(2026, 2, 18).isoformat()
    grid = (
        await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": day}, headers=teacher)
    ).json()
    free = [s for s in grid["slots"] if s["status"] == "available" and s.get("allow_single")][:5]
    assert len(free) == 5
    ids = []
    for slot in free:
        body = {"room_id": slot["room_id"], "date": day, "period_id": slot["period_id"]}
        r = await env.client.post("/api/v1/bookings", json=body, headers=teacher)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    async with dbmod.get_session_factory()() as s:
        for bid, status in zip(ids[1:], ("REJECTED", "WITHDRAWN", "EXPIRED", "PENDING"), strict=True):
            (await s.get(Booking, bid)).status = status  # type: ignore[union-attr]
        await s.commit()
    totals = (await env.client.get("/api/v1/bookings/dashboard", headers=teacher)).json()["totals"]
    assert totals["all"] == 1 and totals["session"] == 1
    assert totals["pending"] == 1
