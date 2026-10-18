"""HB-05 helper writes: preview, signed confirm token, once-only claim, audit and undo, on the real Bahar 2026 data
(``tests/crbs_env``; clock Monday 16 Feb 2026 08:00; A 102 is free at P1 on Thursday 19 Feb).

* nothing is written without confirm (the card endpoint previews only);
* a reused / expired / other user's / forged token → 409 / 410 / 403 / 403, each audited ``helper.confirm_rejected``;
* a slot taken between preview and confirm → 409 with free alternatives;
* undo within the window and before the start, refused after;
* approval mode ``all`` turns ``create_booking`` into a request;
* own-only cancel and withdraw, the approver's decision (a rejection needs a reason), undo of the last action;
* the write actions pass the same drift check as the reads.
"""

from __future__ import annotations

from datetime import date, datetime

from app.ai.helper import confirm as cf
from app.ai.helper import schema
from app.ai.helper.actions import registry as reg
from app.core import db as dbmod
from app.models import ApprovalRequest, AuditEvent, Booking
from app.models.helper import HelperActionInvocation
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, card, personas
from tests.helper.test_hb_03_registry import _fields, _gate, _guard_perms, _route

THU = date(2026, 2, 19)
WRITES = ["create_booking", "cancel_my_booking", "withdraw_my_request", "decide_approval", "undo_last_helper_action"]


async def _count(model, *where) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())


async def _book_card(env, p, room: str = "A 102", period: str = "P1"):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await card(env, p, "create_booking", room=room, date=THU.isoformat(), period_id=env.periods[period])
    assert r.status_code == 200, r.text
    return r.json()


async def _confirm(env, p, token: str):  # type: ignore[no-untyped-def]  # noqa: F811
    return await env.client.post(f"{H}/actions/confirm", json={"token": token}, headers=p.headers)


def test_hb_05_write_actions_drift() -> None:
    for name in WRITES:
        a = reg.get(name)
        assert a is not None and a.kind == "write" and a.risk in ("R1", "R2")
        route = _route(a.route)
        guard = _guard_perms(route)
        if guard:
            assert frozenset(a.permission) == guard, name
        assert a.gate == _gate(route), name
        fields = _fields(route)
        for f in a.route_args.values():
            assert f in fields, (name, f, sorted(fields))
        for arg in a.args.model_fields:
            assert arg in a.route_args or arg in a.resolved, (name, arg)


async def test_hb_05_preview_confirm_replay_and_undo(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t = people["teacher"]
    before = await _count(Booking)
    c = await _book_card(env, t)
    schema.validate_card(c)
    assert c["type"] == "confirm" and c["risk"] == "R1" and c["undoable"] is True  # A1: no form step
    assert c["button"]["tr"].startswith("Rezerve et: A 102 · 19.02.2026")
    # nothing is written by the card (RA-06)
    assert await _count(Booking) == before and await _count(HelperActionInvocation) == 0
    # another user's token / a forged token
    other = await _confirm(env, people["approver"], c["token"])
    assert other.status_code == 403 and other.json()["detail"]["code"] == "other_user"
    body, sig = c["token"].split(".")
    forged = await _confirm(env, t, body[:-2] + ("AA" if not body.endswith("AA") else "BB") + "." + sig)
    assert forged.status_code == 403 and forged.json()["detail"]["code"] == "bad_token"
    # the button
    r = await _confirm(env, t, c["token"])
    assert r.status_code == 200, r.text
    res = schema.validate_card(r.json())
    assert res.type == "result" and res.ok and res.undo_token and res.entity.kind == "booking"
    assert len(res.follow_ups) <= 2
    b_id = res.entity.id
    async with dbmod.get_session_factory()() as s:
        b = await s.get(Booking, b_id)
        assert b is not None and b.status == "BOOKED" and b.user_id == t.uid
        ev = (
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "helper.action.create_booking")))
            .scalars()
            .one()
        )
        assert ev.after["via"] == "helper" and ev.actor_id == t.uid
        inv = (await s.execute(select(HelperActionInvocation))).scalars().one()
        assert inv.status == "done" and inv.audit_id == ev.id and inv.entity_id == b_id and inv.undo_event_id
    # a replay or a double click
    again = await _confirm(env, t, c["token"])
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_done"
    assert await _count(Booking) == before + 1
    rejected = await _count(AuditEvent, AuditEvent.action == "helper.confirm_rejected")
    assert rejected == 3  # other user, forged, replay
    # undo before the start
    u = await env.client.post(f"{H}/actions/undo", json={"token": res.undo_token}, headers=t.headers)
    assert u.status_code == 200, u.text
    async with dbmod.get_session_factory()() as s:
        assert (await s.get(Booking, b_id)).status == "CANCELLED"  # type: ignore[union-attr]
    twice = await env.client.post(f"{H}/actions/undo", json={"token": res.undo_token}, headers=t.headers)
    assert twice.status_code == 409
    # an expired confirm token
    old, _ = cf.confirm_token(t.uid, "create_booking", c["args"], "x" * 64, datetime(2026, 1, 1))
    gone = await _confirm(env, t, old)
    assert gone.status_code == 410 and gone.json()["detail"]["code"] == "expired"


async def test_hb_05_slot_taken_between_preview_and_confirm(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t, a = people["teacher"], people["approver"]
    c = await _book_card(env, t)
    taken = await env.book(a.headers, "A102", THU, "P1")
    assert taken.status_code == 201, taken.text
    r = await _confirm(env, t, c["token"])
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "conflict" and d["message_tr"] and "alternatives" in d
    assert await _count(Booking, Booking.user_id == t.uid) == 0


async def test_hb_05_undo_refused_after_the_start(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t = people["teacher"]
    res = (await _confirm(env, t, (await _book_card(env, t))["token"])).json()
    env.set_now(datetime(2026, 2, 19, 9, 0))  # P1 started at 08:30
    u = await env.client.post(f"{H}/actions/undo", json={"token": res["undo_token"]}, headers=t.headers)
    assert u.status_code == 409 and u.json()["detail"]["code"] == "too_old", u.text
    expired = cf.undo_token(t.uid, 1, datetime(2026, 1, 1))
    assert (await env.client.post(f"{H}/actions/undo", json={"token": expired}, headers=t.headers)).status_code == 410


async def test_hb_05_approval_mode_all_makes_a_request_then_withdraw_and_decide(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t, a = people["teacher"], people["approver"]
    r = await env.client.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    assert r.status_code == 200, r.text
    c = await _book_card(env, t)
    assert c["button"]["tr"].startswith("Talep et:") and c["undoable"] is False
    res = (await _confirm(env, t, c["token"])).json()
    assert res["type"] == "result" and "undo_token" not in res and res["entity"]["feature_id"] == "my_requests"
    async with dbmod.get_session_factory()() as s:
        req = (await s.execute(select(ApprovalRequest).where(ApprovalRequest.requested_by == t.uid))).scalars().one()
    # the requester withdraws it (R1, own only); the approver may not
    assert (await card(env, a, "withdraw_my_request", request_id=req.id)).status_code == 404
    w = await card(env, t, "withdraw_my_request", request_id=req.id)
    assert w.json()["type"] == "confirm"
    assert (await _confirm(env, t, w.json()["token"])).status_code == 200
    async with dbmod.get_session_factory()() as s:
        assert (await s.get(ApprovalRequest, req.id)).status == "WITHDRAWN"  # type: ignore[union-attr]
    # a new request, decided by the approver (R2): a rejection without a reason asks for one
    res2 = (await _confirm(env, t, (await _book_card(env, t, period="P2"))["token"])).json()
    req2_id = None
    async with dbmod.get_session_factory()() as s:
        req2_id = (
            await s.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.requested_by == t.uid, ApprovalRequest.status == "PENDING"
                )
            )
        ).scalar_one()
    assert res2["ok"]
    assert (await card(env, t, "decide_approval", request_id=req2_id, decision="approve")).status_code == 403
    form = (await card(env, a, "decide_approval", request_id=req2_id, decision="reject")).json()
    assert form["type"] == "form" and form["missing"] == ["reason_code"]
    ok = (await card(env, a, "decide_approval", request_id=req2_id, decision="approve")).json()
    assert ok["type"] == "confirm" and ok["risk"] == "R2" and ok["affected"]["tr"]
    assert (await _confirm(env, a, ok["token"])).status_code == 200
    async with dbmod.get_session_factory()() as s:
        assert (await s.get(ApprovalRequest, req2_id)).status == "APPROVED"  # type: ignore[union-attr]


async def test_hb_05_cancel_own_only_and_undo_last(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    t, admin = people["teacher"], people["admin"]
    # RA-03: the admin's booking cannot be cancelled by the teacher, whatever they type
    other = await env.book(admin.headers, "A102", THU, "P2")
    assert other.status_code == 201, other.text
    r = await card(env, t, "cancel_my_booking", booking_id=other.json()["id"])
    assert r.status_code in (403, 404) and r.json()["detail"]["card"]["type"] == "refusal"
    # the admin may cancel others' bookings on the page, but the helper cancels only their own
    r = await card(
        env,
        admin,
        "cancel_my_booking",
        booking_id=(await env.book(t.headers, "A201", date(2026, 2, 18), "P3")).json()["id"],
    )
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_cancelable"
    # own cancel, then "Son yaptığımı geri al" re-books it
    mine = await env.book(t.headers, "A102", THU, "P1")
    assert mine.status_code == 201, mine.text
    c = (await card(env, t, "cancel_my_booking", booking_id=mine.json()["id"])).json()
    assert c["type"] == "confirm" and c["danger"] is True and c["button"]["tr"].startswith("İptal et: A 102")
    assert (await _confirm(env, t, c["token"])).status_code == 200
    async with dbmod.get_session_factory()() as s:
        assert (await s.get(Booking, mine.json()["id"])).status == "CANCELLED"  # type: ignore[union-attr]
    u = (await card(env, t, "undo_last_helper_action")).json()
    assert u["type"] == "confirm"
    assert (await _confirm(env, t, u["token"])).status_code == 200, "undo of the cancel"
    async with dbmod.get_session_factory()() as s:
        assert (await s.get(Booking, mine.json()["id"])).status == "BOOKED"  # type: ignore[union-attr]
        rows = (await s.execute(select(HelperActionInvocation).order_by(HelperActionInvocation.id))).scalars().all()
        assert [r.status for r in rows] == ["undone", "done"] and rows[1].undo_of == rows[0].id
    nothing = await card(env, t, "undo_last_helper_action")
    assert nothing.status_code == 404 and nothing.json()["detail"]["code"] == "nothing_to_undo"
    # without a booking id the action shows the person's list to pick from
    assert (await card(env, t, "cancel_my_booking")).json()["type"] == "list"
