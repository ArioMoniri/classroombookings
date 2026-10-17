"""RF-11 (audit 2026-10-17 A6): the senders of the e-mail kinds that used to be preview-only.

Every message goes through :func:`app.services.notify_dispatch.dispatch`, so the recipient's channel preferences
(Profil › Bildirimler), the delivery ledger (``notification_deliveries``: one occurrence reaches a person once per
channel) and the e-mail outbox (``notification_outbox``, sent after the commit by the integrations worker) apply as
for every other notice. The words are the kind's shipped template (``app.emails.strings``, admin overrides of set
``email`` first) in the reader's language; the in-app bell shows the same subject and text.

==================  =====================  ==========================================================================
event               outbox kind            sent when / to
==================  =====================  ==========================================================================
booking.reminder    booking_reminder       :func:`send_due_reminders` (worker ``app.workers.reminders``, every 5 min):
                                           a booking starts within ``bookings.reminder_lead_hours`` (admin setting,
                                           default 24, 0 = off) and existed before that window opened; to its owner
series.created      series_created         a recurring series is created (legacy hook ``series.created``); to the
                                           series' owner (``by=self`` when they made it themselves)
series.changed      series_changed         instances of a series are edited with scope ``future`` / ``all``; to the
                                           owners (not the person who edited) and to the approvers who approved the
                                           series (``to=approver``)
approval.submitted  approval_submitted     a request is opened (first step); a receipt to the person who submitted it
calendar.consent    calendar_consent       the KVKK ``calendar_sync`` consent is given or withdrawn (``app.services
                                           .kvkk.grant`` / ``withdraw``; ``scope=consent_on`` / ``consent_off``)
new_device.sign_in  new_device_sign_in     a sign-in from a device not seen before: user-agent family (browser + OS,
                                           no versions) plus the client network (/24, /48 for IPv6), stored only as
                                           an HMAC in the user setting ``known_devices``; the very first device of an
                                           account is recorded silently; off for the whole organisation with
                                           ``org.new_device_sign_in_mail``
==================  =====================  ==========================================================================
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ApprovalDecision, ApprovalRequest, Booking, BookingPeriod, BookingSeries, NotificationDelivery
from app.models import User
from app.models.booking import BOOKED
from app.models.catalog import Room
from app.services import audit
from app.services import bookings_events as legacy
from app.services import bookings_i18n
from app.services import events as domain
from app.services.bookings_settings import get_user_value, get_value, set_user_value

log = logging.getLogger(__name__)

#: session.info key: the request's User-Agent (bound by app.api.v1.audit.audit_context for every API request)
UA_KEY = "rf11.user_agent"
#: session.info key: a series move waiting for the booking.update event of the same edit
_MOVES_KEY = "rf11.series_moves"
#: user setting with the hashed known devices (JSON list, newest first)
DEVICES_KEY = "known_devices"
MAX_DEVICES = 20


# --------------------------------------------------------------------------------------------------
# Rendering + dispatch
# --------------------------------------------------------------------------------------------------


async def _lang(session: AsyncSession, user: User) -> str:
    from app.services import mail

    return await mail.resolve_locale(session, None, user)


async def send(
    session: AsyncSession,
    user: User,
    *,
    event: str,
    key: str,
    kind: str,
    link: str,
    locale: str | None = None,
    booking_id: int | None = None,
    request_id: int | None = None,
    data: dict[str, Any] | None = None,
    **ctx: Any,
) -> list[Any]:
    """Render ``kind`` (template mode, the reader's language) and hand it to the dispatcher as one notice."""
    from app.services import mail
    from app.services import notify_dispatch as nd

    lang = locale or await _lang(session, user)
    ctx.setdefault("name", mail.display_name(user))
    rendered = await mail.render_for(session, kind, lang, link=link, **ctx)
    return await nd.dispatch(
        session,
        user,
        nd.Notice(
            event=event,
            key=key,
            title=rendered.subject,
            body=rendered.content,
            link=link,
            booking_id=booking_id,
            request_id=request_id,
            data=data or {},
        ),
    )


def _delivered_any(out: Iterable[Any]) -> bool:
    return any(d.status not in ("off", "duplicate") for d in out)


async def _tz(session: AsyncSession) -> ZoneInfo:
    from app.services import settings_service

    try:
        return ZoneInfo(str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul"))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Istanbul")


def _period_label(fmt: bookings_i18n.Formatter, p: BookingPeriod | None) -> str:
    if p is None:
        return ""
    return f"{p.name} {fmt.time(p.time_start)}-{fmt.time(p.time_end)}".strip()


def _who(u: User | None) -> str:
    return audit.user_label(u) or "SmartSched"


# --------------------------------------------------------------------------------------------------
# 1. Booking reminders
# --------------------------------------------------------------------------------------------------


def reminder_key(b: Booking) -> str:
    return f"booking:{b.id}:reminder:{b.date.isoformat()}:{b.period_id}"


async def send_due_reminders(session: AsyncSession, now: datetime | None = None) -> int:
    """Remind the owners of the bookings that start within the lead time; the number of bookings reminded now.

    Idempotent: the ledger key names the booking, its date and period, so a second sweep (or a second worker) sends
    nothing, and a booking moved to another day is reminded again for the new day. A booking made inside the window
    (booked this afternoon for tomorrow morning) gets no reminder: its owner has just seen it."""
    from app.services import bookings as bsvc

    lead = int(await get_value(session, "bookings", "reminder_lead_hours") or 0)
    if lead <= 0:
        return 0
    now = now or await bsvc.now_local(session)
    horizon = now + timedelta(hours=lead)
    tz = await _tz(session)
    q = (
        select(Booking, BookingPeriod)
        .join(BookingPeriod, BookingPeriod.id == Booking.period_id)
        .where(
            Booking.status == BOOKED,
            Booking.user_id.is_not(None),
            Booking.date >= now.date(),
            Booking.date <= horizon.date(),
        )
        .order_by(Booking.date, Booking.start_period, Booking.id)
    )
    due: list[tuple[Booking, BookingPeriod]] = []
    for b, p in (await session.execute(q)).all():
        start = datetime.combine(b.date, p.time_start)
        if not (now < start <= horizon):
            continue
        if b.created_at is not None:
            made = b.created_at.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
            if made > start - timedelta(hours=lead):
                continue
        due.append((b, p))
    if not due:
        return 0
    keys = [reminder_key(b) for b, _ in due]
    done = set(
        (await session.execute(select(NotificationDelivery.event_key).where(NotificationDelivery.event_key.in_(keys))))
        .scalars()
        .all()
    )
    sent = 0
    for b, p in due:
        if reminder_key(b) in done:
            continue
        user = await session.get(User, b.user_id)
        room = await session.get(Room, b.room_id)
        if user is None or not user.is_active or room is None:
            continue
        lang = await _lang(session, user)
        fmt = await bookings_i18n.formatter(session, lang)
        days = (b.date - now.date()).days
        when = "hour_before" if days == 0 else ("day_before" if days == 1 else "later")
        out = await send(
            session,
            user,
            event="booking.reminder",
            key=reminder_key(b),
            kind="booking_reminder",
            link=f"/bookings/mine?booking={b.id}",
            locale=lang,
            booking_id=b.id,
            data={"booking_ids": [b.id], "room_id": b.room_id, "date": b.date.isoformat(), "lead_hours": lead},
            when=when,
            room=room.display_name,
            date=fmt.long(b.date),
            period=_period_label(fmt, p),
            start=fmt.time(p.time_start),
        )
        sent += _delivered_any(out)
    await session.flush()
    return sent


# --------------------------------------------------------------------------------------------------
# 2. Series created / changed
# --------------------------------------------------------------------------------------------------


async def _items(session: AsyncSession, rows: Sequence[Booking], lang: str) -> list[str]:
    from app.services.bookings_notify import _describe

    fmt = await bookings_i18n.formatter(session, lang)
    return [await _describe(session, b, fmt) for b in sorted(rows, key=lambda x: (x.date, x.start_period, x.id))]


async def series_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    """``series_created`` to the owner of a new series (legacy hook ``series.created``; the payload carries
    ``series_id``, ``booking_ids`` and ``actor_id``)."""
    sid = payload.get("series_id")
    series = await session.get(BookingSeries, sid) if sid else None
    rows = [b for b in [await session.get(Booking, i) for i in payload.get("booking_ids") or []] if b is not None]
    if series is None or not rows:
        return
    owner_id = series.user_id or rows[0].user_id
    owner = await session.get(User, owner_id) if owner_id else None
    if owner is None:
        return
    actor = await session.get(User, payload["actor_id"]) if payload.get("actor_id") else None
    room = await session.get(Room, series.room_id)
    period = await session.get(BookingPeriod, series.period_id)
    lang = await _lang(session, owner)
    first = min(rows, key=lambda b: (b.date, b.start_period))
    weekday = bookings_i18n.format_pattern(first.date, "EEEE", lang)
    pname = period.name if period else ""
    pattern = f"her {weekday} {pname}" if lang == "tr" else f"every {weekday} {pname}"
    await send(
        session,
        owner,
        event="series.created",
        key=f"series:{series.id}:created",
        kind="series_created",
        link=f"/bookings/mine?series={series.id}",
        locale=lang,
        booking_id=first.id,
        data={
            "series_id": series.id,
            "booking_ids": [b.id for b in rows],
            "room_id": series.room_id,
            "actor": {"id": actor.id, "name": _who(actor)} if actor else None,
        },
        by="self" if actor is not None and actor.id == owner.id else "other",
        who=_who(actor),
        room=room.display_name if room else str(series.room_id),
        pattern=pattern.strip(),
        count=len(rows),
        series_id=series.id,
        items=await _items(session, rows, lang),
    )


_CHANGE = {
    "tr": {
        "notes": 'not "{new}" oldu',
        "notes_removed": "not kaldırıldı",
        "room_id": "derslik {old} yerine {new}",
        "date": "tarih {old} yerine {new}",
        "period_id": "saat {old} yerine {new}",
        "department_id": "bölüm değişti",
        "user_id": "rezervasyon sahibi artık {new}",
    },
    "en": {
        "notes": 'the note is now "{new}"',
        "notes_removed": "the note was removed",
        "room_id": "room {new} instead of {old}",
        "date": "date {new} instead of {old}",
        "period_id": "time {new} instead of {old}",
        "department_id": "the department changed",
        "user_id": "the booking now belongs to {new}",
    },
}


async def _describe_change(session: AsyncSession, lang: str, items: Sequence[domain.Item]) -> str:
    """``saat P3 yerine P4 (11:00-11:50); not "Laboratuvar" oldu`` from the audited before / after snapshots."""
    words = _CHANGE["tr" if lang == "tr" else "en"]
    fmt = await bookings_i18n.formatter(session, lang)
    parts: list[str] = []
    for field in ("room_id", "date", "period_id", "notes", "department_id", "user_id"):
        pair = next(
            ((b or {}).get(field), (a or {}).get(field))
            for _id, b, a in items
            if (b or {}).get(field) != (a or {}).get(field)
        ) if any((b or {}).get(field) != (a or {}).get(field) for _id, b, a in items) else None
        if pair is None:
            continue
        old, new = pair
        if field == "notes":
            parts.append(words["notes"].format(new=bookings_i18n_clean(new)) if new else words["notes_removed"])
        elif field == "room_id":
            ro, rn = await session.get(Room, old) if old else None, await session.get(Room, new) if new else None
            parts.append(
                words[field].format(old=ro.display_name if ro else "-", new=rn.display_name if rn else "-")
            )
        elif field == "date":
            parts.append(words[field].format(old=_dmy(old), new=_dmy(new)))
        elif field == "period_id":
            po, pn = await session.get(BookingPeriod, old) if old else None, await session.get(BookingPeriod, new)
            new_label = f"{pn.name} ({fmt.time(pn.time_start)}-{fmt.time(pn.time_end)})" if pn else "-"
            parts.append(words[field].format(old=po.name if po else "-", new=new_label))
        elif field == "user_id":
            u = await session.get(User, new) if new else None
            parts.append(words[field].format(new=_who(u) if u else "-"))
        else:
            parts.append(words[field])
    return "; ".join(parts)


def bookings_i18n_clean(value: Any) -> str:
    from app.emails import clean

    return " ".join(clean(value).split())


def _dmy(value: Any) -> str:
    text = str(value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}.{text[5:7]}.{text[0:4]}"
    return text or "-"


async def _series_approvers(session: AsyncSession, series_id: int) -> list[int]:
    q = (
        select(ApprovalDecision.approver_user_id)
        .join(ApprovalRequest, ApprovalRequest.id == ApprovalDecision.request_id)
        .where(
            ApprovalRequest.series_id == series_id,
            ApprovalRequest.status == "APPROVED",
            ApprovalDecision.decision == "APPROVED",
            ApprovalDecision.approver_user_id.is_not(None),
        )
    )
    return sorted({int(x) for x in (await session.execute(q)).scalars() if x is not None})


async def _on_booking_change(session: AsyncSession, ev: domain.DomainEvent) -> None:
    """``booking.update`` / ``booking.move`` with scope ``future`` / ``all``: one ``series_changed`` per series and
    recipient. An edit that moves one instance and changes the others publishes ``booking.move`` first and
    ``booking.update`` second (``app.services.bookings.update``): the move waits for the update."""
    scope = ev.payload.get("scope")
    if scope not in ("future", "all"):
        return
    ids = tuple(sorted(int(i) for i in ev.payload.get("booking_ids") or []))
    moves: dict[tuple[int, ...], list[domain.Item]] = session.info.setdefault(_MOVES_KEY, {})
    if ev.action == "booking.move" and len(ids) > 1:
        moves[ids] = list(ev.items)
        return
    items = [*moves.pop(ids, []), *ev.items]
    by_series: dict[int, list[domain.Item]] = {}
    for item in items:
        after = item[2] or {}
        sid = after.get("series_id") or (item[1] or {}).get("series_id")
        if sid:
            by_series.setdefault(int(sid), []).append(item)
    actor = await session.get(User, ev.actor_id) if ev.actor_id else None
    for sid, its in by_series.items():
        changed = [it for it in its if (it[1] or {}) != (it[2] or {})]
        if not changed:
            continue
        rows = [b for b in [await session.get(Booking, int(it[0])) for it in changed] if b is not None]
        if not rows:
            continue
        owners: list[int] = []
        for it in changed:
            for snap in (it[2], it[1]):
                uid = (snap or {}).get("user_id")
                if uid and uid not in owners:
                    owners.append(int(uid))
        approvers = [u for u in await _series_approvers(session, sid) if u not in owners]
        room = await session.get(Room, rows[0].room_id)
        for uid, to in [*((u, "owner") for u in owners), *((u, "approver") for u in approvers)]:
            if actor is not None and uid == actor.id:
                continue
            user = await session.get(User, uid)
            if user is None or not user.is_active:
                continue
            lang = await _lang(session, user)
            await send(
                session,
                user,
                event="series.changed",
                key=f"series:{sid}:changed:{ev.audit_id or ':'.join(map(str, ids))}",
                kind="series_changed",
                link=f"/bookings/mine?series={sid}" if to == "owner" else f"/bookings?series={sid}",
                locale=lang,
                booking_id=rows[0].id,
                data={
                    "series_id": sid,
                    "booking_ids": [b.id for b in rows],
                    "scope": scope,
                    "to": to,
                    "actor": {"id": actor.id, "name": _who(actor)} if actor else None,
                },
                to=to,
                who=_who(actor),
                room=room.display_name if room else str(rows[0].room_id),
                series_id=sid,
                change=await _describe_change(session, lang, changed),
                items=await _items(session, rows, lang),
            )


# --------------------------------------------------------------------------------------------------
# 3. Approval submitted (receipt)
# --------------------------------------------------------------------------------------------------


async def approval_submitted(session: AsyncSession, entries: Sequence[tuple[Any, Any, list[Booking], User]]) -> None:
    """A receipt for one submission (one request, or the requests of one multi-booking) to the person who submitted
    it; called by :func:`app.services.approvals.flush_approver_notices` for first-step notices."""
    from app.services import approvals

    if not entries:
        return
    entries = sorted(entries, key=lambda e: (min((b.date, b.start_period) for b in e[2]), e[0].id))
    req, _room, _rows, requester = entries[0]
    if requester is None or not requester.is_active:
        return
    by_room: dict[int, tuple[Room, list[Booking]]] = {}
    for _r, rm, rows, _u in entries:
        by_room.setdefault(rm.id, (rm, []))[1].extend(rows)
    what = "; ".join([(await approvals.summary(session, rm, rows))[0] for rm, rows in by_room.values()])
    ids = sorted(e[0].id for e in entries)
    first = min((b for e in entries for b in e[2]), key=lambda b: (b.date, b.start_period))
    gid = approvals._group_of(req, first)
    if len(ids) > 1 and gid is not None:
        digest = hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:16]
        key = f"approval_group:{gid}:submitted:{digest}"
    else:
        key = f"approval_request:{req.id}:submitted"
    lang = await _lang(session, requester)
    held = first.held_until
    fmt = await bookings_i18n.formatter(session, lang)
    ctx: dict[str, Any] = {"what": what}
    if held is not None:
        ctx.update(hold="held", held_until=f"{held:%d.%m.%Y} {fmt.time(held.time())}")
    await send(
        session,
        requester,
        event="approval.submitted",
        key=key,
        kind="approval_submitted",
        link=f"/bookings/mine?request={req.id}",
        locale=lang,
        booking_id=first.id,
        request_id=req.id,
        data={
            "request_id": req.id,
            "request_ids": ids,
            "series_id": req.series_id,
            "group_id": gid,
            "decision": "submitted",
            "booking_ids": [b.id for e in entries for b in e[2]],
        },
        **ctx,
    )


# --------------------------------------------------------------------------------------------------
# 4. Calendar-sync consent
# --------------------------------------------------------------------------------------------------


async def calendar_consent(session: AsyncSession, user: User, *, granted: bool, consent_id: int) -> None:
    """The KVKK ``calendar_sync`` consent was given (``granted``) or withdrawn (``app.services.kvkk``)."""
    state = "consent_on" if granted else "consent_off"
    await send(
        session,
        user,
        event="calendar.consent",
        key=f"consent:{consent_id}:{'granted' if granted else 'withdrawn'}",
        kind="calendar_consent",
        link="/profile#privacy",
        data={"purpose": "calendar_sync", "consent_id": consent_id, "granted": granted},
        scope=state,
    )


# --------------------------------------------------------------------------------------------------
# 5. New-device sign-in
# --------------------------------------------------------------------------------------------------


def bind_user_agent(session: AsyncSession, user_agent: str | None) -> None:
    """Remember the request's User-Agent on its DB session (the sign-in hook reads it with the hashed network)."""
    session.info[UA_KEY] = (user_agent or "")[:512]


def device_family(user_agent: str | None) -> tuple[str, str]:
    """``(browser, os)`` of a User-Agent, without versions (a browser update is the same device)."""
    s = user_agent or ""
    if "Edg/" in s or "Edge/" in s or "EdgA/" in s or "EdgiOS/" in s:
        browser = "Edge"
    elif "OPR/" in s or "Opera" in s:
        browser = "Opera"
    elif "Firefox/" in s or "FxiOS/" in s:
        browser = "Firefox"
    elif "SamsungBrowser/" in s:
        browser = "Samsung Internet"
    elif "Chrome/" in s or "CriOS/" in s or "Chromium/" in s:
        browser = "Chrome"
    elif "Safari/" in s and ("Version/" in s or "Mobile/" in s):
        browser = "Safari"
    else:
        browser = ""
    if "iPhone" in s:
        system = "iPhone"
    elif "iPad" in s:
        system = "iPad"
    elif "Android" in s:
        system = "Android"
    elif "Windows" in s:
        system = "Windows"
    elif "CrOS" in s:
        system = "ChromeOS"
    elif "Macintosh" in s or "Mac OS X" in s:
        system = "macOS"
    elif "Linux" in s:
        system = "Linux"
    else:
        system = ""
    return browser, system


def device_label(user_agent: str | None, lang: str) -> str:
    browser, system = device_family(user_agent)
    unknown_b = "bilinmeyen tarayıcı" if lang == "tr" else "unknown browser"
    unknown_s = "bilinmeyen cihaz" if lang == "tr" else "unknown device"
    return f"{browser or unknown_b}, {system or unknown_s}"


def device_hash(user_agent: str | None, network_hash: str | None) -> str:
    browser, system = device_family(user_agent)
    raw = f"{browser}|{system}|{network_hash or '-'}"
    return hmac.new(get_settings().app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]


def _known(raw: str | None) -> list[dict[str, str]]:
    try:
        data = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict) and isinstance(d.get("h"), str)] if isinstance(data, list) else []


async def _on_logged_in(session: AsyncSession, payload: dict[str, Any]) -> None:
    if UA_KEY not in session.info:
        return  # not an HTTP sign-in (no request context to compare)
    user = await session.get(User, payload.get("user_id")) if payload.get("user_id") else None
    if user is None:
        return
    ua = session.info.get(UA_KEY) or ""
    ctx = audit.context(session)
    h = device_hash(ua, ctx.ip_hash if ctx else None)
    known = _known(await get_user_value(session, user.id, DEVICES_KEY))
    is_new = all(d["h"] != h for d in known)
    first_device = not known
    from app.models.base import utcnow

    now = utcnow()
    known = [{"h": h, "seen": now.isoformat(timespec="seconds")}, *(d for d in known if d["h"] != h)][:MAX_DEVICES]
    await set_user_value(session, user.id, DEVICES_KEY, json.dumps(known, separators=(",", ":")))
    if not is_new or first_device or not user.email:
        return
    if not await get_value(session, "org", "new_device_sign_in_mail"):
        return
    lang = await _lang(session, user)
    fmt = await bookings_i18n.formatter(session, lang)
    local = now.replace(tzinfo=UTC).astimezone(await _tz(session)).replace(tzinfo=None)
    await send(
        session,
        user,
        event="new_device.sign_in",
        key=f"new_device:{user.id}:{h}:{now:%Y-%m-%d}",
        kind="new_device_sign_in",
        link="/profile#security",
        locale=lang,
        data={"auth_method": payload.get("auth_method"), "device": device_label(ua, "en")},
        when=f"{fmt.long(local.date())} {fmt.time(local.time())}",
        device=device_label(ua, lang),
    )


legacy.on("user.logged_in", _on_logged_in)
domain.subscribe("booking.update", _on_booking_change)
domain.subscribe("booking.move", _on_booking_change)
