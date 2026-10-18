"""Calendar subscription feeds (docs/product/calendar-sync-api.md §2).

Calendar apps (Google, Outlook, Apple, Thunderbird) cannot send our JWT, so a feed URL carries a per-user secret
token: ``/api/v1/calendar/feeds/{token}/mine.ics`` (and ``room/{id}``, ``department/{id}``, ``room-group/{id}``).
Only the token's SHA-256 is stored; a user may hold several links (one per app) and revoke each, or reset all.

A feed shows only what the token's owner may see: rooms with ``room.view`` (role or room ACL) or the owner's own
bookings; notes and user names only with CRBS ``view_other_notes`` / ``view_other_users``. Every event carries a
stable UID (``booking-{id}@smartsched``, the older feeds' UID), ``SEQUENCE`` and ``LAST-MODIFIED`` from
``calendar_event_revisions`` (bumped when the booking's calendar content changes), and cancelled bookings stay as
``STATUS:CANCELLED`` for a grace period so subscribed calendars drop them.

The organisation's KVKK switch (``integrations.calendar_sync_enabled``) turns every token feed into a 404.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.importers import normalize as n
from app.models import (
    Booking,
    BookingPeriod,
    CalendarEventRevision,
    CalendarFeedToken,
    Program,
    RoomGroup,
    User,
)
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED, PENDING
from app.models.catalog import Room
from app.services import bookings as booking_svc
from app.services import settings_service
from app.services.bookings_collation import tr_sort_key
from app.services.bookings_export import IcsEvent, render_calendar
from app.services.bookings_perms import Access
from app.services.bookings_settings import get_group, get_value

TOKEN_PREFIX = "sst_"
MAX_TOKENS_PER_USER = 10
#: ``last_used_at`` is written at most this often (calendar apps poll; a write per poll is wasteful)
LAST_USED_RESOLUTION = timedelta(hours=1)
FEED_KINDS = ("mine", "room", "department", "room_group")
#: statuses shown as cancelled in the owner's feed (they may have been shown as tentative before)
ENDED = frozenset({CANCELLED, "REJECTED", "EXPIRED", "WITHDRAWN"})


class FeedNotFound(Exception):
    """Unknown / revoked token, disabled user, invisible or unknown room / department / group, or sync off."""


# --------------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------------


async def sync_enabled(session: AsyncSession) -> bool:
    return bool(await get_value(session, "integrations", "calendar_sync_enabled"))


async def feed_switches(session: AsyncSession) -> dict[str, bool]:
    """In one query (the CAL-05 304 path): ``enabled`` (the KVKK switch with its sign-off, :func:`sync_enabled`) and
    the admin's switch per export scope (``my_classes`` / ``department_classes`` / ``my_bookings`` /
    ``my_duties``)."""
    from app.models import Setting
    from app.services import bookings_settings as bs

    group, key, signoff = bs.SIGNOFF_GATED
    switch_keys = {"my_classes": "export_my_classes", "department_classes": "export_department_classes",
                   "my_bookings": "export_my_bookings", "my_duties": "export_my_duties"}  # fmt: skip
    names = [f"{group}.{key}", f"{group}.{signoff}", *(f"{group}.{k}" for k in switch_keys.values())]
    rows = {r.key: r.value for r in (await session.execute(select(Setting).where(Setting.key.in_(names)))).scalars()}
    specs = bs.GROUPS[group]
    on = bs._decode(specs[key], rows.get(names[0]))
    out = {"enabled": bool(on) and bs.kvkk_signed(bs._decode(specs[signoff], rows.get(names[1])))}
    for kind, k in switch_keys.items():
        out[kind] = bool(bs._decode(specs[k], rows.get(f"{group}.{k}")))
    return out


def clean_public_url(value: Any) -> str:
    """``https://host[:port]`` (or ``http://localhost…`` for a local stack); no path, query or user info. Raises
    ``ValueError``. NBSP / spaces around the value are trimmed."""
    text = n.clean_text(value) or ""
    if not text:
        return ""
    text = text.rstrip("/")
    parts = urlsplit(text)
    local = (parts.hostname or "") in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not local):
        raise ValueError("public_url must be https:// (http:// only for localhost)")
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("public_url must be scheme://host[:port]")
    if parts.path not in ("", "/"):
        raise ValueError("public_url must not have a path")
    return f"{parts.scheme}://{parts.netloc}"


async def public_base(session: AsyncSession) -> tuple[str, str | None]:
    """(base URL without trailing slash or "", source ``setting`` / ``env`` / None)."""
    configured = await get_value(session, "integrations", "public_url")
    if configured:
        return str(configured).rstrip("/"), "setting"
    env = get_settings().public_url
    if env:
        try:
            cleaned = clean_public_url(env)
        except ValueError:
            cleaned = ""
        if cleaned:
            return cleaned, "env"
    return "", None


async def url_templates(session: AsyncSession, token: str = "{token}") -> dict[str, str]:
    base, _ = await public_base(session)
    root = f"{base}/api/v1/calendar/feeds/{token}"
    return {
        "mine": f"{root}/mine.ics",
        "room": f"{root}/room/{{id}}.ics",
        "department": f"{root}/department/{{id}}.ics",
        "room_group": f"{root}/room-group/{{id}}.ics",
    }


def subscribe_links(url: str, name: str = "SmartSched") -> dict[str, str]:
    """``webcal://`` (Apple, Outlook desktop, Thunderbird), Google "add by URL" and Outlook on the web."""
    webcal = url.replace("https://", "webcal://", 1).replace("http://", "webcal://", 1) if "://" in url else url
    return {
        "webcal": webcal,
        "google": "https://calendar.google.com/calendar/r?cid=" + quote(webcal, safe=""),
        "outlook": "https://outlook.office.com/calendar/0/addfromweb?url="
        + quote(url, safe="")
        + "&name="
        + quote(name, safe=""),
    }


# --------------------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_label(label: str | None) -> str | None:
    text = n.clean_text(label) if label is not None else None
    return text[:64] if text else None


def token_out(row: CalendarFeedToken) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "hint": row.hint,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


async def list_tokens(session: AsyncSession, user_id: int) -> list[CalendarFeedToken]:
    q = select(CalendarFeedToken).where(CalendarFeedToken.user_id == user_id).order_by(CalendarFeedToken.id)
    return list((await session.execute(q)).scalars())


async def require_sync_consent(session: AsyncSession, user: User) -> None:
    """While calendar sync is on (the institution's KVKK sign-off, :func:`sync_enabled`), a feed link or a push
    connection needs the person's active ``calendar_sync`` consent: raises the 409 ``consent_required``
    :class:`app.services.kvkk.KvkkError` otherwise (consent gates 2026-10-16). With sync off nothing is shared (every
    feed is a 404, connecting is refused), so a link can still be prepared."""
    if not await sync_enabled(session):
        return
    from app.services import kvkk

    await kvkk.require_consent(session, user, "calendar_sync")


async def consent_state(session: AsyncSession, user: User) -> dict[str, Any]:
    """``{purpose, required, granted}`` for ``GET /calendar/sync`` (the screen asks for the consent first)."""
    from app.services import kvkk

    return {
        "purpose": "calendar_sync",
        "required": await sync_enabled(session),
        "granted": await kvkk.has_consent(session, user.id, "calendar_sync"),
    }


async def create_token(session: AsyncSession, user: User, label: str | None = None) -> tuple[CalendarFeedToken, str]:
    """A new link (raises ``OverflowError`` above :data:`MAX_TOKENS_PER_USER`, the ``consent_required``
    :class:`~app.services.kvkk.KvkkError` without the ``calendar_sync`` consent while sync is on). The token is
    returned once."""
    await require_sync_consent(session, user)
    count = (
        await session.execute(select(func.count(CalendarFeedToken.id)).where(CalendarFeedToken.user_id == user.id))
    ).scalar_one()
    if count >= MAX_TOKENS_PER_USER:
        raise OverflowError(f"at most {MAX_TOKENS_PER_USER} calendar links per user; revoke one first")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = CalendarFeedToken(user_id=user.id, token_hash=hash_token(token), hint=token[-4:], label=_clean_label(label))
    session.add(row)
    await session.flush()
    return row, token


async def reset_tokens(session: AsyncSession, user: User, label: str | None = None) -> tuple[CalendarFeedToken, str]:
    """Revoke every link of ``user`` and create one new link (refused before anything is revoked without the
    consent, :func:`require_sync_consent`)."""
    await require_sync_consent(session, user)
    await session.execute(delete(CalendarFeedToken).where(CalendarFeedToken.user_id == user.id))
    return await create_token(session, user, label)


async def revoke_token(session: AsyncSession, user: User, token_id: int) -> bool:
    row = await session.get(CalendarFeedToken, token_id)
    if row is None or row.user_id != user.id:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def resolve_token(session: AsyncSession, token: str) -> User:
    """The active owner of ``token``; :class:`FeedNotFound` otherwise. Updates ``last_used_at`` (hourly)."""
    if not token or len(token) < 20 or len(token) > 128:
        raise FeedNotFound
    row = (
        await session.execute(select(CalendarFeedToken).where(CalendarFeedToken.token_hash == hash_token(token)))
    ).scalar_one_or_none()
    if row is None:
        raise FeedNotFound
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise FeedNotFound
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at > LAST_USED_RESOLUTION:
        row.last_used_at = now
        await session.commit()
    return user


# --------------------------------------------------------------------------------------------------
# Booking -> event content, revisions
# --------------------------------------------------------------------------------------------------


@dataclass
class EventView:
    """What a calendar shows of one booking for one viewer (shared with the push connectors)."""

    booking: Booking
    room: Room
    period: BookingPeriod
    start: datetime  # local, naive
    end: datetime
    summary: str
    location: str
    description: str | None
    status: str  # CONFIRMED | TENTATIVE | CANCELLED
    fingerprint: str  # of the full content (independent of the viewer)


def _display(u: User | None) -> str | None:
    return (u.full_name or u.username or u.email) if u is not None else None


def ical_status(b: Booking) -> str:
    if b.status == BOOKED:
        return "CONFIRMED"
    if b.status == PENDING:
        return "TENTATIVE"
    return "CANCELLED"


def changed_at(b: Booking) -> datetime:
    return max(x for x in (b.created_at, b.updated_at, b.cancelled_at) if x is not None)


class _Cache:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._rows: dict[tuple[type, int], Any] = {}

    async def get(self, model: type, key: int | None) -> Any:
        if key is None:
            return None
        if (model, key) not in self._rows:
            self._rows[(model, key)] = await self.session.get(model, key)
        return self._rows[(model, key)]


async def event_view(cache: _Cache, access: Access | None, b: Booking) -> EventView | None:
    """``access=None``: the booking's own user (push connectors write into the owner's calendar)."""
    room: Room | None = await cache.get(Room, b.room_id)
    period: BookingPeriod | None = await cache.get(BookingPeriod, b.period_id)
    if room is None or period is None:
        return None
    start = datetime.combine(b.date, period.time_start)
    end = datetime.combine(b.date, period.time_end)
    if end <= start:
        end = start + timedelta(minutes=40)
    user: User | None = await cache.get(User, b.user_id)
    dep: Program | None = await cache.get(Program, b.department_id)
    status = ical_status(b)
    full = {
        "status": status,
        "date": b.date.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "period": period.name,
        "room": room.display_name,
        "notes": b.notes,
        "user": [b.user_id, _display(user)],
        "department": [b.department_id, dep.name if dep else None],
    }
    fingerprint = hashlib.sha256(json.dumps(full, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    lines: list[str] = []
    owner_view = access is None
    if b.notes and (owner_view or booking_svc.can_view_notes(access, b, room)):  # type: ignore[arg-type]
        lines.append(b.notes)
    own = access is not None and booking_svc.is_owner(access, b)
    if user is not None and not owner_view and not own and booking_svc.can_view_user(access, b, room):  # type: ignore[arg-type]
        lines.append(_display(user) or "")
    if dep is not None:
        lines.append(dep.name)
    return EventView(
        booking=b,
        room=room,
        period=period,
        start=start,
        end=end,
        summary=f"{room.display_name} – {period.name}",
        location=room.display_name,
        description="\n".join(x for x in lines if x) or None,
        status=status,
        fingerprint=fingerprint,
    )


def merge_blocks(views: list[EventView]) -> list[EventView]:
    """A-12: the periods of one submission (same multi-booking, room, date and status, consecutive periods) are one
    VEVENT from the first period's start to the last one's end. The block keeps the first booking's UID; its
    fingerprint covers every member, so SEQUENCE moves when the block changes (a period rejected or cancelled
    leaves the block and appears on its own)."""
    out: list[EventView] = []
    members: list[list[EventView]] = []
    for v in sorted(views, key=lambda x: (x.booking.date, x.booking.room_id, x.booking.start_period, x.booking.id)):
        last = members[-1][-1] if members else None
        if (
            last is not None
            and v.booking.multi_booking_id is not None
            and v.booking.multi_booking_id == last.booking.multi_booking_id
            and v.booking.room_id == last.booking.room_id
            and v.booking.date == last.booking.date
            and v.status == last.status
            and v.booking.start_period == last.booking.end_period + 1
        ):
            members[-1].append(v)
        else:
            members.append([v])
    for block in members:
        if len(block) == 1:
            out.append(block[0])
            continue
        first, final = block[0], block[-1]
        notes = list(dict.fromkeys(x.description for x in block if x.description))
        out.append(
            EventView(
                booking=first.booking,
                room=first.room,
                period=first.period,
                start=first.start,
                end=final.end,
                summary=f"{first.room.display_name} – {first.period.name}–{final.period.name}",
                location=first.location,
                description="\n".join(notes) or None,
                status=first.status,
                fingerprint=hashlib.sha256("|".join(x.fingerprint for x in block).encode()).hexdigest(),
            )
        )
    return sorted(out, key=lambda x: (x.start, x.booking.id))


async def revisions(session: AsyncSession, views: list[EventView]) -> dict[int, tuple[int, datetime]]:
    """``booking_id -> (SEQUENCE, LAST-MODIFIED)``; a changed fingerprint bumps the sequence (persisted)."""
    out: dict[int, tuple[int, datetime]] = {}
    ids = [v.booking.id for v in views]
    rows: dict[int, CalendarEventRevision] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        q = select(CalendarEventRevision).where(CalendarEventRevision.booking_id.in_(chunk))
        rows.update({r.booking_id: r for r in (await session.execute(q)).scalars()})
    dirty = False
    now = utcnow()
    for v in views:
        rev = rows.get(v.booking.id)
        if rev is None:
            rev = CalendarEventRevision(
                booking_id=v.booking.id, fingerprint=v.fingerprint, sequence=0, last_modified=changed_at(v.booking)
            )
            session.add(rev)
            rows[v.booking.id] = rev
            dirty = True
        elif rev.fingerprint != v.fingerprint:
            rev.fingerprint, rev.sequence, rev.last_modified = v.fingerprint, rev.sequence + 1, now
            dirty = True
        out[v.booking.id] = (rev.sequence, rev.last_modified.replace(microsecond=0))
    if dirty:
        try:
            await session.commit()
        except IntegrityError:  # a concurrent poll stored the same revision first; the values above stand
            await session.rollback()
    return out


# --------------------------------------------------------------------------------------------------
# Feeds
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedScope:
    kind: str  # mine | room | department | room_group | my_classes | department_classes | my_duties
    id: int


@dataclass
class Feed:
    title: str
    filename: str
    text: str
    #: the newest LAST-MODIFIED in the feed (CAL-05 ``Last-Modified``)
    last_modified: datetime | None = None
    #: CAL-05: a version key computed before rendering; the ETag is derived from it when set
    version: str | None = None

    @property
    def etag(self) -> str:
        if self.version:
            return '"' + self.version[:32] + '"'
        return '"' + hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:32] + '"'


def _visible(access: Access, b: Booking, room: Room) -> bool:
    return access.can_view_room(room) or booking_svc.is_owner(access, b)


async def _visible_rooms_of(session: AsyncSession, access: Access, room_ids: list[int]) -> list[int]:
    if not room_ids:
        return []
    rooms = (await session.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()
    return [r.id for r in rooms if access.can_view_room(r)]


#: CAL-05: a department feed above this size is trimmed (feeds above ~1 MB are reported to fail in Google)
FEED_MAX_BYTES = 1_000_000
CLASS_KINDS = frozenset({"room", "room_group", "department", "my_classes", "department_classes"})
BOOKING_KINDS = frozenset({"mine", "room", "room_group", "department"})


def _rfc7986(title: str, source: str | None) -> list[str]:
    from app.core.export_safety import ics_text

    out = [f"NAME:{ics_text(title)}"]
    if source:
        out.append(f"SOURCE;VALUE=URI:{source}")
    return out


async def build_feed(
    session: AsyncSession,
    access: Access,
    scope: FeedScope,
    *,
    title: str | None = None,
    source: str | None = None,
    attachment: bool = False,
) -> Feed:
    """The calendar of ``scope`` as seen by ``access``; :class:`FeedNotFound` for what the user may not see.
    ``source``: the subscription URL (RFC 7986 ``SOURCE``); ``attachment``: a one-off file (CAL-04, no SOURCE)."""
    from app.services import calendar_classes as cc
    from app.services import calendar_duties as cd

    group = await get_group(session, "integrations")
    today: date = await booking_svc.today(session)
    since = today - timedelta(days=max(0, int(group["feed_past_days"] or 0)))
    grace_days = max(0, int(group["feed_cancelled_grace_days"] or 0))
    grace_cutoff = utcnow() - timedelta(days=grace_days)
    q = select(Booking).where(Booking.date >= since)
    include_pending = False
    room_filter: list[int] | None = None
    class_filter: cc.ScopeFilter | None = None
    own_instructors: list[int] = []
    duties = False
    if scope.kind == "mine":
        q = q.where(Booking.user_id == scope.id)
        include_pending = True
        name = _display(await session.get(User, scope.id)) or "SmartSched"
        default_title, filename = f"SmartSched – {name}", "bookings.ics"
    elif scope.kind == "room":
        room = await session.get(Room, scope.id)
        if room is None or not access.can_view_room(room):
            raise FeedNotFound
        q = q.where(Booking.room_id == room.id)
        default_title, filename = f"SmartSched – {room.display_name}", f"{room.code}.ics"
        class_filter = cc.ScopeFilter(room_ids=frozenset({room.id}), include_legacy=True)
    elif scope.kind in ("department", "department_classes"):
        dep = await session.get(Program, scope.id)
        # CAL-03: own department, a department of a section taught, or calendar.department_feed; every poll
        if dep is None or not await cc.department_allowed(session, access, dep.id):
            raise FeedNotFound
        q = q.where(Booking.department_id == dep.id)
        if scope.kind == "department":
            default_title, filename = f"SmartSched – {dep.name}", f"department-{dep.id}.ics"
        else:
            default_title = f"SmartSched – {dep.name} dersleri"
            filename = f"bolum-{cc.ascii_slug(dep.name)}.ics"
        class_filter = cc.ScopeFilter(program_id=dep.id, include_legacy=scope.kind == "department")
    elif scope.kind == "room_group":
        rg = await session.get(RoomGroup, scope.id)
        if rg is None:
            raise FeedNotFound
        members = list((await session.execute(select(Room.id).where(Room.room_group_id == rg.id))).scalars())
        room_filter = await _visible_rooms_of(session, access, members)
        if not room_filter:
            raise FeedNotFound
        q = q.where(Booking.room_id.in_(room_filter))
        default_title, filename = f"SmartSched – {rg.name}", f"room-group-{rg.id}.ics"
        class_filter = cc.ScopeFilter(room_ids=frozenset(room_filter), include_legacy=True)
    elif scope.kind == "my_classes":
        own_instructors = await cc.linked_instructor_ids(session, scope.id)
        if not own_instructors:
            raise FeedNotFound
        default_title, filename = "SmartSched – Derslerim", "derslerim.ics"
        class_filter = cc.ScopeFilter(instructor_ids=frozenset(own_instructors))
    elif scope.kind == "my_duties":  # CAL-13 "Sınav görevlerim"
        own_instructors = await cc.linked_instructor_ids(session, scope.id)
        if not own_instructors:
            raise FeedNotFound
        default_title, filename = "SmartSched – Sınav görevlerim", "sinav-gorevlerim.ics"
        duties = True
    else:
        raise FeedNotFound
    views: list[EventView] = []
    if scope.kind in BOOKING_KINDS:
        statuses = {BOOKED, CANCELLED} | ({PENDING} | ENDED if include_pending else set())
        q = q.where(Booking.status.in_(sorted(statuses))).order_by(Booking.date, Booking.start_period, Booking.id)
        cache = _Cache(session)
        for b in (await session.execute(q)).scalars():
            if b.status != BOOKED and b.status != PENDING and changed_at(b) < grace_cutoff:
                continue
            room_row: Room | None = await cache.get(Room, b.room_id)
            if room_row is None or not _visible(access, b, room_row):
                continue
            view = await event_view(cache, access, b)
            if view is not None:
                views.append(view)
        views = merge_blocks(views)
    revs = await revisions(session, views)
    events = [
        IcsEvent(
            uid=f"booking-{v.booking.id}@smartsched",
            start=v.start,
            end=v.end,
            summary=v.summary,
            location=v.location,
            description=v.description,
            status=v.status,
            sequence=revs[v.booking.id][0],
            last_modified=revs[v.booking.id][1],
        )
        for v in views
    ]
    if class_filter is not None:  # A-14 / CAL-01: the published classes
        rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
        base, _ = await public_base(session)
        ctx = cc.EventContext(
            fields=await cc.fields_setting(session), own_instructor_ids=frozenset(own_instructors), base_url=base
        )
        horizon = await cc.horizon_end(session, today)
        events += await cc.class_events(
            session,
            class_filter,
            since,
            horizon,
            grace_days=grace_days,
            ctx=ctx,
            room_visible=lambda rid: rid in rooms and access.can_view_room(rooms[rid]),
        )
        events.sort(key=lambda e: (e.start, e.uid))
    if duties:
        base, _ = await public_base(session)
        ctx = cc.EventContext(fields=await cc.fields_setting(session), base_url=base)
        events += await cd.duty_events(
            session, frozenset(own_instructors), since, cd.horizon(today), grace_days=grace_days, ctx=ctx
        )
        events.sort(key=lambda e: (e.start, e.uid))
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    final_title = title or default_title
    extra = _rfc7986(final_title, None if attachment else source)
    text = render_calendar(final_title, tz_name, events, extra=extra)
    if len(text.encode("utf-8")) > FEED_MAX_BYTES:
        text, events = _trim(final_title, tz_name, events, extra)
    newest = max((e.last_modified for e in events), default=None)
    return Feed(final_title, filename, text, last_modified=newest)


def _trim(title: str, tz_name: str, events: list[IcsEvent], extra: list[str]) -> tuple[str, list[IcsEvent]]:
    """CAL-05: keep a feed under :data:`FEED_MAX_BYTES`: drop the tombstones first, then the farthest events."""
    kept = [e for e in events if e.status != "CANCELLED"]
    text = render_calendar(title, tz_name, kept, extra=extra)
    while len(text.encode("utf-8")) > FEED_MAX_BYTES and kept:
        kept = kept[: max(0, int(len(kept) * 0.9))]
        text = render_calendar(title, tz_name, kept, extra=extra)
    return text, kept


CLASS_HORIZON_DAYS = 200  # kept for callers of the A-14 constant (app.services.calendar_classes owns it now)


async def feed_options(session: AsyncSession, access: Access) -> dict[str, Any]:
    rooms = await booking_svc.visible_rooms(session, access)
    group_ids = {r.room_group_id for r in rooms if r.room_group_id is not None}
    groups = (
        list((await session.execute(select(RoomGroup).where(RoomGroup.id.in_(group_ids)))).scalars())
        if group_ids
        else []
    )
    groups.sort(key=lambda g: (g.pos or 0, tr_sort_key(g.name), g.id))
    deps = list((await session.execute(select(Program))).scalars())
    deps.sort(key=lambda d: (tr_sort_key(d.name), d.id))
    return {
        "rooms": [
            {"id": r.id, "code": r.code, "name": r.display_name, "room_group_id": r.room_group_id} for r in rooms
        ],
        "room_groups": [{"id": g.id, "name": g.name} for g in groups],
        "departments": [{"id": d.id, "name": d.name} for d in deps],
    }


def etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    if header.strip() == "*":
        return True
    tags = [t.strip().removeprefix("W/") for t in header.split(",")]
    return etag in tags


# --------------------------------------------------------------------------------------------------
# CAL-03: scope-bound links ("subscriptions"), the department rule, per-scope approval
# --------------------------------------------------------------------------------------------------

#: the feed path each scope serves (a scope-bound link serves only this one)
SCOPE_FEED_KIND = {
    "my_classes": "my_classes",
    "department_classes": "department_classes",
    "my_bookings": "mine",
    "room": "room",
    "room_group": "room_group",
    "my_duties": "my_duties",
}
#: what a legacy (scope-less) link may open: its pre-CAL-03 paths
LEGACY_FEED_KINDS = frozenset({"mine", "room", "department", "room_group"})
#: the admin's on / off switch per scope (integrations.export_*); room feeds have none
SCOPE_SWITCH = {
    "my_classes": "export_my_classes",
    "department_classes": "export_department_classes",
    "my_bookings": "export_my_bookings",
    "my_duties": "export_my_duties",
}
_SHORT_DAYS = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
_SHORT_DAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def token_serves(row: CalendarFeedToken, kind: str, scope_id: int | None) -> bool:
    """A scope-bound link opens only its own feed; a legacy link its old paths."""
    if row.scope_kind is None:
        return kind in LEGACY_FEED_KINDS
    if SCOPE_FEED_KIND.get(row.scope_kind) != kind:
        return False
    if row.scope_kind in ("room", "room_group", "department_classes"):
        return scope_id is not None and row.scope_id == scope_id
    return True


def scoped_path(row: CalendarFeedToken) -> str | None:
    kind = row.scope_kind
    if kind == "my_classes":
        return "classes.ics"
    if kind == "department_classes":
        return f"department-classes/{row.scope_id}.ics"
    if kind == "my_bookings":
        return "mine.ics"
    if kind == "room":
        return f"room/{row.scope_id}.ics"
    if kind == "room_group":
        return f"room-group/{row.scope_id}.ics"
    if kind == "my_duties":
        return "duties.ics"
    return None


async def resolve_token_row(session: AsyncSession, token: str) -> tuple[CalendarFeedToken, User]:
    """The link row and its active owner; :class:`FeedNotFound` otherwise. Updates ``last_used_at`` (hourly)."""
    if not token or len(token) < 20 or len(token) > 128:
        raise FeedNotFound
    q = (
        select(CalendarFeedToken, User)
        .join(User, User.id == CalendarFeedToken.user_id)
        .where(CalendarFeedToken.token_hash == hash_token(token))
    )
    found = (await session.execute(q)).first()
    if found is None:
        raise FeedNotFound
    row, user = found
    if not user.is_active:
        raise FeedNotFound
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at > LAST_USED_RESOLUTION:
        row.last_used_at = now
        await session.commit()
    return row, user


def _istanbul(at: datetime | None) -> datetime | None:
    if at is None:
        return None
    from datetime import UTC
    from zoneinfo import ZoneInfo

    return at.replace(tzinfo=UTC).astimezone(ZoneInfo("Europe/Istanbul"))


def fetched_text(at: datetime | None) -> tuple[str | None, str | None]:
    """CAL-05 "Takviminiz en son … çekti" (Istanbul time); ``(None, None)`` before the first fetch."""
    local = _istanbul(at)
    if local is None:
        return None, None
    stamp = f"{local:%d.%m.%Y %H:%M}"
    return f"Takviminiz en son çekti: {stamp}", f"Your calendar last fetched: {stamp}"


async def scope_label(session: AsyncSession, kind: str | None, scope_id: int | None) -> tuple[str, str]:
    from app.services import calendar_classes as cc

    if kind is None:
        return "Tüm takvim bağlantıları (eski bağlantı)", "Every calendar feed (legacy link)"
    tr, en = cc.SCOPE_LABELS.get(kind, (kind, kind))
    if kind == "department_classes" and scope_id is not None:
        dep = await session.get(Program, scope_id)
        if dep is not None:
            return f"{dep.name} bölümünün dersleri", f"{dep.name} classes"
    if kind == "room" and scope_id is not None:
        room = await session.get(Room, scope_id)
        if room is not None:
            return f"{room.display_name} takvimi", f"{room.display_name} calendar"
    if kind == "room_group" and scope_id is not None:
        rg = await session.get(RoomGroup, scope_id)
        if rg is not None:
            return f"{rg.name} takvimi", f"{rg.name} calendar"
    return tr, en


async def subscription_out(session: AsyncSession, row: CalendarFeedToken) -> dict[str, Any]:
    base, _ = await public_base(session)
    tr, en = await scope_label(session, row.scope_kind, row.scope_id)
    fetched_tr, fetched_en = fetched_text(row.last_used_at)
    return {
        **token_out(row),
        "channel": "link",
        "scope_kind": row.scope_kind,
        "scope_id": row.scope_id,
        "scope_label": tr,
        "scope_label_en": en,
        "path": scoped_path(row),
        "consent_id": row.consent_id,
        "fields": row.fields,
        "last_fetched_tr": fetched_tr,
        "last_fetched_en": fetched_en,
        "url_known": bool(base),
    }


async def scope_switches(session: AsyncSession) -> dict[str, bool]:
    g = await get_group(session, "integrations")
    return {kind: bool(g.get(key, True)) for kind, key in SCOPE_SWITCH.items()}


def _scope_error(status: int, code: str, en: str, tr: str, **extra: Any) -> Exception:
    from app.services import calendar_classes as cc

    return cc.ScopeError(status, code, en, tr, **extra)


async def check_scope(session: AsyncSession, access: Access, kind: str, scope_id: int | None) -> None:
    """Raise :class:`app.services.calendar_classes.ScopeError` unless ``access`` may export ``kind`` /
    ``scope_id``: the admin's switch (403 ``scope_disabled``), a linked instructor (409 ``not_linked``), the
    department rule (403 ``department_not_allowed``), an existing department / visible room or group (404)."""
    from app.services import calendar_classes as cc

    if kind not in cc.SCOPE_KINDS:
        raise _scope_error(422, "unknown_scope", f"unknown scope {kind!r}", "Bilinmeyen takvim kapsamı")
    if kind in cc.SCOPES_WITH_ID and scope_id is None:
        raise _scope_error(422, "scope_id_required", f"{kind} needs scope_id", "Bu kapsam için bir seçim gerekli")
    if not (await scope_switches(session)).get(kind, True):
        raise _scope_error(
            403,
            "scope_disabled",
            "The administrator has turned this calendar off.",
            "Bu takvim seçeneği yönetici tarafından kapatıldı.",
        )
    if kind in ("my_classes", "my_duties"):
        if not await cc.linked_instructor_ids(session, access.user_id):
            raise cc.not_linked_error()
    elif kind == "department_classes":
        assert scope_id is not None
        dep = await session.get(Program, scope_id)
        if dep is None:
            raise _scope_error(404, "department_not_found", "department not found", "Bölüm bulunamadı")
        if not await cc.department_allowed(session, access, dep.id):
            raise cc.department_not_allowed_error(dep.id, dep.name)
    elif kind == "room":
        room = await session.get(Room, scope_id)
        if room is None or not access.can_view_room(room):
            raise _scope_error(404, "room_not_found", "room not found", "Derslik bulunamadı")
    elif kind == "room_group":
        rg = await session.get(RoomGroup, scope_id)
        members = (
            list((await session.execute(select(Room.id).where(Room.room_group_id == rg.id))).scalars())
            if rg is not None
            else []
        )
        if not await _visible_rooms_of(session, access, members):
            raise _scope_error(404, "room_group_not_found", "room group not found", "Derslik grubu bulunamadı")


async def active_consent_id(session: AsyncSession, user_id: int) -> int | None:
    from app.models.kvkk import Consent

    q = (
        select(Consent.id)
        .where(Consent.user_id == user_id, Consent.purpose == "calendar_sync", Consent.withdrawn_at.is_(None))
        .order_by(Consent.id.desc())
    )
    return (await session.execute(q.limit(1))).scalar_one_or_none()


async def create_subscription(
    session: AsyncSession, access: Access, kind: str, scope_id: int | None, label: str | None = None
) -> tuple[CalendarFeedToken, str]:
    """A link bound to one scope after the switch, consent and permission checks (CAL-03). Raises
    :class:`~app.services.calendar_classes.ScopeError`, the ``consent_required``
    :class:`~app.services.kvkk.KvkkError` or ``OverflowError`` (too many links). Flushes; the caller audits and
    commits."""
    from app.services import calendar_classes as cc

    if not await sync_enabled(session):
        raise cc.ScopeError(
            403,
            "calendar_sync_off",
            "Calendar sync is turned off by the institution.",
            "Takvim eşitleme kurumunuz tarafından kapalı.",
        )
    if kind not in cc.SCOPES_WITH_ID:
        scope_id = None
    await check_scope(session, access, kind, scope_id)
    row, token = await create_token(session, access.user, label)
    row.scope_kind, row.scope_id = kind, scope_id
    row.consent_id = await active_consent_id(session, access.user_id)
    row.fields = (await cc.fields_setting(session)).as_dict()
    await session.flush()
    return row, token


async def rotate_subscription(session: AsyncSession, access: Access, row: CalendarFeedToken) -> tuple[Any, str]:
    """Rotate ("Bağlantıyı yenile"): a new link of the same scope (re-checked), the old one revoked."""
    kind, scope_id, label = row.scope_kind, row.scope_id, row.label
    if kind is None:
        await session.delete(row)
        await session.flush()
        return await create_token(session, access.user, label)
    await session.delete(row)
    await session.flush()
    return await create_subscription(session, access, kind, scope_id, label)


def sample_text(start: datetime, end: datetime, summary: str, location: str) -> tuple[str, str]:
    """``PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50`` (research §3.7 tap 3) and its English twin."""
    day = start.isoweekday() - 1
    when = f"{start:%H:%M}–{end:%H:%M}"
    return (
        f"{summary} — {location} — {_SHORT_DAYS[day]} {when}",
        f"{summary} — {location} — {_SHORT_DAYS_EN[day]} {when}",
    )


async def _class_filter(session: AsyncSession, access: Access, kind: str, scope_id: int | None) -> Any:
    from app.services import calendar_classes as cc

    if kind == "my_classes":
        return cc.ScopeFilter(instructor_ids=frozenset(await cc.linked_instructor_ids(session, access.user_id)))
    if kind == "department_classes":
        return cc.ScopeFilter(program_id=scope_id)
    if kind == "room" and scope_id is not None:
        return cc.ScopeFilter(room_ids=frozenset({scope_id}))
    if kind == "room_group" and scope_id is not None:
        members = list((await session.execute(select(Room.id).where(Room.room_group_id == scope_id))).scalars())
        return cc.ScopeFilter(room_ids=frozenset(await _visible_rooms_of(session, access, members)))
    return None


async def preview(session: AsyncSession, access: Access, kind: str, scope_id: int | None) -> dict[str, Any]:
    """Tap 3 "Takviminize şunlar gönderilecek": the fields that leave SmartSched, the number of upcoming events
    and a sample event card from the real first upcoming one (``sample`` is null when there is none)."""
    from app.services import calendar_classes as cc
    from app.services import calendar_duties as cd

    today: date = await booking_svc.today(session)
    fields = (await cc.fields_setting(session)).as_dict()
    if kind == "my_duties":  # CAL-13: never another person's name, whatever the class setting says
        fields = {**fields, "section": False, "co_instructors": False}
    sample: dict[str, Any] | None = None
    count = 0
    if kind == "my_bookings":
        q = (
            select(Booking)
            .where(Booking.user_id == access.user_id, Booking.status.in_((BOOKED, PENDING)), Booking.date >= today)
            .order_by(Booking.date, Booking.start_period, Booking.id)
        )
        rows = list((await session.execute(q)).scalars())
        count = len(rows)
        if rows:
            view = await event_view(_Cache(session), None, rows[0])
            if view is not None:
                tr, en = sample_text(view.start, view.end, view.summary, view.location)
                sample = {"summary": view.summary, "location": view.location, "start": view.start.isoformat(),
                          "end": view.end.isoformat(), "text_tr": tr, "text_en": en}  # fmt: skip
    else:
        flt = await _class_filter(session, access, kind, scope_id)
        sel = None
        if kind == "my_duties":
            mine = frozenset(await cc.linked_instructor_ids(session, access.user_id))
            sel = await cd.select_duties(session, mine, today, cd.horizon(today), grace_days=0)
        elif flt is not None:
            horizon = await cc.horizon_end(session, today)
            sel = await cc.select_classes(session, flt, today, horizon, grace_days=0)
        if sel is not None:
            live = sorted((o for o, _ in sel.live), key=lambda o: (o.start, o.uid))
            count = len(live)
            if live:
                o = live[0]
                tr, en = sample_text(o.start, o.end, o.summary(), o.location)
                sample = {"summary": o.summary(), "location": o.location, "start": o.start.isoformat(),
                          "end": o.end.isoformat(), "text_tr": tr, "text_en": en}  # fmt: skip
    sent = [k for k, on in fields.items() if on and (kind != "my_bookings" or k in ("room", "time", "department"))]
    return {
        "scope_kind": kind,
        "scope_id": scope_id,
        "upcoming_count": count,
        "sample": sample,
        "fields": [{"key": k, "label_tr": cc.FIELD_LABELS[k][0], "label_en": cc.FIELD_LABELS[k][1]} for k in sent],
        "never_tr": "Öğrenci bilgisi, not ve diğer gözetmenlerin adları gönderilmez."
        if kind == "my_duties"
        else "Öğrenci bilgisi, not ve diğer öğretim elemanlarının adları gönderilmez."
        if not fields["co_instructors"]
        else "Öğrenci bilgisi ve notlar gönderilmez.",
        "never_en": "No student data, notes or other invigilators' names are sent."
        if kind == "my_duties"
        else "No student data, notes or other instructors' names are sent."
        if not fields["co_instructors"]
        else "No student data or notes are sent.",
    }


#: research §2.2: how soon each channel shows a change (the client decides when it polls a link)
FRESHNESS = {
    "push": (
        "Değişiklikler birkaç dakika içinde takviminize yansır. Ayrı bir 'SmartSched – Derslerim' takvimi oluşturulur.",
        "Changes reach your calendar within minutes. A separate 'SmartSched – Derslerim' calendar is created.",
    ),
    "link": (
        "Apple Takvim, Google veya Outlook bu bağlantıya abone olur. Güncellemeler uygulamaya göre birkaç dakika ile "
        "12 saat arasında gelir.",
        "Apple Calendar, Google or Outlook subscribe to this link. Updates arrive within minutes to 12 hours, "
        "depending on the app.",
    ),
    "file": (
        "Tek seferlik kopya. Sonraki değişiklikler kendiliğinden gelmez.",
        "A one-off copy. Later changes do not arrive by themselves.",
    ),
}


async def export_options(session: AsyncSession, access: Access) -> dict[str, Any]:
    """``GET /calendar/export/options``: per scope whether it is available (with the reason when not), the upcoming
    count and a sample, the departments the person may export, the configured channels and the consent state."""
    from app.services import calendar_classes as cc
    from app.services import calendar_connectors as conn_svc

    enabled = await sync_enabled(session)
    linked = await cc.linked_instructor_ids(session, access.user_id)
    everything, allowed = await cc.department_rule(session, access)
    deps = list((await session.execute(select(Program).where(Program.archived.is_(False)))).scalars())
    deps = [d for d in deps if everything or d.id in allowed]
    deps.sort(key=lambda d: (tr_sort_key(d.name), d.id))
    own = access.user.department_id if access.user.department_id in {d.id for d in deps} else None
    taught = sorted(await cc.taught_program_ids(session, linked) & {d.id for d in deps})
    default_dep = own or (taught[0] if taught else (deps[0].id if deps else None))
    scopes: list[dict[str, Any]] = []
    for kind in ("my_classes", "department_classes", "my_bookings", "my_duties"):
        tr, en = cc.SCOPE_LABELS[kind]
        item: dict[str, Any] = {"kind": kind, "label_tr": tr, "label_en": en, "available": True, "reason": None}
        scope_id = default_dep if kind == "department_classes" else None
        if kind == "department_classes":
            item["departments"] = [{"id": d.id, "name": d.name} for d in deps]
            item["default_department_id"] = default_dep
        try:
            if kind == "department_classes" and scope_id is None:
                raise cc.department_not_allowed_error(0)
            await check_scope(session, access, kind, scope_id)
        except cc.ScopeError as exc:
            item["available"] = False
            item["reason"] = {"code": exc.code, "message_tr": exc.tr, "message_en": exc.en}
        if item["available"]:
            item["preview"] = await preview(session, access, kind, scope_id)
        scopes.append(item)
    providers = {
        p.name: {"label": p.label, "configured": await conn_svc.client_config(session, p) is not None}
        for p in conn_svc.PROVIDERS.values()
    }
    # CAL-07: say which account to use before the person leaves for the provider's consent screen
    hint = (await conn_svc.verify_account(session, access.user, conn_svc.PROVIDERS["google"],
                                          conn_svc.AccountInfo(None, None))).domain  # fmt: skip
    verified_only = await conn_svc.push_verified_only(session)
    base, _ = await public_base(session)
    verification = {"required": verified_only, "domain": hint,
                    **({k: v for k, v in conn_svc.not_verified_detail(hint).items() if k.startswith("message")}
                       if verified_only else {})}  # fmt: skip
    return {
        "enabled": enabled,
        "consent": await consent_state(session, access.user),
        "linked": bool(linked),
        "scopes": scopes,
        "channels": {
            "push": {
                **providers,
                "freshness_tr": FRESHNESS["push"][0],
                "freshness_en": FRESHNESS["push"][1],
                "verification": verification,
            },
            # CAL10-F02: without a panel address a link cannot subscribe ("never a fake button"): not offered, said why
            "link": {
                "available": enabled and bool(base),
                **(
                    {
                        "reason": "no_public_url",
                        "message_tr": "Abonelik bağlantısı için yöneticinizin panel adresini girmesi gerekiyor. "
                        "Şimdilik .ics dosyasını indirebilirsiniz.",
                        "message_en": "A subscription link needs the panel address, which your administrator has not "
                        "set yet. You can download an .ics file for now.",
                    }
                    if enabled and not base
                    else {}
                ),
                "freshness_tr": FRESHNESS["link"][0],
                "freshness_en": FRESHNESS["link"][1],
            },
            "file": {"available": True, "freshness_tr": FRESHNESS["file"][0], "freshness_en": FRESHNESS["file"][1]},
        },
    }
