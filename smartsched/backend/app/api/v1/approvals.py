"""P1 approval workflows (docs/product/wave1-api.md §4).

* ``/approvals``: the approver inbox, the requester's list, one request, decide (approve / reject / reject with a
  suggested alternative / approve in another room), withdraw, the expiry sweep, the rule check of a room, and
  the designated approvers ("approves for", set when administrator accounts are created).
* ``/approval-rules``: rooms, room groups or room types that require approval (``setup.rooms_acl``).
* ``/me/notifications``: the in-app notification list (bell in the shell).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from app.api.deps import DB, CurrentAccess, require_permission
from app.models import ApprovalRule, ApproverScope, InAppNotification, User
from app.models.base import utcnow
from app.models.catalog import Room
from app.schemas.approvals import (
    ApproverIn,
    ApproverOut,
    DecideIn,
    NotificationOut,
    ReadIn,
    RuleCheckOut,
    RuleIn,
    RuleOut,
)
from app.services import approvals as svc
from app.services import audit
from app.services import bookings as bsvc
from app.services.bookings_perms import load_access, may_manage_user

router = APIRouter(prefix="/approvals", tags=["approvals"])
rules_router = APIRouter(prefix="/approval-rules", tags=["approvals"])
me_router = APIRouter(prefix="/me", tags=["approvals"])
RulesAdmin = Annotated[User, Depends(require_permission("setup.rooms_acl"))]
UsersAdmin = Annotated[User, Depends(require_permission("setup.users"))]


def _err(exc: bsvc.BookingError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


# --- inbox, requests --------------------------------------------------------------------------------


@router.get("/inbox")
async def inbox(db: DB, access: CurrentAccess, status: str = "open") -> list[dict[str, Any]]:
    """Requests whose current step the caller may decide (``open``), or that the caller decided (``decided``)."""
    if status not in ("open", "decided", "all"):
        raise HTTPException(422, "status must be open, decided or all")
    if not access.can(svc.DECIDE):
        return []
    return await svc.inbox(db, access, status)


@router.get("/mine")
async def mine(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    """The caller's own requests with their decisions (timeline)."""
    return await svc.mine(db, access)


@router.post("/sweep", dependencies=[Depends(require_permission(svc.DECIDE, "setup.rooms_acl"))])
async def sweep(db: DB) -> dict[str, int]:
    """Expire overdue requests and release holds that ran out (also done lazily by every approvals call)."""
    return await svc.sweep(db)


@router.get("/rooms/{room_id}/check", response_model=RuleCheckOut)
async def check_room(room_id: int, db: DB, access: CurrentAccess, term_id: int | None = None) -> dict[str, Any]:
    """For the booking sheet: will the caller book (``book``), request (``request``) or neither in this room?"""
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(404, "room not found")
    rules = await svc.RulesIndex.load(db)
    action = await rules.mode_for(db, access, room, term_id)
    rule = rules.rule_for(room, term_id)
    snap = svc.rule_snapshot(rule) if (rule is not None or action == "request") else None
    approvers = await svc.step_approvers(db, room, snap, 1) if snap else []
    if action == "request" and snap:
        lead = snap.get("lead_time_workdays") or 0
        tr = f"{len(snap['steps'])} adımlı onay: atanmış yönetici onaylar" + (
            f" · en az {lead} iş günü önce" if lead else ""
        )
        en = f"{len(snap['steps'])}-step approval by a designated administrator" + (
            f" · at least {lead} working day(s) ahead" if lead else ""
        )
    elif action == "book":
        tr, en = "Doğrudan rezerve edilir", "Booked directly"
    else:
        tr, en = "Bu odada rezervasyon yetkiniz yok", "You may not book this room"
    return {
        "room_id": room.id,
        "action": action,
        "rule": snap,
        "approvers": [{"id": u.id, "name": audit.user_label(u)} for u in approvers],
        "summary_tr": tr,
        "summary_en": en,
    }


# --- approvers ("approves for") ---------------------------------------------------------------------


async def _approver_out(db: DB, u: User) -> dict[str, Any]:
    acc = await load_access(db, u)
    return {
        "user_id": u.id,
        "name": audit.user_label(u),
        "email": u.email,
        "can_decide": acc.can(svc.DECIDE),
        "scopes": [svc.scope_out(s) for s in await svc.scopes_of(db, u.id)],
    }


@router.get("/approvers", response_model=list[ApproverOut])
async def list_approvers(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    if not (access.can("setup.users") or access.can(svc.DECIDE) or access.can("setup.rooms_acl")):
        raise HTTPException(403, "requires permission setup.users or approvals.decide")
    ids = sorted(set((await db.execute(select(ApproverScope.user_id))).scalars()))
    users = [u for u in [await db.get(User, i) for i in ids] if u is not None]
    return [await _approver_out(db, u) for u in users]


@router.put("/approvers/{user_id}", response_model=ApproverOut)
async def set_approver(user_id: int, body: ApproverIn, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """Designate an administrator as approver (``scopes``: every room, room groups, rooms, room types); an
    empty list removes the designation. The caller must hold ``approvals.decide`` and may manage the user."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if not await may_manage_user(db, me, target):
        raise HTTPException(403, {"code": "no_escalation", "message": "you may not manage this account"})
    try:
        await svc.set_scopes(db, me, target, [svc.ScopeIn(s.type, s.id, s.tag) for s in body.scopes])
    except bsvc.BookingError as exc:
        await db.rollback()
        raise _err(exc) from exc
    await db.commit()
    return await _approver_out(db, target)


# --- one request ------------------------------------------------------------------------------------


async def _visible(db: DB, access: Any, request_id: int) -> Any:
    from app.models import ApprovalRequest

    req = await db.get(ApprovalRequest, request_id)
    if req is None:
        raise HTTPException(404, "request not found")
    if req.requested_by == access.user_id:
        return req
    room = await db.get(Room, req.room_id)
    if room is not None and access.can(svc.DECIDE):
        decided = req.status != "PENDING"
        if decided or access.user in await svc.step_approvers(db, room, req.rule_snapshot or {}, req.step):
            return req
    raise HTTPException(404, "request not found")


@router.get("/{request_id}")
async def get_request(request_id: int, db: DB, access: CurrentAccess) -> dict[str, Any]:
    req = await _visible(db, access, request_id)
    return await svc.request_out(db, access, req, detail=True)


@router.post("/{request_id}/decide")
async def decide(request_id: int, body: DecideIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    alt = None
    if body.alternative is not None:
        a = body.alternative
        alt = svc.Alternative(a.room_id, a.date, a.period_id, a.start_period, a.end_period)
    try:
        return await svc.decide(db, access, request_id, body.decision, body.note, alt, body.instances)
    except bsvc.BookingError as exc:
        await db.rollback()
        raise _err(exc) from exc


@router.post("/{request_id}/withdraw")
async def withdraw(request_id: int, db: DB, access: CurrentAccess) -> dict[str, Any]:
    try:
        req = await svc.withdraw(db, access, request_id)
    except bsvc.BookingError as exc:
        await db.rollback()
        raise _err(exc) from exc
    return await svc.request_out(db, access, req, detail=True)


# --- rules ------------------------------------------------------------------------------------------


async def _rule(db: DB, rule_id: int) -> ApprovalRule:
    r = await db.get(ApprovalRule, rule_id)
    if r is None:
        raise HTTPException(404, "rule not found")
    return r


@rules_router.get("", response_model=list[RuleOut])
async def list_rules(db: DB, _: RulesAdmin) -> list[dict[str, Any]]:
    rows = (await db.execute(select(ApprovalRule).order_by(ApprovalRule.id))).scalars()
    return [svc.rule_out(r) for r in rows]


@rules_router.post("", response_model=RuleOut, status_code=201)
async def create_rule(body: RuleIn, db: DB, me: RulesAdmin) -> dict[str, Any]:
    try:
        data = await svc.validate_rule(db, body.model_dump(mode="json"))
    except bsvc.BookingError as exc:
        raise _err(exc) from exc
    r = ApprovalRule(**data, created_by=me.id)
    db.add(r)
    await db.flush()
    await audit.record(db, "approval_rule.create", "approval_rule", r.id, after=svc.rule_out(r), actor=me)
    await db.commit()
    await db.refresh(r)
    return svc.rule_out(r)


@rules_router.put("/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: int, body: RuleIn, db: DB, me: RulesAdmin) -> dict[str, Any]:
    """Open requests keep the snapshot of the rule they were made under."""
    r = await _rule(db, rule_id)
    before = svc.rule_out(r)
    try:
        data = await svc.validate_rule(db, body.model_dump(mode="json"))
    except bsvc.BookingError as exc:
        raise _err(exc) from exc
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_at = utcnow()
    await db.flush()
    await audit.record(
        db, "approval_rule.update", "approval_rule", r.id, before=before, after=svc.rule_out(r), actor=me
    )
    await db.commit()
    await db.refresh(r)
    return svc.rule_out(r)


@rules_router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, db: DB, me: RulesAdmin) -> None:
    r = await _rule(db, rule_id)
    before = svc.rule_out(r)
    await db.delete(r)
    await audit.record(db, "approval_rule.delete", "approval_rule", rule_id, before=before, actor=me)
    await db.commit()


# --- in-app notifications ---------------------------------------------------------------------------


def _note_out(x: InAppNotification) -> dict[str, Any]:
    return {
        "id": x.id,
        "kind": x.kind,
        "title": x.title,
        "body": x.body,
        "link": x.link,
        "booking_id": x.booking_id,
        "request_id": x.request_id,
        "read_at": x.read_at.isoformat() if x.read_at else None,
        "created_at": x.created_at.isoformat() if x.created_at else None,
    }


@me_router.get("/notifications", response_model=list[NotificationOut])
async def notifications(db: DB, access: CurrentAccess, unread: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    q = select(InAppNotification).where(InAppNotification.user_id == access.user_id)
    if unread:
        q = q.where(InAppNotification.read_at.is_(None))
    q = q.order_by(InAppNotification.id.desc()).limit(max(1, min(limit, 200)))
    return [_note_out(x) for x in (await db.execute(q)).scalars()]


@me_router.post("/notifications/read")
async def mark_read(body: ReadIn, db: DB, access: CurrentAccess) -> dict[str, int]:
    q = update(InAppNotification).where(
        InAppNotification.user_id == access.user_id, InAppNotification.read_at.is_(None)
    )
    if not body.all:
        if not body.ids:
            return {"read": 0}
        q = q.where(InAppNotification.id.in_(body.ids))
    res = await db.execute(q.values(read_at=utcnow()))
    await db.commit()
    return {"read": int(res.rowcount or 0)}  # type: ignore[attr-defined]
