"""The five helper writes (HB-05): ``create_booking``, ``cancel_my_booking``, ``withdraw_my_request``,
``decide_approval`` and ``undo_last_helper_action``.

Owner defaults (2026-10-18): anyone may book, cancel and withdraw **their own single** bookings and requests;
approvers may also decide requests; nothing else writes from the helper. No on-behalf, recurring or bulk writes.

Each write has a ``preview`` and an ``execute``:

* ``preview`` walks the service's own check path with the person's ``Access`` and **writes nothing**: for a booking
  the same checks as ``bookings.create_single`` in the same order (room visible and bookable, the term and the open
  date, the approval need, the lead time, ``booking_policies.enforce``, the booking window, the period not started,
  the active-booking limit, a duplicate request, the free-slot check, the unpublished-timetable warning). It answers
  a :class:`Preview` (rows, the button text, a hash of the facts) or a ``form`` / ``choice`` card when an argument
  is missing or ambiguous (helper.md A1: everything resolved → ``confirm`` directly).
* ``execute`` calls the page's service (``create_single``, ``cancel``, ``approvals.withdraw``, ``approvals.decide``,
  ``bookings_undo.undo``) and runs only from :func:`app.ai.helper.confirm.confirm`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import Field
from sqlalchemy import func, select

from app.ai.helper import cards
from app.ai.helper import confirm as cf
from app.ai.helper import schema as s
from app.ai.helper.actions.common import DayText, day_label, resolve_day, resolve_rooms
from app.ai.helper.actions.registry import REGISTRY, Action, ActionRefused, Args, Ctx, action
from app.models import ApprovalRequest, AuditEvent, Booking, BookingPeriod, User
from app.models.base import utcnow
from app.models.booking import BOOKED, PENDING
from app.models.catalog import Room
from app.services import approvals as asvc
from app.services import audit, booking_policies
from app.services import bookings as bsvc
from app.services.bookings_calendar import CalendarError, period_for, resolve_term
from app.services.bookings_perms import effective_limits
from app.services.bookings_settings import get_value

WRITE_RATE = (10, 60)
BOOKERS = ("book_single.create", "book_single.request")

#: Turkish for the booking service's English-only refusals (the API keeps ``message`` in English)
TR_BY_CODE = {
    "conflict": "Bu saat dolu.",
    "room_not_found": "Salon bulunamadı.",
    "room_not_bookable": "Bu salon rezervasyona kapalı.",
    "calendar": "Bu tarih için takvim tanımlı değil.",
    "holiday": "Bu gün tatil.",
    "no_week": "Bu tarih için ders haftası tanımlı değil.",
    "date_range": "Bu tarih dönemin dışında.",
    "closed": "Bu gün rezervasyona kapalı.",
    "not_cancelable": "Bu rezervasyonu iptal edemezsiniz.",
    "already_cancelled": "Bu rezervasyon zaten iptal edilmiş.",
    "max_active_bookings": "Etkin rezervasyon sınırınıza ulaştınız.",
    "not_found": "Kayıt bulunamadı.",
    "book_single.create": "Bu salonda rezervasyon yetkiniz yok.",
    "range_min": "Bu tarih için henüz rezervasyon yapılamaz.",
    "range_max": "Bu tarih rezervasyon aralığının dışında.",
}


def refusal(exc: bsvc.BookingError) -> ActionRefused:
    d = dict(exc.data)
    tr = (
        d.pop("message_tr", None)
        or TR_BY_CODE.get(exc.code)
        or (
            "Rezervasyon kuralları buna izin vermiyor."
            if exc.code.startswith("policy")
            else "Bu işlem şu an yapılamadı."
        )
    )
    en = d.pop("message_en", None) or exc.message
    keep = {k: v for k, v in d.items() if k in ("conflict", "alternatives", "request_id", "booking_id", "earliest")}
    return ActionRefused(exc.status, exc.code, str(tr), str(en), **keep)


@dataclass
class Preview:
    action: str
    risk: Literal["R1", "R2"]
    args: dict[str, Any]
    #: the facts the write depends on; their hash is signed into the token and compared on confirm
    facts: dict[str, Any]
    lines: list[s.PreviewLine]
    button: s.Txt
    title: s.Txt
    undoable: bool
    danger: bool = False
    affected: s.Txt | None = None
    warnings: list[s.Txt] = field(default_factory=list)

    @property
    def hash(self) -> str:
        return cf.digest({"action": self.action, **self.facts})


PreviewFn = Callable[[Ctx, Any], Awaitable["Preview | s.CardBase"]]
ExecuteFn = Callable[[Ctx, Any, Preview], Awaitable[cf.Executed]]


@dataclass(frozen=True)
class WriteSpec:
    action: Action
    preview: PreviewFn
    execute: ExecuteFn


WRITES: dict[str, WriteSpec] = {}


def line(tr_label: str, en_label: str, tr: str, en: str | None = None) -> s.PreviewLine:
    return s.PreviewLine(label=cards.txt(tr_label, en_label), value=cards.txt(tr, en))


async def to_card(ctx: Ctx, p: Preview | s.CardBase) -> s.CardBase:
    """A preview becomes the ``confirm`` card with its signed token; a form / choice passes through."""
    if not isinstance(p, Preview):
        return p
    token, exp = cf.confirm_token(ctx.access.user_id, p.action, p.args, p.hash, utcnow())
    return s.ConfirmCard(
        id=cards.new_id(),
        action=p.action,
        title=p.title,
        risk=p.risk,
        token=token,
        expires_at=exp,
        preview=p.lines,
        affected=p.affected,
        warnings=p.warnings,
        button=p.button,
        undoable=p.undoable,
        danger=p.danger,
        args={k: v for k, v in p.args.items() if isinstance(v, str | int | float | bool) or v is None},
    )


def write(
    *,
    name: str,
    permission: tuple[str, ...],
    args: type[Args],
    summary_tr: str,
    summary_en: str,
    description: str,
    route: str,
    risk: Literal["R1", "R2"],
    route_args: dict[str, str] | None = None,
    resolved: tuple[str, ...] = (),
    gate: Literal["maintenance", "list"] | None = None,
) -> Callable[[PreviewFn], PreviewFn]:
    """Register a write: the decorated function is its preview; :func:`executes` attaches the execute step."""

    def deco(preview: PreviewFn) -> PreviewFn:
        async def run(ctx: Ctx, a: Any) -> s.CardBase:
            return await to_card(ctx, await preview(ctx, a))

        action(
            name=name,
            kind="write",
            permission=permission,
            args=args,
            summary_tr=summary_tr,
            summary_en=summary_en,
            description=description,
            route=route,
            card="confirm",
            route_args=route_args,
            resolved=resolved,
            risk=risk,
            rate=WRITE_RATE,
            gate=gate,
        )(run)
        _PREVIEWS[name] = preview
        return preview

    return deco


_PREVIEWS: dict[str, PreviewFn] = {}


def executes(name: str) -> Callable[[ExecuteFn], ExecuteFn]:
    def deco(fn: ExecuteFn) -> ExecuteFn:
        WRITES[name] = WriteSpec(REGISTRY[name], _PREVIEWS[name], fn)
        return fn

    return deco


async def _booking_audit_event(ctx: Ctx, action_name: str, booking_id: int) -> int | None:
    row = (
        await ctx.session.execute(
            select(func.max(AuditEvent.id)).where(
                AuditEvent.action == action_name,
                AuditEvent.entity_type == "booking",
                AuditEvent.entity_id == str(booking_id),
            )
        )
    ).scalar()
    return int(row) if row is not None else None


async def _undo_until(ctx: Ctx, d: date, period: BookingPeriod | None) -> datetime:
    """The booking's start as naive UTC (``bookings_undo`` allows undo until then, or 24 h after the change)."""
    start = datetime.combine(d, period.time_start if period else datetime.min.time())
    return utcnow() + (start - await bsvc.now_local(ctx.session))


def _when(d: date, period: BookingPeriod) -> tuple[str, str]:
    tr_day, en_day = day_label(d)
    t = f"{period.time_start:%H:%M}–{period.time_end:%H:%M}"
    return f"{tr_day} {t}", f"{en_day} {t}"


# ------------------------------------------------------------------------------------------- create_booking


class CreateBookingArgs(Args):
    room: Annotated[str, Field(max_length=40, description="room code, name or id from a result, e.g. 'A 204'")] = ""
    date: DayText = ""
    period_id: Annotated[int, Field(ge=0, description="booking period id from a result; 0 = not chosen yet")] = 0
    notes: Annotated[str, Field(max_length=255, description="the purpose, in the user's words; '' = none")] = ""


def _booking_form(a: CreateBookingArgs, missing: list[str], room: Room | None) -> s.FormCard:
    return s.FormCard(
        id=cards.new_id(),
        action="create_booking",
        title=cards.txt("Rezervasyon", "Booking"),
        risk="R1",
        missing=missing,
        fields=[
            s.FormField(
                name="room",
                label=cards.txt("Salon", "Room"),
                kind="room",
                required=True,
                value=str(room.id) if room else (a.room or None),
                options_source="rooms",
            ),
            s.FormField(
                name="date", label=cards.txt("Tarih", "Date"), kind="date", required=True, value=a.date or None
            ),
            s.FormField(
                name="period_id",
                label=cards.txt("Ders saati", "Period"),
                kind="period",
                required=True,
                value=a.period_id or None,
                options_source="periods",
            ),
            s.FormField(
                name="notes",
                label=cards.txt("Amaç", "Purpose"),
                kind="text",
                required=False,
                value=a.notes or None,
                max_length=255,
            ),
        ],
    )


@write(
    name="create_booking",
    permission=BOOKERS,
    args=CreateBookingArgs,
    summary_tr="Rezerve et",
    summary_en="Book a room",
    description="Prepare one single booking of one room, on one date, in one period, for the user themself. "
    "The user confirms it on the card; nothing is booked before.",
    route="POST /bookings",
    risk="R1",
    route_args={"date": "date", "period_id": "period_id", "notes": "notes"},
    resolved=("room",),
    gate="maintenance",
)
async def preview_create_booking(ctx: Ctx, a: CreateBookingArgs) -> Preview | s.CardBase:
    from app.ai.helper.actions.bookings import _choice

    room: Room | None = None
    if a.room:
        rooms = await resolve_rooms(ctx, a.room)
        if not rooms:
            raise ActionRefused(
                404,
                "room_not_found",
                f"“{a.room}” adında bir salon bulunamadı.",
                f"No room called “{a.room}” was found.",
            )
        if len(rooms) > 1:
            return _choice("room", rooms, a.model_dump(), "create_booking")
        room = rooms[0]
    d = await resolve_day(ctx, a.date)
    missing = [n for n, ok in (("room", room), ("date", d), ("period_id", a.period_id)) if not ok]
    if missing or room is None or d is None:
        return _booking_form(a, missing, room)
    session, access = ctx.session, ctx.access
    try:
        room = await bsvc.visible_room(session, access, room.id)
        try:
            info = await resolve_term(session, d, None, view_all=access.can("system.view_all_sessions"))
        except CalendarError as exc:
            raise bsvc.BookingError(409, "calendar", str(exc)) from exc
        need = await asvc.need_for(session, access, room, "book_single", info.term.id)
        try:
            await bsvc._open_date(session, info, d)  # noqa: SLF001 - the create path's own check
            period = await period_for(session, info, room, a.period_id, d)
        except CalendarError as exc:
            raise bsvc.BookingError(409, "calendar", str(exc)) from exc
        if need is not None:
            await asvc.check_lead_time(session, need, info.term.id, d)
        user_id = access.user_id  # never on behalf of someone else from the helper
        need = await booking_policies.enforce(session, access, room, info.term.id, d, period, user_id, need)
        await bsvc.check_window(session, access, info, d, room)
        await bsvc.check_not_started(session, access, d, period)
        if await get_value(session, "bookings", "enforce_max_active_on_create"):
            left = await bsvc.remaining_bookings(session, access)
            if left is not None and left < 1:
                limits = await effective_limits(session, access.user)
                raise bsvc.BookingError(
                    409,
                    "max_active_bookings",
                    "you already have the maximum active bookings",
                    limit=limits["max_active_bookings"],
                )
        if need is not None:
            await bsvc._refuse_duplicate_request(session, access, room, d, period, user_id)  # noqa: SLF001
        held = await bsvc.find_conflict(session, room.id, d, period.start_period, period.end_period)
        if held is not None:
            err = await bsvc._conflict_error(held, room, d)  # noqa: SLF001
            from app.services.find_room import alternatives_for

            err.data["alternatives"] = await alternatives_for(
                session, access, room, d, period.start_period, period.end_period
            )
            raise err
        st = await bsvc.timetable_state(session, d, d)
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    request = need is not None
    unpublished = st["state"] == "unpublished"
    tr_when, en_when = _when(d, period)
    lines = [
        line("Salon", "Room", room.display_name),
        line("Zaman", "When", tr_when, en_when),
        line("Kimin adına", "For", "Kendiniz", "Yourself"),
    ]
    if a.notes:
        lines.append(line("Amaç", "Purpose", a.notes))
    if request:
        lines.append(line("Onay", "Approval", "Onaycıya talep olarak gider", "Goes to an approver as a request"))
    warnings = [cards.txt(bsvc.UNPUBLISHED_TR, bsvc.UNPUBLISHED_EN)] if unpublished else []
    verb_tr, verb_en = ("Talep et", "Request") if request else ("Rezerve et", "Book")
    return Preview(
        action="create_booking",
        risk="R1",
        args={"room": str(room.id), "date": d.isoformat(), "period_id": period.id, "notes": a.notes},
        facts={
            "room": room.id,
            "date": d.isoformat(),
            "period": period.id,
            "request": request,
            "unpublished": unpublished,
            "notes": a.notes,
        },
        lines=lines,
        button=cards.txt(f"{verb_tr}: {room.display_name} · {tr_when}", f"{verb_en}: {room.display_name} · {en_when}"),
        title=cards.txt(
            "Rezervasyon talebi" if request else "Rezervasyon", "Booking request" if request else "Booking"
        ),
        undoable=not request,
        warnings=warnings,
    )


@executes("create_booking")
async def execute_create_booking(ctx: Ctx, a: CreateBookingArgs, p: Preview) -> cf.Executed:
    body = bsvc.SingleIn(
        room_id=int(p.args["room"]),
        date=date.fromisoformat(p.args["date"]),
        period_id=int(p.args["period_id"]),
        notes=a.notes or None,
        confirm_unpublished=bool(p.facts["unpublished"]),
    )
    try:
        b = await bsvc.create_single(ctx.session, ctx.access, body)
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    period = await ctx.session.get(BookingPeriod, b.period_id)
    room = await ctx.session.get(Room, b.room_id)
    name = room.display_name if room else ""
    tr_when, en_when = _when(b.date, period) if period else day_label(b.date)
    if b.status == PENDING:
        return cf.Executed(
            entity=s.Entity(kind="booking", id=b.id, feature_id="my_requests"),
            message=cards.txt(
                f"Talebiniz gönderildi: {name} · {tr_when}. Onaycı karar verince bildirim alırsınız.",
                f"Your request was sent: {name} · {en_when}. You are notified when it is decided.",
            ),
            follow_ups=[s.FollowUp(label=cards.txt("Taleplerim", "My requests"), action="my_requests_status")],
        )
    return cf.Executed(
        entity=s.Entity(kind="booking", id=b.id, feature_id="my_bookings"),
        message=cards.txt(f"{name} {tr_when} için rezerve edildi.", f"{name} booked for {en_when}."),
        undo_event_id=await _booking_audit_event(ctx, "booking.create", b.id),
        undo_until=await _undo_until(ctx, b.date, period),
        follow_ups=[
            s.FollowUp(label=cards.txt("Takvimime ekle", "Add to my calendar"), feature_id="profile.calendar"),
            s.FollowUp(label=cards.txt("Rezervasyonlarım", "My bookings"), action="my_bookings"),
        ],
    )


# ---------------------------------------------------------------------------------------- cancel_my_booking


class CancelArgs(Args):
    booking_id: Annotated[int, Field(ge=0, description="id of one of the user's own bookings; 0 = not chosen")] = 0


@write(
    name="cancel_my_booking",
    permission=(),
    args=CancelArgs,
    summary_tr="Rezervasyonumu iptal et",
    summary_en="Cancel my booking",
    description="Prepare cancelling ONE of the user's own single bookings (from my_bookings). The user confirms it.",
    route="POST /bookings/{booking_id}/cancel",
    risk="R1",
    route_args={"booking_id": "booking_id"},
    gate="maintenance",
)
async def preview_cancel(ctx: Ctx, a: CancelArgs) -> Preview | s.CardBase:
    from app.ai.helper.actions.bookings import my_bookings

    if not a.booking_id:
        return await my_bookings(ctx, REGISTRY["my_bookings"].args())  # pick one from the list
    b = await ctx.session.get(Booking, a.booking_id)
    room = await ctx.session.get(Room, b.room_id) if b is not None else None
    if b is None or room is None or not (ctx.access.can_view_room(room) or bsvc.is_owner(ctx.access, b)):
        raise ActionRefused(404, "not_found", "Rezervasyon bulunamadı.", "Booking not found.")
    if not bsvc.is_owner(ctx.access, b):
        # owner default: the helper cancels only the person's own bookings (RA-03), whatever their role allows
        raise ActionRefused(
            403,
            "not_cancelable",
            "Yardımcı yalnızca kendi rezervasyonlarınızı iptal eder.",
            "The helper only cancels your own bookings.",
        )
    if b.series_id:
        raise ActionRefused(
            422,
            "recurring",
            "Tekrarlayan rezervasyonlar Rezervasyonlarım sayfasından iptal edilir.",
            "Recurring bookings are cancelled on the My bookings page.",
        )
    if b.status != BOOKED:
        raise ActionRefused(
            409, "already_cancelled", TR_BY_CODE["already_cancelled"], "The booking is already cancelled."
        )
    if not await bsvc.can_cancel(ctx.session, ctx.access, b, room):
        raise ActionRefused(403, "not_cancelable", TR_BY_CODE["not_cancelable"], "You may not cancel this booking.")
    period = await ctx.session.get(BookingPeriod, b.period_id)
    tr_when, en_when = _when(b.date, period) if period else day_label(b.date)
    return Preview(
        action="cancel_my_booking",
        risk="R1",
        args={"booking_id": b.id},
        facts={"booking": b.id, "status": b.status, "date": b.date.isoformat(), "period": b.period_id},
        lines=[line("Salon", "Room", room.display_name), line("Zaman", "When", tr_when, en_when)],
        button=cards.txt(f"İptal et: {room.display_name} · {tr_when}", f"Cancel: {room.display_name} · {en_when}"),
        title=cards.txt("Rezervasyonu iptal et", "Cancel the booking"),
        undoable=True,
        danger=True,
    )


@executes("cancel_my_booking")
async def execute_cancel(ctx: Ctx, a: CancelArgs, p: Preview) -> cf.Executed:
    b = await ctx.session.get(Booking, a.booking_id)
    assert b is not None
    d, period_id = b.date, b.period_id
    try:
        await bsvc.cancel(ctx.session, ctx.access, a.booking_id, "one", None)
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    period = await ctx.session.get(BookingPeriod, period_id)
    return cf.Executed(
        entity=s.Entity(kind="booking", id=a.booking_id, feature_id="my_bookings"),
        message=cards.txt("Rezervasyon iptal edildi.", "Booking cancelled."),
        undo_event_id=await _booking_audit_event(ctx, "booking.cancel", a.booking_id),
        undo_until=await _undo_until(ctx, d, period),
        follow_ups=[
            s.FollowUp(
                label=cards.txt("Boş salon bul", "Find a free room"),
                action="find_free_rooms",
                args={"date": d.isoformat()},
            )
        ],
    )


# -------------------------------------------------------------------------------------- withdraw_my_request


class RequestArgs(Args):
    request_id: Annotated[int, Field(ge=0, description="id of the user's own pending request; 0 = not chosen")] = 0


@write(
    name="withdraw_my_request",
    permission=(),
    args=RequestArgs,
    summary_tr="Talebimi geri çek",
    summary_en="Withdraw my request",
    description="Prepare withdrawing ONE of the user's own pending booking requests. The user confirms it.",
    route="POST /approvals/{request_id}/withdraw",
    risk="R1",
    route_args={"request_id": "request_id"},
)
async def preview_withdraw(ctx: Ctx, a: RequestArgs) -> Preview | s.CardBase:
    if not a.request_id:
        return await REGISTRY["my_requests_status"].run(ctx, REGISTRY["my_requests_status"].args())
    req = await ctx.session.get(ApprovalRequest, a.request_id)
    if req is None or req.requested_by != ctx.access.user_id:
        raise ActionRefused(404, "not_found", "Talep bulunamadı.", "Request not found.")
    if req.status != PENDING:
        raise ActionRefused(
            409, "not_pending", "Bu talep artık beklemiyor; geri çekilemez.", "This request is no longer pending."
        )
    room = await ctx.session.get(Room, req.room_id)
    rows = await asvc.bookings_of(ctx.session, req)
    first = rows[0] if rows else None
    period = await ctx.session.get(BookingPeriod, first.period_id) if first else None
    tr_when, en_when = _when(first.date, period) if first and period else ("—", "—")
    name = room.display_name if room else ""
    return Preview(
        action="withdraw_my_request",
        risk="R1",
        args={"request_id": req.id},
        facts={"request": req.id, "status": req.status, "step": req.step},
        lines=[line("Salon", "Room", name), line("Zaman", "When", tr_when, en_when)],
        button=cards.txt(f"Geri çek: {name} · {tr_when}", f"Withdraw: {name} · {en_when}"),
        title=cards.txt("Talebi geri çek", "Withdraw the request"),
        undoable=False,
        danger=True,
        warnings=[
            cards.txt(
                "Bu işlem geri alınamaz; gerekirse yeni bir talep gönderin.",
                "This cannot be undone; send a new request if needed.",
            )
        ],
    )


@executes("withdraw_my_request")
async def execute_withdraw(ctx: Ctx, a: RequestArgs, p: Preview) -> cf.Executed:
    try:
        await asvc.withdraw(ctx.session, ctx.access, a.request_id)
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    return cf.Executed(
        entity=s.Entity(kind="approval_request", id=a.request_id, feature_id="my_requests"),
        message=cards.txt("Talebiniz geri çekildi.", "Your request was withdrawn."),
    )


# ------------------------------------------------------------------------------------------ decide_approval


class DecideArgs(Args):
    request_id: Annotated[
        int, Field(ge=0, description="id of a pending request from approvals_inbox; 0 = not chosen")
    ] = 0
    decision: Literal["approve", "reject"] = "approve"
    reason_code: Literal["", "room_unavailable", "capacity", "policy", "other"] = ""
    reason: Annotated[str, Field(max_length=1000, description="why, for a rejection; '' = none")] = ""


@write(
    name="decide_approval",
    permission=(asvc.DECIDE,),
    args=DecideArgs,
    summary_tr="Talebi onayla ya da reddet",
    summary_en="Approve or reject a request",
    description="Prepare approving or rejecting ONE pending booking request the user is the approver of. A "
    "rejection needs a reason code or a reason. The user confirms it on the card.",
    route="POST /approvals/{request_id}/decide",
    risk="R2",
    route_args={"request_id": "request_id", "decision": "decision", "reason_code": "reason_code", "reason": "reason"},
)
async def preview_decide(ctx: Ctx, a: DecideArgs) -> Preview | s.CardBase:
    if not a.request_id:
        return await REGISTRY["approvals_inbox"].run(ctx, REGISTRY["approvals_inbox"].args())
    req = await ctx.session.get(ApprovalRequest, a.request_id)
    room = await ctx.session.get(Room, req.room_id) if req is not None else None
    if req is None or room is None:
        raise ActionRefused(404, "not_found", "Talep bulunamadı.", "Request not found.")
    if req.status != PENDING:
        raise ActionRefused(409, "not_pending", "Bu talep artık beklemiyor.", "This request is no longer pending.")
    snap = req.rule_snapshot or asvc.rule_snapshot(None)
    approvers = await asvc.step_approvers(ctx.session, room, snap, req.step)
    if ctx.access.user not in approvers:
        raise ActionRefused(
            403, "not_an_approver", "Bu adımın onaycısı değilsiniz.", "You are not an approver of this step."
        )
    others = [u for u in approvers if u.id != ctx.access.user_id]
    if (
        a.decision == "approve"
        and req.requested_by == ctx.access.user_id
        and not snap.get("allow_self_approve")
        and others
    ):
        raise ActionRefused(
            403, "self_approval", "Kendi talebinizi onaylayamazsınız.", "You cannot approve your own request."
        )
    if a.decision == "reject":
        try:
            asvc.check_reason(a.reason_code or None, a.reason or None)
        except bsvc.BookingError:
            return s.FormCard(
                id=cards.new_id(),
                action="decide_approval",
                title=cards.txt("Reddetme gerekçesi", "Reason for rejecting"),
                risk="R2",
                missing=["reason_code"],
                message=cards.txt("Reddetmek için bir gerekçe seçin ya da yazın.", "Pick or write a reason to reject."),
                fields=[
                    s.FormField(
                        name="request_id",
                        label=cards.txt("Talep", "Request"),
                        kind="number",
                        required=True,
                        value=req.id,
                    ),
                    s.FormField(
                        name="decision",
                        label=cards.txt("Karar", "Decision"),
                        kind="select",
                        required=True,
                        value="reject",
                        options=[s.Option(value="reject", label=cards.txt("Reddet", "Reject"))],
                    ),
                    s.FormField(
                        name="reason_code",
                        label=cards.txt("Gerekçe", "Reason"),
                        kind="select",
                        required=True,
                        options=[
                            s.Option(value=k, label=cards.txt(tr, en)) for k, (tr, en) in asvc.REASON_CODES.items()
                        ],
                        options_source="reasons",
                    ),
                    s.FormField(
                        name="reason",
                        label=cards.txt("Açıklama", "Note"),
                        kind="textarea",
                        required=False,
                        max_length=1000,
                    ),
                ],
            )
    requester = await ctx.session.get(User, req.requested_by) if req.requested_by else None
    who = audit.user_label(requester) or ""
    rows = await asvc.bookings_of(ctx.session, req)
    first = rows[0] if rows else None
    period = await ctx.session.get(BookingPeriod, first.period_id) if first else None
    tr_when, en_when = _when(first.date, period) if first and period else ("—", "—")
    approve = a.decision == "approve"
    lines = [
        line("Salon", "Room", room.display_name),
        line("Zaman", "When", tr_when, en_when),
        line("Talep eden", "Requested by", who),
        line("Karar", "Decision", "Onay" if approve else "Ret", "Approve" if approve else "Reject"),
    ]
    if not approve:
        code_tr, code_en = asvc.REASON_CODES.get(a.reason_code, ("", ""))
        lines.append(
            line(
                "Gerekçe",
                "Reason",
                " · ".join(x for x in (code_tr, a.reason) if x),
                " · ".join(x for x in (code_en, a.reason) if x),
            )
        )
    return Preview(
        action="decide_approval",
        risk="R2",
        args={"request_id": req.id, "decision": a.decision, "reason_code": a.reason_code, "reason": a.reason},
        facts={
            "request": req.id,
            "status": req.status,
            "step": req.step,
            "decision": a.decision,
            "reason_code": a.reason_code,
            "reason": a.reason,
        },
        lines=lines,
        button=cards.txt(
            f"{'Onayla' if approve else 'Reddet'}: {room.display_name} · {tr_when}",
            f"{'Approve' if approve else 'Reject'}: {room.display_name} · {en_when}",
        ),
        title=cards.txt("Talep kararı", "Request decision"),
        affected=cards.txt(f"{who} kişisine bildirim gider.", f"{who} is notified."),
        undoable=False,
        danger=not approve,
    )


@executes("decide_approval")
async def execute_decide(ctx: Ctx, a: DecideArgs, p: Preview) -> cf.Executed:
    try:
        await asvc.decide(
            ctx.session,
            ctx.access,
            a.request_id,
            a.decision,
            (a.reason or None) if a.decision == "reject" else None,
            None,
            None,
            reason_code=a.reason_code or None,
        )
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    approve = a.decision == "approve"
    return cf.Executed(
        entity=s.Entity(kind="approval_request", id=a.request_id, feature_id="approvals"),
        message=cards.txt(
            "Onaylandı." if approve else "Reddedildi; kişiye gerekçe gönderildi.",
            "Approved." if approve else "Rejected; the reason was sent.",
        ),
        follow_ups=[s.FollowUp(label=cards.txt("Bekleyen talepler", "Pending requests"), action="approvals_inbox")],
    )


# ---------------------------------------------------------------------------------- undo_last_helper_action


class NoArgs(Args):
    pass


@write(
    name="undo_last_helper_action",
    permission=(),
    args=NoArgs,
    summary_tr="Son yaptığımı geri al",
    summary_en="Undo my last helper action",
    description="Prepare undoing the user's last booking or cancellation made through the helper.",
    route="POST /audit/{event_id}/undo",
    risk="R1",
)
async def preview_undo(ctx: Ctx, _a: NoArgs) -> Preview | s.CardBase:
    from app.services import bookings_undo

    inv = await cf.last_undoable(ctx.session, ctx.access)
    if inv is None or inv.undo_event_id is None:
        raise ActionRefused(
            404, "nothing_to_undo", "Geri alınacak bir yardımcı işlemi yok.", "There is no helper action to undo."
        )
    try:
        ev, rows = await bookings_undo.check(ctx.session, ctx.access, inv.undo_event_id)
    except bsvc.BookingError as exc:
        raise refusal(exc) from exc
    b = rows[0]
    room = await ctx.session.get(Room, b.room_id)
    period = await ctx.session.get(BookingPeriod, b.period_id)
    tr_when, en_when = _when(b.date, period) if period else day_label(b.date)
    name = room.display_name if room else ""
    what_tr, what_en = (
        ("Rezervasyonu iptal eder", "Cancels the booking")
        if ev.action == "booking.create"
        else ("Rezervasyonu yeniden yapar", "Books it again")
    )
    return Preview(
        action="undo_last_helper_action",
        risk="R1",
        args={},
        facts={"invocation": inv.id, "event": inv.undo_event_id},
        lines=[
            line("Salon", "Room", name),
            line("Zaman", "When", tr_when, en_when),
            line("Geri alma", "Undo", what_tr, what_en),
        ],
        button=cards.txt(f"Geri al: {name} · {tr_when}", f"Undo: {name} · {en_when}"),
        title=cards.txt("Son işlemi geri al", "Undo the last action"),
        undoable=False,
    )


@executes("undo_last_helper_action")
async def execute_undo(ctx: Ctx, _a: NoArgs, p: Preview) -> cf.Executed:
    from app.models.helper import HelperActionInvocation

    inv = await ctx.session.get(HelperActionInvocation, int(p.facts["invocation"]))
    if inv is None:
        raise ActionRefused(404, "nothing_to_undo", "Geri alınacak bir işlem yok.", "There is nothing to undo.")
    await cf.undo_invocation(ctx.session, ctx.access, inv, record=False)
    return cf.Executed(
        entity=s.Entity(kind="booking", id=inv.entity_id, feature_id="my_bookings") if inv.entity_id else None,
        message=cards.txt("Geri alındı.", "Undone."),
        undo_of=inv.id,
    )


__all__ = ["WRITES", "Preview", "WriteSpec", "refusal"]
