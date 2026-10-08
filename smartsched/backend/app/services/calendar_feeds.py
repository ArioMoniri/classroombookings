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


async def create_token(session: AsyncSession, user: User, label: str | None = None) -> tuple[CalendarFeedToken, str]:
    """A new link (raises ``OverflowError`` above :data:`MAX_TOKENS_PER_USER`). The token is returned once."""
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
    """Revoke every link of ``user`` and create one new link."""
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
    if user is not None and not owner_view and booking_svc.can_view_user(access, b, room):  # type: ignore[arg-type]
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
    kind: str  # mine | room | department | room_group
    id: int


@dataclass
class Feed:
    title: str
    filename: str
    text: str

    @property
    def etag(self) -> str:
        return '"' + hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:32] + '"'


def _visible(access: Access, b: Booking, room: Room) -> bool:
    return access.can_view_room(room) or booking_svc.is_owner(access, b)


async def _visible_rooms_of(session: AsyncSession, access: Access, room_ids: list[int]) -> list[int]:
    if not room_ids:
        return []
    rooms = (await session.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()
    return [r.id for r in rooms if access.can_view_room(r)]


async def build_feed(session: AsyncSession, access: Access, scope: FeedScope, *, title: str | None = None) -> Feed:
    """The calendar of ``scope`` as seen by ``access``; :class:`FeedNotFound` for what the user may not see."""
    group = await get_group(session, "integrations")
    today: date = await booking_svc.today(session)
    since = today - timedelta(days=max(0, int(group["feed_past_days"] or 0)))
    grace_cutoff = utcnow() - timedelta(days=max(0, int(group["feed_cancelled_grace_days"] or 0)))
    q = select(Booking).where(Booking.date >= since)
    include_pending = False
    room_filter: list[int] | None = None
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
    elif scope.kind == "department":
        dep = await session.get(Program, scope.id)
        if dep is None:
            raise FeedNotFound
        q = q.where(Booking.department_id == dep.id)
        default_title, filename = f"SmartSched – {dep.name}", f"department-{dep.id}.ics"
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
    else:
        raise FeedNotFound
    statuses = {BOOKED, CANCELLED} | ({PENDING} | ENDED if include_pending else set())
    q = q.where(Booking.status.in_(sorted(statuses))).order_by(Booking.date, Booking.start_period, Booking.id)
    cache = _Cache(session)
    views: list[EventView] = []
    for b in (await session.execute(q)).scalars():
        if b.status != BOOKED and b.status != PENDING and changed_at(b) < grace_cutoff:
            continue
        room_row: Room | None = await cache.get(Room, b.room_id)
        if room_row is None or not _visible(access, b, room_row):
            continue
        view = await event_view(cache, access, b)
        if view is not None:
            views.append(view)
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
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    final_title = title or default_title
    return Feed(final_title, filename, render_calendar(final_title, tz_name, events))


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
        "rooms": [{"id": r.id, "code": r.code, "name": r.display_name, "room_group_id": r.room_group_id} for r in rooms],
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
