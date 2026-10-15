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
    if scope.kind in ("room", "room_group", "department"):  # A-14: the published classes too
        horizon = today + timedelta(days=CLASS_HORIZON_DAYS)
        events += await class_events(
            session,
            access,
            since,
            horizon,
            room_ids=[scope.id] if scope.kind == "room" else room_filter,
            program_id=scope.id if scope.kind == "department" else None,
        )
        events.sort(key=lambda e: (e.start, e.uid))
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    final_title = title or default_title
    return Feed(final_title, filename, render_calendar(final_title, tz_name, events))


CLASS_HORIZON_DAYS = 200  # published classes are listed this far ahead (the rest of a term)


async def class_events(
    session: AsyncSession,
    access: Access,
    d_from: date,
    d_to: date,
    *,
    room_ids: list[int] | None = None,
    program_id: int | None = None,
) -> list[IcsEvent]:
    """A-14: the published (active-run) class meetings in ``room_ids`` or of the department ``program_id`` as busy
    events. SUMMARY is the course code(s) (or the request's code and section), never the board text, which may
    name people; no instructor names at all (KVKK). Times come from the term's booking periods, else the standard
    grid. Rooms the viewer may not see are left out."""
    from app.models import Assignment, Course, ScheduleRun, Section, Term
    from app.services.bookings_calendar import term_info
    from app.services.calendar import period_times

    wanted_ids: set[int] | None = None
    if program_id is not None:
        # the department's classes: requests of its sections, and board rows whose course codes are its courses
        run_ids = list((await session.execute(select(ScheduleRun.id).where(ScheduleRun.is_active.is_(True)))).scalars())
        if not run_ids:
            return []
        keys = {
            n.course_key(code)
            for code in (
                await session.execute(
                    select(Course.code)
                    .join(Section, Section.course_id == Course.id)
                    .where(Section.program_id == program_id)
                )
            ).scalars()
        }
        rows = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id.in_(run_ids), Assignment.archived.is_(False))
                )
            ).scalars()
        )
        mrs = {a.meeting_request_id for a in rows if a.meeting_request_id}
        own_mr: set[int] = set()
        if mrs:
            from app.models import MeetingRequest

            own_mr = set(
                (
                    await session.execute(
                        select(MeetingRequest.id)
                        .join(Section, Section.id == MeetingRequest.section_id)
                        .where(MeetingRequest.id.in_(mrs), Section.program_id == program_id)
                    )
                ).scalars()
            )
        wanted_ids = {
            a.id
            for a in rows
            if (a.meeting_request_id in own_mr) or any(n.course_key(c) in keys for c in (a.course_codes or []))
        }
        if not wanted_ids:
            return []
        room_ids = sorted({int(r) for a in rows if a.id in wanted_ids for r in (a.room_ids or [])})
    occ = await booking_svc.timetable_occupancy(session, set(room_ids) if room_ids else None, d_from, d_to)
    helds = [h for hs in occ.values() for h in hs if h.kind == "timetable"]
    if wanted_ids is not None:
        helds = [h for h in helds if h.ref_id in wanted_ids]
    if not helds:
        return []
    assigns = {
        a.id: a
        for a in (
            await session.execute(select(Assignment).where(Assignment.id.in_({h.ref_id for h in helds})))
        ).scalars()
    }
    labels = await booking_svc._request_labels(
        session, {a.meeting_request_id for a in assigns.values() if a.meeting_request_id}
    )
    runs = {
        r.id: r
        for r in (
            await session.execute(select(ScheduleRun).where(ScheduleRun.id.in_({a.run_id for a in assigns.values()})))
        ).scalars()
    }
    # booking-period times per term (start_period -> time_start, end_period -> time_end)
    times: dict[int, tuple[dict[int, Any], dict[int, Any]]] = {}

    async def period_clock(term_id: int, sp: int, ep: int) -> tuple[Any, Any]:
        if term_id not in times:
            term = await session.get(Term, term_id)
            info = await term_info(session, term) if term is not None else None
            starts: dict[int, Any] = {}
            ends: dict[int, Any] = {}
            if info is not None and info.default_schedule_id:
                for p in (
                    await session.execute(
                        select(BookingPeriod).where(BookingPeriod.schedule_id == info.default_schedule_id)
                    )
                ).scalars():
                    starts.setdefault(p.start_period, p.time_start)
                    ends.setdefault(p.end_period, p.time_end)
            times[term_id] = (starts, ends)
        starts, ends = times[term_id]
        if sp in starts and ep in ends:
            return starts[sp], ends[ep]
        s_txt, e_txt = period_times(sp, ep)
        return datetime.strptime(s_txt, "%H:%M").time(), datetime.strptime(e_txt, "%H:%M").time()

    # course codes as the planner writes them ("PSY 262"), looked up by course key
    all_codes = {n.course_key(c) for a in assigns.values() for c in (a.course_codes or []) if c}
    display: dict[str, str] = {}
    if all_codes:
        for code, disp in (await session.execute(select(Course.code, Course.display_code))).all():
            k = n.course_key(code)
            if k in all_codes and disp:
                display.setdefault(k, disp)
    cache = _Cache(session)
    out: list[IcsEvent] = []
    for h in sorted(helds, key=lambda x: (x.date, x.start, x.room_id, x.ref_id)):
        a = assigns.get(h.ref_id)
        room: Room | None = await cache.get(Room, h.room_id)
        if a is None or room is None or not access.can_view_room(room):
            continue
        run = runs.get(a.run_id)
        codes = [display.get(n.course_key(c), c) for c in (a.course_codes or []) if c]
        what = " / ".join(dict.fromkeys(codes)) or labels.get(a.meeting_request_id or 0, "")
        t0, t1 = await period_clock(run.term_id if run else 0, h.start, h.end)
        stamp = (run.finished_at or run.created_at) if run is not None else utcnow()
        out.append(
            IcsEvent(
                uid=f"class-{a.id}-{h.room_id}-{h.date:%Y%m%d}@smartsched",
                start=datetime.combine(h.date, t0),
                end=datetime.combine(h.date, t1),
                summary=f"{what} ({room.display_name})" if what else room.display_name,
                location=room.display_name,
                description=None,
                status="CONFIRMED",
                sequence=0,
                last_modified=stamp,
            )
        )
    return out


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
