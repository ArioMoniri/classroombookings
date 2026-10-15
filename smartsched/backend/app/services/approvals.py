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
* The requester and the approvers are notified through :mod:`app.services.notify_dispatch` (in-app
  ``inapp_notifications`` + the e-mail outbox ``notification_outbox``, per-user channel preferences, once per
  occurrence, recipient and channel); every transition is audited (P7).

Approval-first bookings (owner requirement 2026-10-15)
-----------------------------------------------------
* ``bookings.approval_mode`` = ``rules`` (default; above) or ``all``: every booking request without a rule of its
  own goes to the approvers first (designated approvers of the room, else the fallback chain). Users holding
  ``approvals.decide``, ``planning.admin`` or ``bookings.skip_approval`` book directly. A room's own approval rule
  applies in both modes exactly as before (its steps, hold, lead time, self-approval).
* A rejection needs a reason: a reason code (:data:`REASON_CODES`) other than ``other``, or a non-blank free text
  (``other`` needs the text); 422 ``reason_required`` otherwise. Stored on the request and on every decision (per
  period in group decisions). The requester sees the reason and who decided.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.util import await_only

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
    RoomGroup,
    User,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, EXPIRED, PENDING, REJECTED, WITHDRAWN
from app.models.catalog import Room
from app.services import audit
from app.services import bookings as bsvc
from app.services import bookings_notify as mail
from app.services import notify_dispatch as nd
from app.services.bookings_calendar import CalendarError, date_infos, holidays_by_date, term_info
from app.services.bookings_perms import SKIP_APPROVAL, Access, load_access
from app.services.bookings_settings import get_value
from app.services.events import publish_event

DECIDE = "approvals.decide"
APPROVED = "APPROVED"
MODE_ALL = "all"
#: structured rejection reasons: code -> (Turkish, English). "other" needs a free text; "slot_taken" is set by the
#: system when a competing request for the same slot was approved (not accepted from the API).
REASON_CODES: dict[str, tuple[str, str]] = {
    "room_unavailable": ("Oda uygun değil", "Room unavailable"),
    "capacity": ("Kapasite yetersiz", "Not enough seats"),
    "policy": ("Rezervasyon kurallarına uygun değil", "Against the booking policy"),
    "other": ("Diğer", "Other"),
}
SYSTEM_REASONS: dict[str, tuple[str, str]] = {
    "slot_taken": ("Aynı saat başka bir talebe verildi", "The slot was given to another request"),
}
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


async def approval_mode(session: AsyncSession) -> str:
    """``bookings.approval_mode``: ``all`` or ``rules`` (anything else reads as ``rules``)."""
    return MODE_ALL if await get_value(session, "bookings", "approval_mode") == MODE_ALL else "rules"


def skips_approval(access: Access) -> bool:
    """Approvers, planning administrators and holders of ``bookings.skip_approval`` are not sent to the approvers
    by ``approval_mode = all`` (a room's own rule still applies)."""
    return access.can(DECIDE) or access.can("planning.admin") or access.can(SKIP_APPROVAL)


def mode_snapshot() -> dict[str, Any]:
    """The snapshot of a request made only because ``approval_mode`` is ``all`` (no rule of its own)."""
    return {**rule_snapshot(None), "source": "approval_mode"}


class RulesIndex:
    """The active rules, loaded once per request; the most specific rule wins (room > room group > room type),
    a rule of the booking's term before a rule of every term. ``mode``: ``bookings.approval_mode``."""

    def __init__(self, rules: list[ApprovalRule], mode: str = "rules") -> None:
        self.rules = rules
        self.mode = mode
        self._approvers: dict[int, bool] = {}

    @classmethod
    async def load(cls, session: AsyncSession) -> RulesIndex:
        q = select(ApprovalRule).where(ApprovalRule.active.is_(True)).order_by(ApprovalRule.id)
        return cls(list((await session.execute(q)).scalars()), await approval_mode(session))

    def mode_requires(self, access: Access, create: bool, request: bool) -> bool:
        """``approval_mode = all`` sends this booking (no rule of its own) to the approvers."""
        return self.mode == MODE_ALL and (create or request) and not skips_approval(access)

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
            if self.mode_requires(access, create, request):
                return "request"
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
        if rules.mode_requires(access, create, request):
            # every request is approved first; step_approvers falls back to the approvers of every room, the room
            # owner, then the Administrators, so the request is never orphaned
            return Need(None, mode_snapshot())
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
    # a single request expires before its start; a series before its last instance starts (instances that
    # started meanwhile are not booked when it is approved)
    last = max(bookings, key=lambda b: (b.date, b.start_period))
    expires = await _start_of(session, last if series is not None else first) - timedelta(
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
    await notify_approvers(session, req, room, bookings, access.user)
    return req


# --------------------------------------------------------------------------------------------------
# Notifications (app.services.notify_dispatch: in-app + e-mail outbox, per-user preferences, idempotent)
# --------------------------------------------------------------------------------------------------


def _hm(t: Any) -> str:
    return f"{t:%H:%M}" if t is not None else ""


async def summary(session: AsyncSession, room: Room, rows: list[Booking]) -> tuple[str, dict[str, Any]]:
    """``A 201, 18.02.2026 P3-P5 10:10-12:30`` and the structured facts (room, dates, periods) of ``rows``."""
    rows = sorted(rows, key=lambda b: (b.date, b.start_period, b.id))
    dates = sorted({b.date for b in rows})
    seen: dict[tuple[int, int], dict[str, Any]] = {}
    for b in rows:
        if (b.start_period, b.end_period) in seen:
            continue
        p = await session.get(BookingPeriod, b.period_id)
        seen[(b.start_period, b.end_period)] = {
            "name": p.name if p else f"P{b.start_period}",
            "start": _hm(p.time_start) if p else "",
            "end": _hm(p.time_end) if p else "",
            "start_period": b.start_period,
            "end_period": b.end_period,
        }
    periods = [seen[k] for k in sorted(seen)]
    contiguous = all(b["start_period"] == a["end_period"] + 1 for a, b in zip(periods, periods[1:], strict=False))
    if len(periods) == 1:
        span = f"{periods[0]['name']} {periods[0]['start']}-{periods[0]['end']}"
    elif periods and contiguous:
        span = f"{periods[0]['name']}-{periods[-1]['name']} {periods[0]['start']}-{periods[-1]['end']}"
    else:
        span = ", ".join(f"{p['name']} {p['start']}-{p['end']}" for p in periods)
    if len(dates) == 1:
        when = f"{dates[0]:%d.%m.%Y}"
    elif dates:
        when = f"{dates[0]:%d.%m.%Y} - {dates[-1]:%d.%m.%Y} ({len(dates)} tarih / dates)"
    else:
        when = ""
    what = f"{room.display_name}, {when} {span.replace('  ', ' ').strip()}".strip().rstrip(",")
    data = {
        "room_id": room.id,
        "room": room.display_name,
        "dates": [d.isoformat() for d in dates],
        "periods": periods,
        "booking_ids": [b.id for b in rows],
    }
    return what, data


TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    # kind -> language -> (title, body); placeholders: who, what, note, alt, reason
    "approval.requested": {
        "tr": ("Onay bekleyen oda talebi: {what}", "{who} şu oda için onay istiyor: {what}.{note}"),
        "en": ("Room request awaiting approval: {what}", "{who} asks for approval: {what}.{note}"),
    },
    "approval.approved": {
        "tr": ("Oda talebiniz onaylandı: {what}", "{who} talebinizi onayladı: {what}.{note}"),
        "en": ("Your room request was approved: {what}", "{who} approved your request: {what}.{note}"),
    },
    "approval.rejected": {
        "tr": ("Oda talebiniz reddedildi: {what}", "{who} talebinizi reddetti: {what}.\nGerekçe: {reason}{alt}"),
        "en": ("Your room request was declined: {what}", "{who} declined your request: {what}.\nReason: {reason}{alt}"),
    },
    "approval.withdrawn": {
        "tr": ("Oda talebinizi geri çektiniz: {what}", "Talebiniz geri çekildi: {what}."),
        "en": ("You withdrew your room request: {what}", "Your request was withdrawn: {what}."),
    },
    # to the approvers of the withdrawn request
    "approval.withdrawn.approver": {
        "tr": ("Oda talebi geri çekildi: {what}", "{who} onayınızı bekleyen talebini geri çekti: {what}."),
        "en": ("Room request withdrawn: {what}", "{who} withdrew the request awaiting your approval: {what}."),
    },
    "approval.expired": {
        "tr": ("Oda talebinizin süresi doldu: {what}", "Talebiniz başlangıçtan önce onaylanmadı: {what}.{note}"),
        "en": ("Your room request expired: {what}", "Your request was not approved before it started: {what}.{note}"),
    },
}
DECISION_OF = {
    "approval.approved": "approved",
    "approval.rejected": "rejected",
    "approval.withdrawn": "withdrawn",
    "approval.expired": "expired",
}


def reason_label(code: str | None, lang: str) -> str | None:
    pair = REASON_CODES.get(code or "") or SYSTEM_REASONS.get(code or "")
    if pair is None:
        return None
    return pair[0] if lang == "tr" else pair[1]


def reason_both(code: str | None) -> str | None:
    """``Kapasite yetersiz / not enough seats``: the code in both languages (stored where one text is needed)."""
    pair = REASON_CODES.get(code or "") or SYSTEM_REASONS.get(code or "")
    return f"{pair[0]} / {pair[1][:1].lower()}{pair[1][1:]}" if pair else None


def reason_text(code: str | None, note: str | None, lang: str) -> str:
    """What the requester reads after "Gerekçe / Reason:" -- the code's label and the free text."""
    label = reason_label(code, lang)
    if code in SYSTEM_REASONS or not note:
        return label or note or "-"
    return f"{label}: {note}" if label and code != "other" else note


def check_reason(code: str | None, text: str | None) -> tuple[str | None, str | None]:
    """A rejection's reason, normalised (NBSP, whitespace): ``(code, text)``; 422 when there is none."""
    clean = n.clean_text(text) if text else None
    code = (n.clean_text(code) or "").lower() or None  # codes are ASCII; blank / NBSP = no code
    if code is not None and code not in REASON_CODES:
        raise _err(
            422,
            "reason_code",
            f"reason_code must be one of {', '.join(REASON_CODES)}",
            f"gerekçe kodu şunlardan biri olmalı: {', '.join(REASON_CODES)}",
        )
    if clean is None and (code is None or code == "other"):
        raise _err(
            422,
            "reason_required",
            "a rejection needs a reason: pick a reason code or write why (required for 'other')",
            "reddetmek için bir gerekçe gerekir: bir gerekçe seçin ya da nedenini yazın ('diğer' için zorunlu)",
            reason_codes=list(REASON_CODES),
        )
    return code, clean


async def _render(session: AsyncSession, user: User, kind: str, **fmt: str) -> tuple[str, str, str]:
    lang = await mail._language(session, user)
    title_t, body_t = TEXTS[kind]["tr" if lang == "tr" else "en"]
    return title_t.format(**fmt), body_t.format(**fmt), lang


def _group_of(req: ApprovalRequest, first: Booking) -> int | None:
    return first.multi_booking_id if req.series_id is None else None


def _person(u: User | None) -> dict[str, Any] | None:
    return {"id": u.id, "name": audit.user_label(u)} if u is not None else None


#: ``sync_session.info`` keys: approver notices queued in this transaction / the commit hook is installed
_APPROVER_QUEUE = "approvals.approver_notices"
_APPROVER_HOOK = "approvals.approver_hook"


async def notify_approvers(
    session: AsyncSession, req: ApprovalRequest, room: Room, rows: list[Booking], requester: User
) -> None:
    """``approval.requested`` to the approvers of the request's current step (not to the requester).

    The notice is queued and sent when the transaction commits, so that the periods of one submission (a
    multi-booking: ``group_id``, assigned by the caller after every period was created) reach every approver as
    ONE message listing them; a request outside a group gets its own message as before. A rollback drops the
    queue together with the requests. :func:`flush_approver_notices` sends the queue earlier."""
    sync = session.sync_session
    queue: list[tuple[ApprovalRequest, Room, list[Booking], User]] = sync.info.setdefault(_APPROVER_QUEUE, [])
    queue.append((req, room, list(rows), requester))
    if not sync.info.get(_APPROVER_HOOK):
        sync.info[_APPROVER_HOOK] = True

        def _before_commit(s: Any) -> None:
            if s.info.get(_APPROVER_QUEUE):
                # inside AsyncSession.commit's greenlet: run the async dispatch on the same connection and
                # transaction (the rows it adds are flushed by this commit)
                await_only(flush_approver_notices(session))

        def _drop(s: Any, *_: Any) -> None:
            s.info.pop(_APPROVER_QUEUE, None)

        event.listen(sync, "before_commit", _before_commit)
        event.listen(sync, "after_rollback", _drop)


async def flush_approver_notices(session: AsyncSession) -> int:
    """Send the queued ``approval.requested`` notices: one per approver and submission (``group_id``) and step, or
    per request outside a submission. Returns the number of messages handed to the dispatcher."""
    queue = session.sync_session.info.pop(_APPROVER_QUEUE, None) or []
    buckets: dict[tuple[Any, int], list[tuple[ApprovalRequest, Room, list[Booking], User]]] = {}
    seen: set[tuple[int, int]] = set()
    for req, room, rows, requester in queue:
        if not rows or (req.id, req.step) in seen or req.status != PENDING:
            continue
        seen.add((req.id, req.step))
        first = min(rows, key=lambda b: (b.date, b.start_period))
        gid = _group_of(req, first)
        buckets.setdefault((("group", gid) if gid is not None else ("request", req.id), req.step), []).append(
            (req, room, rows, requester)
        )
    sent = 0
    for (scope, step), entries in buckets.items():
        per_user: dict[int, tuple[User, list[tuple[ApprovalRequest, Room, list[Booking], User]]]] = {}
        for entry in entries:
            req, room, _rows, requester = entry
            for u in await step_approvers(session, room, req.rule_snapshot or {}, req.step):
                if u.id != requester.id:
                    per_user.setdefault(u.id, (u, []))[1].append(entry)
        for u, mine in per_user.values():
            await _send_requested(session, u, mine, scope, step)
            sent += 1
    return sent


async def _send_requested(
    session: AsyncSession,
    approver: User,
    entries: list[tuple[ApprovalRequest, Room, list[Booking], User]],
    scope: tuple[str, Any],
    step: int,
) -> None:
    entries = sorted(entries, key=lambda e: (min((b.date, b.start_period) for b in e[2]), e[0].id))
    req, room, _rows, requester = entries[0]
    by_room: dict[int, tuple[Room, list[Booking]]] = {}
    for _r, rm, rows, _u in entries:
        by_room.setdefault(rm.id, (rm, []))[1].extend(rows)
    parts = [await summary(session, rm, rows) for rm, rows in by_room.values()]
    what = "; ".join(p[0] for p in parts)
    base = dict(parts[0][1])
    if len(parts) > 1:
        base["rooms"] = [p[1] for p in parts]
        base["booking_ids"] = [i for p in parts for i in p[1]["booking_ids"]]
    first = min((b for e in entries for b in e[2]), key=lambda b: (b.date, b.start_period))
    ids = sorted(e[0].id for e in entries)
    title, body, _lang = await _render(
        session, approver, "approval.requested", who=audit.user_label(requester) or "-", what=what, note=""
    )
    gid = scope[1] if scope[0] == "group" else None
    if gid is not None:
        digest = hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:16]
        key, link = f"approval_group:{gid}:requested:{step}:{digest}", f"/approvals?request={req.id}&group={gid}"
    else:
        key, link = f"approval_request:{req.id}:requested:{step}", f"/approvals?request={req.id}"
    await nd.dispatch(
        session,
        approver,
        nd.Notice(
            event="approval.requested",
            key=key,
            title=title,
            body=body,
            link=link,
            booking_id=first.id,
            request_id=req.id,
            data={
                **base,
                "request_id": req.id,
                "request_ids": ids,
                "series_id": req.series_id,
                "group_id": gid,
                "step": step,
                "decision": "requested",
                "requester": _person(requester),
                "source": (req.rule_snapshot or {}).get("source") or "rule",
            },
        ),
    )


async def notify_approvers_withdrawn(
    session: AsyncSession, req: ApprovalRequest, room: Room, rows: list[Booking], requester: User
) -> None:
    """``approval.withdrawn`` to the approvers of the request's current step: the request they were asked to decide
    is gone (their own preferences for ``approval.withdrawn`` apply)."""
    if not rows:
        return
    what, base = await summary(session, room, rows)
    first = min(rows, key=lambda b: (b.date, b.start_period))
    for u in await step_approvers(session, room, req.rule_snapshot or {}, req.step):
        if u.id == requester.id:
            continue
        title, body, _lang = await _render(
            session, u, "approval.withdrawn.approver", who=audit.user_label(requester) or "-", what=what
        )
        await nd.dispatch(
            session,
            u,
            nd.Notice(
                event="approval.withdrawn",
                key=f"approval_request:{req.id}:withdrawn",
                title=title,
                body=body,
                link=f"/approvals?request={req.id}",
                booking_id=first.id,
                request_id=req.id,
                data={
                    **base,
                    "request_id": req.id,
                    "request_ids": [req.id],
                    "series_id": req.series_id,
                    "group_id": _group_of(req, first),
                    "step": req.step,
                    "decision": "withdrawn",
                    "status": req.status,
                    "requester": _person(requester),
                },
            ),
        )


async def notify_requester(
    session: AsyncSession,
    req: ApprovalRequest,
    kind: str,
    actor: User | None,
    alt: str = "",
    *,
    group: list[ApprovalRequest] | None = None,
    group_id: int | None = None,
) -> None:
    """``approval.approved`` / ``rejected`` / ``withdrawn`` / ``expired`` to the requester: room, dates, periods,
    the decision, the reason and who decided. ``group``: one notice for every request of a submission (A-12)."""
    if not req.requested_by:
        return
    user = await session.get(User, req.requested_by)
    room = await session.get(Room, req.room_id)
    if user is None or room is None:
        return
    reqs = group or [req]
    rows = [b for r in reqs for b in await bookings_of(session, r)]
    if not rows:
        return
    what, base = await summary(session, room, rows)
    lang = await mail._language(session, user)
    note = f" {'Not' if lang == 'tr' else 'Note'}: {req.note}" if req.note else ""
    reason = reason_text(req.reason_code, req.note, lang) if kind == "approval.rejected" else ""
    title, body, _lang = await _render(
        session,
        user,
        kind,
        who=audit.user_label(actor) or "SmartSched",
        what=what,
        note=note,
        alt=alt,
        reason=reason,
    )
    ids = sorted(r.id for r in reqs)
    if group is not None:
        digest = hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:16]
        key = f"approval_group:{group_id}:{DECISION_OF[kind]}:{digest}"
    else:
        key = f"approval_request:{req.id}:{DECISION_OF[kind]}"
    first = min(rows, key=lambda b: (b.date, b.start_period))
    await nd.dispatch(
        session,
        user,
        nd.Notice(
            event=kind,
            key=key,
            title=title,
            body=body,
            link=f"/bookings/mine?request={req.id}",
            booking_id=first.id,
            request_id=req.id,
            data={
                **base,
                "request_id": req.id,
                "request_ids": ids,
                "series_id": req.series_id,
                "group_id": group_id if group is not None else _group_of(req, first),
                "decision": DECISION_OF[kind],
                "status": req.status,
                "reason": (req.note or reason_both(req.reason_code)) if kind == "approval.rejected" else None,
                "reason_code": req.reason_code if kind == "approval.rejected" else None,
                "note": req.note,
                "suggestion": alt.strip() or None,
                "decided_by": _person(actor),
            },
        ),
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
        # who closed it (the requester may see the deciding approver); None while open or when it expired
        "decided_by": _person(await session.get(User, req.decided_by)) if req.decided_by else None,
        "note": req.note,
        # a rejection's reason: the free text, else the reason code in Turkish / English
        "reason": (req.note or reason_both(req.reason_code)) if req.status == REJECTED else None,
        "reason_code": req.reason_code if req.status == REJECTED else None,
        "suggestion": req.suggestion,
        "bookings": [await bsvc.booking_out(session, access, b) for b in rows],
        # A-12: the periods of one submission share the multi-booking id (series requests are one request already)
        "group_id": rows[0].multi_booking_id if (rows and req.series_id is None) else None,
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
                "reason_code": d.reason_code,
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


async def sees_request(session: AsyncSession, access: Access, b: Booking) -> bool:
    """U-06: the booking grid shows a PENDING request to whoever asked for it (or is booked for it) and to the
    approvers of its current step; everyone else sees the slot free while requests compete."""
    if access.user_id in (b.created_by, b.user_id):
        return True
    if not access.can(DECIDE):
        return False
    req = await request_for_booking(session, b)
    room = await session.get(Room, b.room_id)
    if req is None or room is None or req.status != PENDING:
        return False
    return access.user in await step_approvers(session, room, req.rule_snapshot or {}, req.step)


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


def group_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A-12: inbox entries -> one entry per submission (``group_id``, its requests in period order, the span); a
    request without a group is an entry of its own (``group_id`` None, one request)."""
    out: list[dict[str, Any]] = []
    by_group: dict[tuple[int, str, int], dict[str, Any]] = {}
    for it in items:
        b = (it.get("bookings") or [{}])[0]
        gid = it.get("group_id")
        key = (int(gid), str(b.get("date")), int(it["room_id"])) if gid else None
        entry = by_group.get(key) if key else None
        if entry is None:
            entry = {
                "group_id": gid,
                "room_id": it["room_id"],
                "room_name": it.get("room_name"),
                "date": b.get("date"),
                "requested_by": it.get("requested_by"),
                "requester_name": it.get("requester_name"),
                "requested_at": it.get("requested_at"),
                "expires_at": it.get("expires_at"),
                "status": it.get("status"),
                "requests": [],
            }
            out.append(entry)
            if key:
                by_group[key] = entry
        entry["requests"].append(it)
    for e in out:
        e["requests"].sort(key=lambda r: ((r.get("bookings") or [{}])[0].get("start_period") or 0, r["id"]))
        spans = [b for r in e["requests"] for b in (r.get("bookings") or [])]
        e["start_period"] = min((b.get("start_period") or 0 for b in spans), default=None)
        e["end_period"] = max((b.get("end_period") or 0 for b in spans), default=None)
        e["request_ids"] = [r["id"] for r in e["requests"]]
        exp = [r["expires_at"] for r in e["requests"] if r.get("expires_at")]
        e["expires_at"] = min(exp) if exp else None
        statuses = {r.get("status") for r in e["requests"]}
        e["status"] = statuses.pop() if len(statuses) == 1 else "MIXED"
    return out


async def decide_group(
    session: AsyncSession,
    access: Access,
    group_id: int,
    decision: str,
    note: str | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    """A-12: decide every open request of one submission whose current step the caller may decide, in period
    order; each is decided (and audited) like ``POST /approvals/{id}/decide``, a failure is reported per request.
    Per-period decisions stay possible through the single endpoint. A rejection needs a reason (stored on every
    period's request and decision); the requester gets one notification for the submission."""
    if not access.can(DECIDE):
        raise _err(403, "not_an_approver", "you may not decide approval requests", "onay talebi karara bağlayamazsınız")
    if decision == "reject":
        reason_code, note = check_reason(reason_code, note)
    await sweep(session)
    q = (
        select(ApprovalRequest)
        .join(Booking, Booking.id == ApprovalRequest.booking_id)
        .where(ApprovalRequest.status == PENDING, Booking.multi_booking_id == group_id)
        .order_by(Booking.date, Booking.start_period, ApprovalRequest.id)
    )
    reqs = list((await session.execute(q)).scalars())
    results: list[dict[str, Any]] = []
    for req in reqs:
        room = await session.get(Room, req.room_id)
        if room is None or access.user not in await step_approvers(session, room, req.rule_snapshot or {}, req.step):
            continue
        try:
            out = await decide(session, access, req.id, decision, note, reason_code=reason_code, notify=False)
            results.append({"request_id": req.id, "ok": True, "status": out.get("status")})
        except (ApprovalError, bsvc.BookingError) as exc:
            await session.rollback()
            results.append({"request_id": req.id, "ok": False, "code": exc.code, "message": exc.message})
    await _notify_group(session, access, group_id, [r["request_id"] for r in results if r["ok"]])
    return {"group_id": group_id, "decision": decision, "results": results}


async def _notify_group(session: AsyncSession, access: Access, group_id: int, ids: list[int]) -> None:
    """One notification per requester and outcome for the requests of a submission decided together, and one
    ``approval.requested`` per next-step approver for the requests the decision moved on to their next step."""
    if not ids:
        return
    q = select(ApprovalRequest).where(ApprovalRequest.id.in_(ids)).execution_options(populate_existing=True)
    by_outcome: dict[tuple[int | None, str], list[ApprovalRequest]] = {}
    advanced: list[ApprovalRequest] = []
    for r in (await session.execute(q.order_by(ApprovalRequest.id))).scalars():
        kind = {APPROVED: "approval.approved", REJECTED: "approval.rejected"}.get(r.status)
        if kind is not None:
            by_outcome.setdefault((r.requested_by, kind), []).append(r)
        elif r.status == PENDING:
            advanced.append(r)
    for (_uid, kind), reqs in by_outcome.items():
        await notify_requester(session, reqs[0], kind, access.user, group=reqs, group_id=group_id)
    # requests that moved on to their next step: one approval.requested per next-step approver for the submission
    for r in advanced:
        room = await session.get(Room, r.room_id)
        requester = await session.get(User, r.requested_by) if r.requested_by else None
        if room is not None:
            await notify_approvers(session, r, room, await bookings_of(session, r), requester or access.user)
    await session.commit()


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
    req.decided_by = actor.id if actor is not None else None
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
        await notify_requester(session, req, "approval.expired", None)
        expired += 1
    released = await bsvc.release_expired_holds(session)
    if expired or released:
        await session.commit()
    return {"expired": expired, "released": released}


async def withdraw(session: AsyncSession, access: Access, request_id: int) -> ApprovalRequest:
    req, room = await _load(session, request_id)
    if req.requested_by != access.user_id:
        raise _err(
            403, "not_requester", "only the requester can withdraw a request", "talebi yalnız sahibi geri çekebilir"
        )
    if req.status != PENDING:
        raise _err(409, "not_pending", f"the request is {req.status}", f"talep {req.status} durumunda")
    rows = await bookings_of(session, req)
    await _close(session, req, rows, WITHDRAWN, "withdrawn by the requester", access.user)
    await publish_event(
        session, "approval.withdraw", "approval_request", req.id, after={"status": WITHDRAWN}, actor=access.user
    )
    await notify_requester(session, req, "approval.withdrawn", access.user)
    await notify_approvers_withdrawn(session, req, room, rows, access.user)
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
    *,
    reason_code: str | None = None,
    notify: bool = True,
) -> dict[str, Any]:
    """``approve`` (optionally in another room = ``alternative``), ``reject`` (optionally suggesting
    ``alternative``; needs a reason: ``reason_code`` and / or the free text ``note``, :func:`check_reason`).
    Approval of the last step books the slot after re-checking it. ``notify=False``: the caller notifies the
    requester (group decisions send one notice per submission)."""
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
    if decision == "reject":
        reason_code, note = check_reason(reason_code, note)
    else:
        note, reason_code = (n.clean_text(note) if note else None), None
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
            reason_code=reason_code,
            alternative=alt_out,
        )
    )
    req.note, req.reason_code = note, reason_code
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
        why = note or reason_both(reason_code) or "rejected by the approver"
        await _close(session, req, rows, REJECTED, why, access.user)
        await publish_event(
            session,
            "approval.reject",
            "approval_request",
            req.id,
            before={"status": PENDING},
            after={"status": REJECTED, "suggestion": suggestion, "reason_code": reason_code},
            actor=access.user,
            reason=why,
        )
        alt_txt = ""
        if alt_out:
            span = f"P{alt_out['start_period']}-P{alt_out['end_period']}"
            alt_txt = f" Öneri / suggestion: {alt_out['room_name']} {alt_out['date']} {span}."
        elif suggestion:
            alt_txt = " Öneri / suggestions: " + ", ".join(a["name"] for a in suggestion["alternatives"]) + "."
        if notify:
            await notify_requester(session, req, "approval.rejected", access.user, alt_txt)
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
            if notify:  # a group decision queues the next step's notice once for the submission (_notify_group)
                requester = await session.get(User, req.requested_by) if req.requested_by else None
                await notify_approvers(session, req, room, rows, requester or access.user)
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
    # read before _finalise: a lost race rolls its savepoint back, which expires the booking rows (an async
    # session cannot lazy-load them afterwards; seen on PostgreSQL, tests/test_postgres_concurrency.py)
    first_slot = (rows[0].date, rows[0].start_period, rows[0].end_period, rows[0].headcount)
    requested_by = req.requested_by
    booked, failed = await _finalise(session, access, req, room, rows, alt_out, instances)
    if not booked:
        from app.services.find_room import alternatives_for

        requester = await session.get(User, requested_by) if requested_by else None
        racc = await load_access(session, requester) if requester is not None else access
        alts = await alternatives_for(session, racc, room, *first_slot)
        await session.rollback()
        raise _err(
            409,
            "conflict",
            "the slot is no longer free",
            "bu saat artık boş değil",
            problems=failed,
            alternatives=alts,
        )
    req.status, req.decided_at, req.decided_by = APPROVED, utcnow(), access.user_id
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
        other.reason_code = "slot_taken"
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
        await notify_requester(session, other, "approval.rejected", access.user)
    if notify:
        await notify_requester(session, req, "approval.approved", access.user)
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
        if req.series_id is not None and await _start_of(session, b) <= await bsvc.now_local(session):
            b.status, b.cancel_reason, b.held_until = EXPIRED, "started before it was approved", None
            await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == b.id))
            failed.append({"date": b.date.isoformat(), "reason": "started"})
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
