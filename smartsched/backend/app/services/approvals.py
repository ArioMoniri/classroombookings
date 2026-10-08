"""P1 approval workflows (docs/product/booking-enhancements.md §4.3; user decisions 2026-10-08).

* No room needs approval by default: without an ``approval_rules`` row a booking is exactly the CRBS booking.
* A rule on a room, a room group or a room type (solver tag such as TIP or PC) turns a booking there into a
  ``PENDING`` request (HTTP 202). The requester needs ``book_*.create`` or ``book_*.request`` on the room (role or
  room ACL). ``book_*.request`` alone also works on rooms without a rule when a designated approver covers them.
* Approvers are administrators designated when their account is created (``approver_scopes``: every room, room
  groups, rooms or room types) who hold ``approvals.decide``. A rule has one or more steps; a step lists
  "designated approvers of the room" (default) or named designated approvers and how many approvals it needs.
  When nobody is eligible the request falls back to the approvers designated for every room, then to the room
  owner (if they hold ``approvals.decide``), then to Administrators: a request is never orphaned.
* A request holds its slot only when the rule says so (``hold_minutes`` > 0; slots in ``booking_slots`` until
  ``held_until``); otherwise competing requests may coexist and approving one rejects the others with a reason.
* Approving re-validates everything in one transaction (holiday added since, the timetable, other bookings; the
  unique slot key is the referee): a lost race answers 409 with free alternatives (T1).
* A request expires ``expires_before_start_minutes`` before the booking starts (default: at the start).
* The requester and the approvers are notified by e-mail (``notification_outbox``) and in-app
  (``inapp_notifications``); every transition is audited (P7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRule,
    ApproverScope,
    Booking,
    BookingPeriod,
    BookingSeries,
    BookingSlot,
    InAppNotification,
    RoomGroup,
    User,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, EXPIRED, PENDING, REJECTED, WITHDRAWN
from app.models.catalog import Room
from app.services import audit
from app.services import bookings as bsvc
from app.services import bookings_notify as mail
from app.services.bookings_calendar import CalendarError, date_infos, holidays_by_date, term_info
from app.services.bookings_perms import Access, load_access
from app.services.events import publish_event

DECIDE = "approvals.decide"
APPROVED = "APPROVED"
DEFAULT_STEPS: list[dict[str, Any]] = [{"approvers": {"type": "designated"}, "min_approvals": 1}]
SCOPE_TYPES = ("all", "room", "room_group", "tag")


class ApprovalError(bsvc.BookingError):
    pass


def _err(status: int, code: str, message: str, message_tr: str, **data: Any) -> ApprovalError:
    return ApprovalError(status, code, message, message_tr=message_tr, **data)


# --------------------------------------------------------------------------------------------------
# Approver designation ("approves for", set when an administrator account is created)
# --------------------------------------------------------------------------------------------------


@dataclass
class ScopeIn:
    type: str
    id: int | None = None
    tag: str | None = None


def scope_covers(s: ApproverScope, room: Room) -> bool:
    if s.scope_type == "all":
        return True
    if s.scope_type == "room":
        return s.scope_id == room.id
    if s.scope_type == "room_group":
        return room.room_group_id is not None and s.scope_id == room.room_group_id
    if s.scope_type == "tag":
        return bool(s.tag) and s.tag in (room.tags or [])
    return False


def scope_out(s: ApproverScope) -> dict[str, Any]:
    return {"type": s.scope_type, "id": s.scope_id, "tag": s.tag}


async def scopes_of(session: AsyncSession, user_id: int) -> list[ApproverScope]:
    q = select(ApproverScope).where(ApproverScope.user_id == user_id).order_by(ApproverScope.id)
    return list((await session.execute(q)).scalars())


async def set_scopes(session: AsyncSession, actor: User, target: User, scopes: list[ScopeIn]) -> list[ApproverScope]:
    """Designate ``target`` as an approver (empty list: remove the designation). No escalation: the actor must be
    an approver (``approvals.decide``) and the target an administrator holding ``approvals.decide``."""
    acc = await load_access(session, actor)
    if not acc.can(DECIDE):
        raise _err(
            403,
            "no_escalation",
            "only users who hold approvals.decide can designate approvers",
            "onaycı atamak için approvals.decide yetkisi gerekir",
        )
    if scopes:
        tacc = await load_access(session, target)
        if not tacc.can(DECIDE):
            raise _err(
                422,
                "not_an_administrator",
                "approvers must be administrators holding approvals.decide",
                "onaycı, approvals.decide yetkisi olan bir yönetici olmalı",
            )
    rows: list[ApproverScope] = []
    seen: set[tuple[str, int | None, str | None]] = set()
    for s in scopes:
        stype = (s.type or "").strip().lower()
        if stype not in SCOPE_TYPES:
            raise _err(422, "scope_type", f"scope type must be one of {', '.join(SCOPE_TYPES)}", "geçersiz kapsam")
        sid, tag = None, None
        if stype == "room":
            if s.id is None or await session.get(Room, s.id) is None:
                raise _err(422, "scope_room", f"room {s.id} not found", f"{s.id} numaralı oda yok")
            sid = s.id
        elif stype == "room_group":
            if s.id is None or await session.get(RoomGroup, s.id) is None:
                raise _err(422, "scope_group", f"room group {s.id} not found", f"{s.id} numaralı oda grubu yok")
            sid = s.id
        elif stype == "tag":
            from app.services.rooms_features import norm_tag

            tag = norm_tag(s.tag)
            if not tag:
                raise _err(422, "scope_tag", "a room type (tag) is needed", "oda türü (etiket) gerekli")
        key = (stype, sid, tag)
        if key in seen:
            continue
        seen.add(key)
        rows.append(ApproverScope(user_id=target.id, scope_type=stype, scope_id=sid, tag=tag, created_by=actor.id))
    before = [scope_out(x) for x in await scopes_of(session, target.id)]
    await session.execute(delete(ApproverScope).where(ApproverScope.user_id == target.id))
    for r in rows:
        session.add(r)
    await session.flush()
    after = [scope_out(x) for x in rows]
    if before != after:
        await audit.record(
            session,
            "approver.update",
            "user",
            target.id,
            before={"approves_for": before},
            after={"approves_for": after},
            actor=actor,
        )
    return rows


async def _decider(session: AsyncSession, user: User | None) -> bool:
    if user is None or not user.is_active:
        return False
    return (await load_access(session, user)).can(DECIDE)


async def designated_for(session: AsyncSession, room: Room) -> list[User]:
    """Active users holding ``approvals.decide`` whose designation covers ``room``."""
    out: dict[int, User] = {}
    for s in (await session.execute(select(ApproverScope).order_by(ApproverScope.user_id))).scalars():
        if s.user_id in out or not scope_covers(s, room):
            continue
        u = await session.get(User, s.user_id)
        if await _decider(session, u):
            assert u is not None
            out[u.id] = u
    return list(out.values())


async def _fallback(session: AsyncSession, room: Room) -> list[User]:
    everyone: list[User] = []
    for s in (await session.execute(select(ApproverScope).where(ApproverScope.scope_type == "all"))).scalars():
        u = await session.get(User, s.user_id)
        if u is not None and await _decider(session, u) and u not in everyone:
            everyone.append(u)
    if everyone:
        return everyone
    if room.owner_user_id:
        owner = await session.get(User, room.owner_user_id)
        if await _decider(session, owner):
            assert owner is not None
            return [owner]
    admins = (await session.execute(select(User).where(User.role == "ADMIN", User.is_active.is_(True)))).scalars()
    return [u for u in admins if await _decider(session, u)]


async def step_approvers(session: AsyncSession, room: Room, snapshot: dict[str, Any], step: int) -> list[User]:
    steps = snapshot.get("steps") or DEFAULT_STEPS
    spec = steps[min(step, len(steps)) - 1].get("approvers") or {"type": "designated"}
    designated = await designated_for(session, room)
    if spec.get("type") == "users":
        ids = [int(i) for i in spec.get("ids") or []]
        users = [u for u in [await session.get(User, i) for i in ids] if u is not None]
        chosen = [u for u in users if await _decider(session, u)]
    else:
        chosen = designated
    return sorted(chosen or await _fallback(session, room), key=lambda u: u.id)


# --------------------------------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------------------------------


def rule_snapshot(rule: ApprovalRule | None) -> dict[str, Any]:
    if rule is None:
        return {
            "rule_id": None,
            "name": None,
            "steps": DEFAULT_STEPS,
            "hold_minutes": 0,
            "lead_time_workdays": 0,
            "expires_before_start_minutes": 0,
            "allow_self_approve": False,
        }
    return {
        "rule_id": rule.id,
        "name": rule.name,
        "entity_type": rule.entity_type,
        "entity_id": rule.entity_id,
        "tag": rule.tag,
        "steps": rule.steps or DEFAULT_STEPS,
        "hold_minutes": rule.hold_minutes or 0,
        "lead_time_workdays": rule.lead_time_workdays or 0,
        "expires_before_start_minutes": rule.expires_before_start_minutes or 0,
        "allow_self_approve": bool(rule.allow_self_approve),
    }


def rule_out(rule: ApprovalRule) -> dict[str, Any]:
    return {
        **rule_snapshot(rule),
        "id": rule.id,
        "term_id": rule.term_id,
        "active": bool(rule.active),
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


class RulesIndex:
    """The active rules, loaded once per request; the most specific rule wins (room > room group > room type),
    a rule of the booking's term before a rule of every term."""

    def __init__(self, rules: list[ApprovalRule]) -> None:
        self.rules = rules
        self._approvers: dict[int, bool] = {}

    @classmethod
    async def load(cls, session: AsyncSession) -> RulesIndex:
        q = select(ApprovalRule).where(ApprovalRule.active.is_(True)).order_by(ApprovalRule.id)
        return cls(list((await session.execute(q)).scalars()))

    def rule_for(self, room: Room, term_id: int | None) -> ApprovalRule | None:
        def applies(r: ApprovalRule) -> int | None:
            if r.term_id is not None and r.term_id != term_id:
                return None
            if r.entity_type == "room" and r.entity_id == room.id:
                rank = 0
            elif r.entity_type == "room_group" and room.room_group_id is not None and r.entity_id == room.room_group_id:
                rank = 2
            elif r.entity_type == "tag" and r.tag and r.tag in (room.tags or []):
                rank = 4
            else:
                return None
            return rank + (0 if r.term_id is not None else 1)

        ranked = [(rk, r.id, r) for r in self.rules if (rk := applies(r)) is not None]
        return min(ranked, key=lambda x: (x[0], x[1]))[2] if ranked else None

    async def mode_for(self, session: AsyncSession, access: Access, room: Room, term_id: int | None) -> str:
        """``book`` | ``request`` | ``none`` for single bookings by ``access`` in ``room`` (the finder's action)."""
        create = access.can("book_single.create", room)
        request = access.can("book_single.request", room)
        rule = self.rule_for(room, term_id)
        if rule is None:
            if create:
                return "book"
            if request:
                if room.id not in self._approvers:
                    self._approvers[room.id] = bool(await designated_for(session, room))
                return "request" if self._approvers[room.id] else "none"
            return "none"
        if not (create or request):
            return "none"
        if await _exempt(session, access, room, rule_snapshot(rule)):
            return "book"
        return "request"


async def _exempt(session: AsyncSession, access: Access, room: Room, snap: dict[str, Any]) -> bool:
    """A designated approver of every step books directly when the rule allows self-approval."""
    if not snap.get("allow_self_approve"):
        return False
    for i in range(1, len(snap.get("steps") or DEFAULT_STEPS) + 1):
        if access.user not in await step_approvers(session, room, snap, i):
            return False
    return True


async def validate_rule(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    from app.services.rooms_features import norm_tag

    et = data.get("entity_type")
    if et == "room":
        if data.get("entity_id") is None or await session.get(Room, data["entity_id"]) is None:
            raise _err(422, "entity", f"room {data.get('entity_id')} not found", "oda bulunamadı")
        data["tag"] = None
    elif et == "room_group":
        if data.get("entity_id") is None or await session.get(RoomGroup, data["entity_id"]) is None:
            raise _err(422, "entity", f"room group {data.get('entity_id')} not found", "oda grubu bulunamadı")
        data["tag"] = None
    elif et == "tag":
        data["tag"] = norm_tag(data.get("tag"))
        data["entity_id"] = None
        if not data["tag"]:
            raise _err(422, "entity", "a room type (tag) is needed, e.g. TIP or PC", "oda türü gerekli (TIP, PC ...)")
    else:
        raise _err(422, "entity", "entity_type must be room, room_group or tag", "geçersiz kural hedefi")
    steps = data.get("steps") or DEFAULT_STEPS
    if not 1 <= len(steps) <= 5:
        raise _err(422, "steps", "a rule has 1 to 5 steps", "bir kural 1-5 adımdan oluşur")
    clean_steps = []
    for st in steps:
        appr = dict(st.get("approvers") or {"type": "designated"})
        kind = appr.get("type", "designated")
        if kind == "users":
            ids = [int(i) for i in appr.get("ids") or []]
            if not ids:
                raise _err(422, "steps", "a 'users' step lists approver ids", "adımda onaycı seçilmeli")
            for uid in ids:
                u = await session.get(User, uid)
                if u is None or not await _decider(session, u) or not await scopes_of(session, uid):
                    raise _err(
                        422,
                        "approver",
                        f"user {uid} is not a designated approver (administrator with approvals.decide)",
                        f"{uid} numaralı kullanıcı atanmış bir onaycı değil",
                    )
            appr = {"type": "users", "ids": ids}
        elif kind != "designated":
            raise _err(422, "steps", "approvers type must be designated or users", "geçersiz onaycı türü")
        else:
            appr = {"type": "designated"}
        mins = int(st.get("min_approvals") or 1)
        if mins < 1:
            raise _err(422, "steps", "min_approvals is at least 1", "en az bir onay gerekir")
        clean_steps.append({"approvers": appr, "min_approvals": mins})
    data["steps"] = clean_steps
    return data


# --------------------------------------------------------------------------------------------------
# Creating requests (called by app.services.bookings when a booking needs approval)
# --------------------------------------------------------------------------------------------------


@dataclass
class Need:
    rule: ApprovalRule | None
    snapshot: dict[str, Any]


async def need_for(session: AsyncSession, access: Access, room: Room, kind: str, term_id: int | None) -> Need | None:
    """``None`` = book directly (CRBS); a :class:`Need` = create a PENDING request; 403 = neither allowed."""
    create = access.can(f"{kind}.create", room)
    request = access.can(f"{kind}.request", room)
    rules = await RulesIndex.load(session)
    rule = rules.rule_for(room, term_id)
    word = "single" if kind == "book_single" else "recurring"
    if rule is None:
        if create:
            return None
        if request:
            if await designated_for(session, room):
                return Need(None, rule_snapshot(None))
            raise _err(
                403,
                "no_approver",
                f"nobody is designated to approve requests for {room.display_name}",
                f"{room.display_name} için atanmış onaycı yok",
            )
        raise bsvc.BookingError(403, f"{kind}.create", f"you may not make {word} bookings in {room.display_name}")
    if not (create or request):
        raise bsvc.BookingError(403, f"{kind}.create", f"you may not make {word} bookings in {room.display_name}")
    snap = rule_snapshot(rule)
    if await _exempt(session, access, room, snap):
        return None
    return Need(rule, snap)


async def add_workdays(session: AsyncSession, term_id: int, start: date, days: int) -> date:
    from app.models import Term

    term = await session.get(Term, term_id)
    info = await term_info(session, term) if term else None
    closed = await holidays_by_date(session, info) if info else {}
    d, left = start, days
    while left > 0:
        d += timedelta(days=1)
        if d.isoweekday() <= 5 and d not in closed:
            left -= 1
    return d


async def check_lead_time(session: AsyncSession, need: Need, term_id: int, d: date) -> None:
    lead = int(need.snapshot.get("lead_time_workdays") or 0)
    if lead <= 0:
        return
    earliest = await add_workdays(session, term_id, await bsvc.today(session), lead)
    if d < earliest:
        raise _err(
            409,
            "lead_time",
            f"requests for this room are made at least {lead} working day(s) ahead (from {earliest:%d.%m.%Y})",
            f"bu oda için talep en az {lead} iş günü önceden yapılır ({earliest:%d.%m.%Y} ve sonrası)",
            earliest=earliest.isoformat(),
        )


async def _start_of(session: AsyncSession, b: Booking) -> datetime:
    period = await session.get(BookingPeriod, b.period_id)
    return datetime.combine(b.date, period.time_start) if period else datetime.combine(b.date, datetime.min.time())


async def hold_until(session: AsyncSession, need: Need, first: Booking) -> datetime | None:
    minutes = int(need.snapshot.get("hold_minutes") or 0)
    if minutes <= 0:
        return None
    now = await bsvc.now_local(session)
    return min(now + timedelta(minutes=minutes), await _start_of(session, first))


async def open_request(
    session: AsyncSession,
    access: Access,
    need: Need,
    room: Room,
    bookings: list[Booking],
    series: BookingSeries | None = None,
) -> ApprovalRequest:
    first = min(bookings, key=lambda b: (b.date, b.start_period))
    expires = await _start_of(session, first) - timedelta(
        minutes=int(need.snapshot.get("expires_before_start_minutes") or 0)
    )
    req = ApprovalRequest(
        booking_id=first.id if series is None else None,
        series_id=series.id if series is not None else None,
        room_id=room.id,
        term_id=first.term_id,
        rule_id=need.rule.id if need.rule else None,
        rule_snapshot=need.snapshot,
        step=1,
        status=PENDING,
        requested_by=access.user_id,
        expires_at=expires,
    )
    session.add(req)
    await session.flush()
    await publish_event(
        session,
        "approval.request",
        "approval_request",
        req.id,
        after={
            "booking_ids": [b.id for b in bookings],
            "series_id": req.series_id,
            "room": room.display_name,
            "rule_id": req.rule_id,
            "held_until": first.held_until,
            "expires_at": expires,
        },
        actor=access.user,
        term_id=first.term_id,
    )
    await _notify_approvers(session, req, room, first, access.user)
    return req


# --------------------------------------------------------------------------------------------------
# Notifications (e-mail outbox + in-app)
# --------------------------------------------------------------------------------------------------


async def _describe(session: AsyncSession, b: Booking, room: Room) -> str:
    period = await session.get(BookingPeriod, b.period_id)
    times = f"{period.time_start:%H:%M}-{period.time_end:%H:%M}" if period else f"P{b.start_period}-P{b.end_period}"
    return f"{room.display_name}, {b.date:%d.%m.%Y} {period.name if period else ''} {times}".replace("  ", " ")


TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    # kind -> language -> (title, body); placeholders: who, what, note, alt
    "approval.requested": {
        "tr": ("Onay bekleyen oda talebi: {what}", "{who} şu oda için onay istiyor: {what}.{note}"),
        "en": ("Room request awaiting approval: {what}", "{who} asks for approval: {what}.{note}"),
    },
    "approval.approved": {
        "tr": ("Oda talebiniz onaylandı: {what}", "{who} talebinizi onayladı: {what}.{note}"),
        "en": ("Your room request was approved: {what}", "{who} approved your request: {what}.{note}"),
    },
    "approval.rejected": {
        "tr": ("Oda talebiniz reddedildi: {what}", "{who} talebinizi reddetti: {what}.{note}{alt}"),
        "en": ("Your room request was declined: {what}", "{who} declined your request: {what}.{note}{alt}"),
    },
    "approval.expired": {
        "tr": ("Oda talebinizin süresi doldu: {what}", "Talebiniz başlangıçtan önce onaylanmadı: {what}.{note}"),
        "en": ("Your room request expired: {what}", "Your request was not approved before it started: {what}.{note}"),
    },
}


async def _send(
    session: AsyncSession, user: User, kind: str, link: str, b: Booking | None, req: ApprovalRequest, **fmt: str
) -> None:
    lang = await mail._language(session, user)
    title_t, body_t = TEXTS[kind]["tr" if lang == "tr" else "en"]
    title, body = title_t.format(**fmt), body_t.format(**fmt)
    session.add(
        InAppNotification(
            user_id=user.id,
            kind=kind,
            title=title[:255],
            body=body,
            link=link,
            booking_id=b.id if b else None,
            request_id=req.id,
        )
    )
    await mail.notify(
        session,
        kind=kind.replace(".", "_")[:32],
        to_email=user.email,
        subject=title,
        body=body,
        user_id=user.id,
        booking_id=b.id if b else None,
    )


async def _notify_approvers(
    session: AsyncSession, req: ApprovalRequest, room: Room, b: Booking, requester: User
) -> None:
    what = await _describe(session, b, room)
    for u in await step_approvers(session, room, req.rule_snapshot or {}, req.step):
        if u.id == requester.id:
            continue
        await _send(
            session,
            u,
            "approval.requested",
            f"/approvals?request={req.id}",
            b,
            req,
            who=audit.user_label(requester) or "-",
            what=what,
            note="",
            alt="",
        )


async def _notify_requester(
    session: AsyncSession, req: ApprovalRequest, kind: str, actor: User | None, alt: str = ""
) -> None:
    if not req.requested_by:
        return
    user = await session.get(User, req.requested_by)
    if user is None:
        return
    b = await _first_booking(session, req)
    room = await session.get(Room, req.room_id)
    if b is None or room is None:
        return
    lang = await mail._language(session, user)
    note = f" {'Not' if lang == 'tr' else 'Note'}: {req.note}" if req.note else ""
    await _send(
        session,
        user,
        kind,
        f"/bookings/mine?request={req.id}",
        b,
        req,
        who=audit.user_label(actor) or "SmartSched",
        what=await _describe(session, b, room),
        note=note,
        alt=alt,
    )


# --------------------------------------------------------------------------------------------------
# Reading requests
# --------------------------------------------------------------------------------------------------


async def bookings_of(session: AsyncSession, req: ApprovalRequest) -> list[Booking]:
    if req.series_id is not None:
        q = select(Booking).where(Booking.series_id == req.series_id).order_by(Booking.date, Booking.start_period)
        return list((await session.execute(q)).scalars())
    b = await session.get(Booking, req.booking_id) if req.booking_id else None
    return [b] if b is not None else []


async def _first_booking(session: AsyncSession, req: ApprovalRequest) -> Booking | None:
    rows = await bookings_of(session, req)
    return rows[0] if rows else None


async def request_out(
    session: AsyncSession, access: Access, req: ApprovalRequest, *, detail: bool = False
) -> dict[str, Any]:
    room = await session.get(Room, req.room_id)
    requester = await session.get(User, req.requested_by) if req.requested_by else None
    rows = await bookings_of(session, req)
    out: dict[str, Any] = {
        "id": req.id,
        "status": req.status,
        "step": req.step,
        "steps": len((req.rule_snapshot or {}).get("steps") or DEFAULT_STEPS),
        "rule": req.rule_snapshot,
        "room_id": req.room_id,
        "room_name": room.display_name if room else None,
        "term_id": req.term_id,
        "series_id": req.series_id,
        "booking_id": req.booking_id,
        "requested_by": req.requested_by,
        "requester_name": audit.user_label(requester),
        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "note": req.note,
        "suggestion": req.suggestion,
        "bookings": [await bsvc.booking_out(session, access, b) for b in rows],
    }
    if detail:
        decisions = (
            await session.execute(
                select(ApprovalDecision).where(ApprovalDecision.request_id == req.id).order_by(ApprovalDecision.id)
            )
        ).scalars()
        out["decisions"] = [
            {
                "step": d.step,
                "approver_user_id": d.approver_user_id,
                "approver_name": audit.user_label(await session.get(User, d.approver_user_id))
                if d.approver_user_id
                else None,
                "decision": d.decision,
                "note": d.note,
                "alternative": d.alternative,
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            }
            for d in decisions
        ]
        if room is not None:
            out["approvers"] = [
                {"id": u.id, "name": audit.user_label(u)}
                for u in await step_approvers(session, room, req.rule_snapshot or {}, req.step)
            ]
            out["competing"] = [c.id for c in await competing(session, req)]
    return out


async def competing(session: AsyncSession, req: ApprovalRequest) -> list[ApprovalRequest]:
    """Other PENDING requests for the same room on an overlapping date and period."""
    mine = await bookings_of(session, req)
    keys = {(b.room_id, b.date): (b.start_period, b.end_period) for b in mine}
    if not keys:
        return []
    q = select(Booking).where(
        Booking.status == PENDING,
        Booking.room_id.in_({k[0] for k in keys}),
        Booking.date.in_({k[1] for k in keys}),
        Booking.id.notin_([b.id for b in mine]),
    )
    out: dict[int, ApprovalRequest] = {}
    for b in (await session.execute(q)).scalars():
        s, e = keys[(b.room_id, b.date)]
        if not (b.start_period <= e and s <= b.end_period):
            continue
        other = await request_for_booking(session, b)
        if other is not None and other.status == PENDING and other.id != req.id:
            out[other.id] = other
    return sorted(out.values(), key=lambda r: r.id)


async def request_for_booking(session: AsyncSession, b: Booking) -> ApprovalRequest | None:
    if b.series_id is not None:
        q = select(ApprovalRequest).where(ApprovalRequest.series_id == b.series_id)
    else:
        q = select(ApprovalRequest).where(ApprovalRequest.booking_id == b.id)
    return (await session.execute(q.order_by(ApprovalRequest.id.desc()))).scalars().first()


async def inbox(session: AsyncSession, access: Access, status: str = "open") -> list[dict[str, Any]]:
    await sweep(session)
    q = select(ApprovalRequest).order_by(ApprovalRequest.requested_at, ApprovalRequest.id)
    if status == "open":
        q = q.where(ApprovalRequest.status == PENDING)
    elif status == "decided":
        q = q.where(ApprovalRequest.status != PENDING)
    out = []
    for req in (await session.execute(q)).scalars():
        room = await session.get(Room, req.room_id)
        if room is None:
            continue
        if req.status == PENDING:
            if access.user not in await step_approvers(session, room, req.rule_snapshot or {}, req.step):
                continue
        else:
            decided = (
                await session.execute(
                    select(ApprovalDecision.id).where(
                        ApprovalDecision.request_id == req.id, ApprovalDecision.approver_user_id == access.user_id
                    )
                )
            ).first()
            if decided is None:
                continue
        out.append(await request_out(session, access, req, detail=True))
    return out


async def mine(session: AsyncSession, access: Access) -> list[dict[str, Any]]:
    await sweep(session)
    q = (
        select(ApprovalRequest)
        .where(ApprovalRequest.requested_by == access.user_id)
        .order_by(ApprovalRequest.requested_at.desc(), ApprovalRequest.id.desc())
    )
    return [await request_out(session, access, r, detail=True) for r in (await session.execute(q)).scalars()]


# --------------------------------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------------------------------


async def _close(
    session: AsyncSession,
    req: ApprovalRequest,
    rows: list[Booking],
    status: str,
    reason: str | None,
    actor: User | None,
) -> None:
    now = utcnow()
    ids = [b.id for b in rows if b.status == PENDING]
    if ids:
        await session.execute(delete(BookingSlot).where(BookingSlot.booking_id.in_(ids)))
    for b in rows:
        if b.status == PENDING:
            b.status, b.held_until = status, None
            b.cancel_reason, b.cancelled_at = reason, now
            b.cancelled_by = actor.id if actor else None
    if req.series_id is not None:
        series = await session.get(BookingSeries, req.series_id)
        if series is not None and series.status == PENDING:
            series.status = status
    req.status, req.decided_at = status, now
    await session.flush()


async def _load(session: AsyncSession, request_id: int) -> tuple[ApprovalRequest, Room]:
    req = await session.get(ApprovalRequest, request_id)
    if req is None:
        raise _err(404, "not_found", "request not found", "talep bulunamadı")
    room = await session.get(Room, req.room_id)
    assert room is not None
    return req, room


async def sweep(session: AsyncSession) -> dict[str, int]:
    """Expire requests whose time has come and release holds that ran out (idempotent; called by the inbox, the
    requester's list, decisions and ``POST /approvals/sweep``)."""
    now = await bsvc.now_local(session)
    expired = 0
    q = select(ApprovalRequest).where(ApprovalRequest.status == PENDING, ApprovalRequest.expires_at <= now)
    for req in list((await session.execute(q)).scalars()):
        rows = await bookings_of(session, req)
        req.note = req.note or "Başlangıçtan önce onaylanmadı / not approved before the start"
        await _close(session, req, rows, EXPIRED, "approval expired", None)
        await publish_event(session, "approval.expire", "approval_request", req.id, after={"status": EXPIRED})
        await _notify_requester(session, req, "approval.expired", None)
        expired += 1
    released = await bsvc.release_expired_holds(session)
    if expired or released:
        await session.commit()
    return {"expired": expired, "released": released}


async def withdraw(session: AsyncSession, access: Access, request_id: int) -> ApprovalRequest:
    req, _room = await _load(session, request_id)
    if req.requested_by != access.user_id:
        raise _err(
            403, "not_requester", "only the requester can withdraw a request", "talebi yalnız sahibi geri çekebilir"
        )
    if req.status != PENDING:
        raise _err(409, "not_pending", f"the request is {req.status}", f"talep {req.status} durumunda")
    await _close(session, req, await bookings_of(session, req), WITHDRAWN, "withdrawn by the requester", access.user)
    await publish_event(
        session, "approval.withdraw", "approval_request", req.id, after={"status": WITHDRAWN}, actor=access.user
    )
    await session.commit()
    return req


@dataclass
class Alternative:
    room_id: int | None = None
    date: date | None = None
    period_id: int | None = None
    start_period: int | None = None
    end_period: int | None = None


async def _alternative_out(session: AsyncSession, alt: Alternative, b: Booking) -> dict[str, Any]:
    room = await session.get(Room, alt.room_id) if alt.room_id else await session.get(Room, b.room_id)
    if room is None:
        raise _err(422, "alternative", f"room {alt.room_id} not found", "önerilen oda bulunamadı")
    period = await session.get(BookingPeriod, alt.period_id) if alt.period_id else None
    if alt.period_id and period is None:
        raise _err(422, "alternative", f"period {alt.period_id} not found", "önerilen ders saati bulunamadı")
    d = alt.date or b.date
    return {
        "room_id": room.id,
        "room_name": room.display_name,
        "date": d.isoformat(),
        "period_id": period.id if period else (b.period_id if not alt.start_period else None),
        "start_period": period.start_period if period else (alt.start_period or b.start_period),
        "end_period": period.end_period if period else (alt.end_period or alt.start_period or b.end_period),
    }


async def decide(
    session: AsyncSession,
    access: Access,
    request_id: int,
    decision: str,
    note: str | None = None,
    alternative: Alternative | None = None,
    instances: list[date] | None = None,
) -> dict[str, Any]:
    """``approve`` (optionally in another room = ``alternative``), ``reject`` (optionally suggesting
    ``alternative``). Approval of the last step books the slot after re-checking it."""
    await sweep(session)
    req, room = await _load(session, request_id)
    if req.status != PENDING:
        raise _err(409, "not_pending", f"the request is already {req.status}", f"talep zaten {req.status}")
    if not access.can(DECIDE):
        raise _err(403, DECIDE, "you may not decide on requests", "talepler hakkında karar veremezsiniz")
    snap = req.rule_snapshot or rule_snapshot(None)
    approvers = await step_approvers(session, room, snap, req.step)
    if access.user not in approvers:
        raise _err(
            403,
            "not_an_approver",
            "you are not an approver of this step",
            "bu adımın onaycısı değilsiniz",
            approvers=[audit.user_label(u) for u in approvers],
        )
    self_req = req.requested_by == access.user_id
    others = [u for u in approvers if u.id != access.user_id]
    if self_req and decision == "approve" and not snap.get("allow_self_approve") and others:
        raise _err(
            403,
            "self_approval",
            "you cannot approve your own request",
            "kendi talebinizi onaylayamazsınız",
        )
    note = n.clean_text(note) if note else None
    rows = await bookings_of(session, req)
    if not rows:
        raise _err(409, "no_bookings", "the request has no bookings any more", "talebin rezervasyonu kalmadı")
    alt_out = await _alternative_out(session, alternative, rows[0]) if alternative is not None else None
    session.add(
        ApprovalDecision(
            request_id=req.id,
            step=req.step,
            approver_user_id=access.user_id,
            decision=APPROVED if decision == "approve" else REJECTED,
            note=note,
            alternative=alt_out,
        )
    )
    req.note = note
    if decision == "reject":
        suggestion = alt_out
        requester = await session.get(User, req.requested_by) if req.requested_by else None
        if suggestion is None and requester is not None:
            from app.services.find_room import alternatives_for

            racc = await load_access(session, requester)
            alts = await alternatives_for(
                session, racc, room, rows[0].date, rows[0].start_period, rows[0].end_period, rows[0].headcount
            )
            suggestion = {"alternatives": alts} if alts else None
        req.suggestion = suggestion
        await _close(session, req, rows, REJECTED, note or "rejected by the approver", access.user)
        await publish_event(
            session,
            "approval.reject",
            "approval_request",
            req.id,
            before={"status": PENDING},
            after={"status": REJECTED, "suggestion": suggestion},
            actor=access.user,
            reason=note,
        )
        alt_txt = ""
        if alt_out:
            span = f"P{alt_out['start_period']}-P{alt_out['end_period']}"
            alt_txt = f" Öneri / suggestion: {alt_out['room_name']} {alt_out['date']} {span}."
        elif suggestion:
            alt_txt = " Öneri / suggestions: " + ", ".join(a["name"] for a in suggestion["alternatives"]) + "."
        await _notify_requester(session, req, "approval.rejected", access.user, alt_txt)
        await session.commit()
        return await request_out(session, access, req, detail=True)
    # approve
    steps = snap.get("steps") or DEFAULT_STEPS
    need = int(steps[min(req.step, len(steps)) - 1].get("min_approvals") or 1)
    await session.flush()
    got = {
        uid
        for uid in (
            await session.execute(
                select(ApprovalDecision.approver_user_id).where(
                    ApprovalDecision.request_id == req.id,
                    ApprovalDecision.step == req.step,
                    ApprovalDecision.decision == APPROVED,
                )
            )
        ).scalars()
    }
    if len(got) < need or req.step < len(steps):
        if len(got) >= need:
            req.step += 1
            first = rows[0]
            await _notify_approvers(session, req, room, first, await session.get(User, req.requested_by) or access.user)
        await publish_event(
            session,
            "approval.step",
            "approval_request",
            req.id,
            after={"step": req.step, "approvals": len(got)},
            actor=access.user,
            reason=note,
        )
        await session.commit()
        return await request_out(session, access, req, detail=True)
    booked, failed = await _finalise(session, access, req, room, rows, alt_out, instances)
    if not booked:
        from app.services.find_room import alternatives_for

        first = rows[0]
        requester = await session.get(User, req.requested_by) if req.requested_by else None
        racc = await load_access(session, requester) if requester is not None else access
        alts = await alternatives_for(
            session, racc, room, first.date, first.start_period, first.end_period, first.headcount
        )
        await session.rollback()
        raise _err(
            409,
            "conflict",
            "the slot is no longer free",
            "bu saat artık boş değil",
            problems=failed,
            alternatives=alts,
        )
    req.status, req.decided_at = APPROVED, utcnow()
    if req.series_id is not None:
        series = await session.get(BookingSeries, req.series_id)
        if series is not None:
            series.status = BOOKED
            if alt_out:
                series.room_id = alt_out["room_id"]
    await publish_event(
        session,
        "approval.approve",
        "approval_request",
        req.id,
        before={"status": PENDING},
        after={"status": APPROVED, "booked": [b.id for b in booked], "not_booked": failed, "alternative": alt_out},
        actor=access.user,
        reason=note,
    )
    # competing requests for the same slots lose, with a reason and free alternatives
    for other in await competing(session, req):
        other_rows = [b for b in await bookings_of(session, other) if b.status == PENDING]
        clash = [
            b
            for b in other_rows
            if any(
                x.room_id == b.room_id
                and x.date == b.date
                and x.start_period <= b.end_period
                and b.start_period <= x.end_period
                for x in booked
            )
        ]
        if not clash:
            continue
        other.note = "Aynı saat başka bir talebe verildi / the slot was given to another request"
        await _close(session, other, other_rows, REJECTED, other.note, access.user)
        await publish_event(
            session,
            "approval.reject",
            "approval_request",
            other.id,
            after={"status": REJECTED, "competing_with": req.id},
            actor=access.user,
            reason=other.note,
        )
        await _notify_requester(session, other, "approval.rejected", access.user)
    await _notify_requester(session, req, "approval.approved", access.user)
    await session.commit()
    return await request_out(session, access, req, detail=True)


async def _finalise(
    session: AsyncSession,
    access: Access,
    req: ApprovalRequest,
    room: Room,
    rows: list[Booking],
    alt: dict[str, Any] | None,
    instances: list[date] | None,
) -> tuple[list[Booking], list[dict[str, Any]]]:
    """Book the request's instances: re-check the calendar and occupancy, insert the slots (unique key)."""
    from app.models import Term

    term = await session.get(Term, req.term_id) if req.term_id else None
    info = await term_info(session, term) if term else None
    chosen = set(instances or [])
    booked: list[Booking] = []
    failed: list[dict[str, Any]] = []
    target = await session.get(Room, alt["room_id"]) if alt else room
    assert target is not None
    for b in rows:
        if b.status != PENDING:
            continue
        if chosen and b.date not in chosen:
            b.status, b.cancel_reason, b.held_until = REJECTED, "not approved (other instances were)", None
            await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
            failed.append({"date": b.date.isoformat(), "reason": "not_selected"})
            continue
        new_date = date.fromisoformat(alt["date"]) if alt and req.series_id is None else b.date
        s, e = (alt["start_period"], alt["end_period"]) if alt else (b.start_period, b.end_period)
        if info is not None:
            di = (await date_infos(session, info, [new_date]))[new_date]
            if not di.open:
                b.status, b.cancel_reason, b.held_until = (
                    REJECTED,
                    f"closed: {di.reason} {di.holiday or ''}".strip(),
                    None,
                )
                await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
                failed.append({"date": new_date.isoformat(), "reason": di.reason, "holiday": di.holiday})
                continue
        if alt:
            if alt.get("period_id"):
                b.period_id = alt["period_id"]
            elif info is not None:
                try:
                    b.period_id = await _period_for_span(session, info, target, new_date, s, e)
                except CalendarError as exc:
                    raise _err(422, "alternative", str(exc), "önerilen saat bu odanın ders saatlerinde yok") from exc
            b.room_id, b.date, b.start_period, b.end_period = target.id, new_date, s, e
        held = await bsvc.find_conflict(session, target.id, new_date, s, e, exclude={b.id})
        if held is not None:
            failed.append({"date": new_date.isoformat(), "reason": "conflict", "held": held.as_dict()})
            if req.series_id is not None:
                b.status, b.cancel_reason, b.held_until = REJECTED, "slot taken before approval", None
                await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
            continue
        await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
        await bsvc.release_expired_holds(session, target.id, new_date)
        savepoint = await session.begin_nested()
        try:
            b.status, b.held_until, b.updated_at, b.updated_by = BOOKED, None, utcnow(), access.user_id
            await session.flush()
            for slot in bsvc.slot_rows(b):
                session.add(slot)
            await session.flush()
        except Exception:  # noqa: BLE001 - IntegrityError: a concurrent approval won the unique slot key
            await savepoint.rollback()
            failed.append({"date": new_date.isoformat(), "reason": "conflict"})
            continue
        await savepoint.commit()
        booked.append(b)
    return booked, failed


async def _period_for_span(session: AsyncSession, info: Any, room: Room, d: date, s: int, e: int) -> int:
    from app.services.bookings_calendar import applied_schedule

    schedule = await applied_schedule(session, info, room)
    if schedule is None:
        raise CalendarError(f"no schedule is set for {room.display_name}")
    for p in schedule.periods:
        if p.start_period == s and p.end_period == e and p.bookable and d.isoweekday() in (p.days or []):
            return p.id
    raise CalendarError(f"P{s}-P{e} is not a bookable period of {room.display_name}")
