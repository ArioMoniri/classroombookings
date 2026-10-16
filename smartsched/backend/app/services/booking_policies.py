"""P8 booking policies and exam-period mode (docs/product/booking-enhancements.md §P8).

Every booking mutation (``app.services.bookings``: single bookings, the instances of a series, multi-booking
selections and moves) calls :func:`enforce` once per booked date, after the room, term, period and approval need
are known. A rule (``booking_policies``, see :mod:`app.models.policies`) that is broken either

* refuses the booking: :class:`app.services.bookings.BookingError` 409 ``policy_<rule>`` with ``message_tr`` /
  ``message_en`` and the rule (``policy``), so the screen can say why ("Neden?"); or
* turns it into an approval request (``effect = request``): the booking is stored ``PENDING`` and goes to the
  approvers exactly like a room rule of P1 (``approvals.Need`` with ``source = policy``).

The rules:

* ``min_notice_workdays``: at least N working days ahead, counted from today without weekends and holidays
  (``approvals.add_workdays``): with 3, a booking made on Thursday may be for Tuesday at the earliest;
* ``max_advance_days``: at most N calendar days ahead;
* ``max_duration_minutes``: one person's back-to-back bookings in one room on one day (the new one included) last
  at most N minutes, from the first start to the last end;
* ``max_active_bookings``: active future bookings of the booked-for user (single bookings and requests count one
  each, a series counts once);
* ``buffer_minutes``: another person's booking in the same room ends at least N minutes before this one starts and
  starts at least N minutes after it ends (setup / teardown);
* ``quiet_hours``: weekday time windows without bookings (``12.40``-``13:30`` style times are accepted);
* ``blackouts``: date ranges without bookings, with a label.

Exam-period mode (settings group ``policies``): in the exam weeks of the booking's term (weeks of kind ``EXAM`` or
``MAKEUP``) the exam rooms (the rooms the term's exam timetable uses, plus a chosen list) take requests only
(``request``) or nothing (``closed``). Holders of ``planning.admin`` are not bound by policies; approvers, planning
administrators and ``bookings.skip_approval`` holders are not bound by exam-period mode (they run the exams).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import Assignment, Booking, BookingPeriod, BookingSeries, RoomGroup, ScheduleRun, Week
from app.models.booking import BOOKED, PENDING
from app.models.catalog import Room
from app.models.policies import BookingPolicy
from app.services.bookings_perms import Access
from app.services.bookings_settings import get_value, set_group

SCOPES = ("all", "room", "room_group", "tag")
EFFECTS = ("refuse", "request")
EXAM_MODES = ("off", "request", "closed")
EXAM_WEEK_KINDS = ("EXAM", "MAKEUP")
RULES = (
    "min_notice",
    "max_advance",
    "max_duration",
    "max_active",
    "buffer",
    "quiet_hours",
    "blackout",
    "exam_period",
)
PUBLISHABLE = ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL")
DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


class PolicyError(Exception):
    """Invalid policy input (422, Turkish and English)."""

    def __init__(self, code: str, message: str, message_tr: str, status: int = 422) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr = status, code, message, message_tr

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "message_en": self.message, "message_tr": self.message_tr}


@dataclass
class Violation:
    rule: str
    effect: str  # refuse | request
    message_tr: str
    message_en: str
    policy_id: int | None = None
    policy_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "effect": self.effect,
            "message_tr": self.message_tr,
            "message_en": self.message_en,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            **self.data,
        }


# --------------------------------------------------------------------------------------------------
# Input normalisation (Turkish times: "12.40", NBSP, "08:30")
# --------------------------------------------------------------------------------------------------


def parse_clock(value: Any) -> time:
    """``08:30``, ``12.40``, ``9.00`` (NBSP tolerated) -> a time; 422 otherwise."""
    t = n.parse_time(n.clean_text(str(value)) if value is not None else None)
    if t is None:
        raise PolicyError(
            "time", f"{value!r} is not a time (HH:MM or HH.MM)", f"{value!r} geçerli bir saat değil (SS:DD ya da SS.DD)"
        )
    return t


def _hm(t: time) -> str:
    return f"{t:%H:%M}"


def _int_or_none(data: dict[str, Any], key: str, lo: int, hi: int) -> int | None:
    v = data.get(key)
    if v is None or v == "":
        return None
    try:
        iv = int(str(v).strip())
    except ValueError as exc:
        raise PolicyError(key, f"{key} must be a whole number", f"{key} bir tam sayı olmalı") from exc
    if not lo <= iv <= hi:
        raise PolicyError(key, f"{key} must be between {lo} and {hi}", f"{key} {lo} ile {hi} arasında olmalı")
    return iv


async def validate(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    """Normalised column values of a policy (422 :class:`PolicyError` on bad input)."""
    out: dict[str, Any] = {}
    name = n.clean_text(data.get("name")) if data.get("name") is not None else None
    if not name:
        raise PolicyError("name", "a policy needs a name", "kuralın bir adı olmalı")
    out["name"] = name[:120]
    out["enabled"] = bool(data.get("enabled", True))
    scope = str(data.get("scope_type") or "all")
    if scope not in SCOPES:
        raise PolicyError("scope_type", f"scope_type: one of {', '.join(SCOPES)}", "kapsam: all, room, room_group, tag")
    out["scope_type"], out["scope_id"], out["tag"] = scope, None, None
    if scope == "room":
        rid = data.get("scope_id")
        if rid is None or await session.get(Room, int(rid)) is None:
            raise PolicyError("scope_id", "room not found", "oda bulunamadı")
        out["scope_id"] = int(rid)
    elif scope == "room_group":
        gid = data.get("scope_id")
        if gid is None or await session.get(RoomGroup, int(gid)) is None:
            raise PolicyError("scope_id", "room group not found", "oda grubu bulunamadı")
        out["scope_id"] = int(gid)
    elif scope == "tag":
        tag = n.tr_upper(n.clean_text(data.get("tag")) or "") if data.get("tag") else ""
        if not tag:
            raise PolicyError(
                "tag", "a room-type rule needs a tag (e.g. TIP, PC)", "oda türü kuralı için etiket gerekli"
            )
        out["tag"] = tag[:32]
    if data.get("term_id") is not None:
        from app.models import Term

        if await session.get(Term, int(data["term_id"])) is None:
            raise PolicyError("term_id", "term not found", "dönem bulunamadı")
        out["term_id"] = int(data["term_id"])
    else:
        out["term_id"] = None
    roles = data.get("role_codes") or []
    if not isinstance(roles, list):
        raise PolicyError("role_codes", "role_codes must be a list", "roller bir liste olmalı")
    out["role_codes"] = sorted({n.tr_upper(n.clean_text(str(r)) or "") for r in roles if str(r).strip()})
    effect = str(data.get("effect") or "refuse")
    if effect not in EFFECTS:
        raise PolicyError("effect", "effect: refuse or request", "etki: refuse (reddet) ya da request (talep)")
    out["effect"] = effect
    out["min_notice_workdays"] = _int_or_none(data, "min_notice_workdays", 0, 365)
    out["max_advance_days"] = _int_or_none(data, "max_advance_days", 0, 3650)
    out["max_duration_minutes"] = _int_or_none(data, "max_duration_minutes", 10, 24 * 60)
    out["max_active_bookings"] = _int_or_none(data, "max_active_bookings", 0, 10_000)
    out["buffer_minutes"] = _int_or_none(data, "buffer_minutes", 0, 240)
    quiet: list[dict[str, Any]] = []
    for w in data.get("quiet_hours") or []:
        if not isinstance(w, dict):
            raise PolicyError("quiet_hours", "quiet_hours: a list of windows", "sessiz saatler bir liste olmalı")
        days = sorted({int(x) for x in (w.get("weekdays") or [1, 2, 3, 4, 5, 6, 7])})
        if not days or any(not 1 <= x <= 7 for x in days):
            raise PolicyError("quiet_hours", "weekdays are 1 (Monday) to 7", "günler 1 (Pazartesi) ile 7 arasında")
        start, end = parse_clock(w.get("start")), parse_clock(w.get("end"))
        if start == end:
            raise PolicyError("quiet_hours", "a quiet window needs a length", "sessiz saat aralığı boş olamaz")
        quiet.append({"weekdays": days, "start": _hm(start), "end": _hm(end)})
    out["quiet_hours"] = quiet
    blackouts: list[dict[str, Any]] = []
    for b in data.get("blackouts") or []:
        if not isinstance(b, dict):
            raise PolicyError("blackouts", "blackouts: a list of date ranges", "kapalı tarihler bir liste olmalı")
        try:
            d0 = _parse_date(b.get("from"))
            d1 = _parse_date(b.get("to") or b.get("from"))
        except ValueError as exc:
            raise PolicyError("blackouts", "dates: YYYY-MM-DD or DD.MM.YYYY", "tarih: GG.AA.YYYY") from exc
        if d1 < d0:
            raise PolicyError("blackouts", "a blackout ends before it starts", "kapalı aralığın sonu başından önce")
        label = n.clean_text(b.get("label")) if b.get("label") else None
        blackouts.append({"from": d0.isoformat(), "to": d1.isoformat(), "label": (label or "")[:120] or None})
    out["blackouts"] = blackouts
    out["note"] = n.clean_text(data.get("note")) if data.get("note") else None
    limits = (
        "min_notice_workdays",
        "max_advance_days",
        "max_duration_minutes",
        "max_active_bookings",
        "buffer_minutes",
    )
    if all(out[k] is None for k in limits) and not quiet and not blackouts:
        raise PolicyError("empty", "a policy needs at least one limit", "kural en az bir sınır içermeli")
    return out


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = (n.clean_text(str(value)) or "").strip()
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return date.fromisoformat(text)


def policy_out(p: BookingPolicy) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "enabled": p.enabled,
        "term_id": p.term_id,
        "scope_type": p.scope_type,
        "scope_id": p.scope_id,
        "tag": p.tag,
        "role_codes": list(p.role_codes or []),
        "effect": p.effect,
        "min_notice_workdays": p.min_notice_workdays,
        "max_advance_days": p.max_advance_days,
        "max_duration_minutes": p.max_duration_minutes,
        "max_active_bookings": p.max_active_bookings,
        "buffer_minutes": p.buffer_minutes,
        "quiet_hours": list(p.quiet_hours or []),
        "blackouts": list(p.blackouts or []),
        "note": p.note,
        "summary": describe(p),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def describe(p: BookingPolicy) -> dict[str, list[str]]:
    """The rule in words (Turkish and English), one line per limit: what "Neden?" shows."""
    tr: list[str] = []
    en: list[str] = []
    if p.min_notice_workdays:
        tr.append(f"En az {p.min_notice_workdays} iş günü önceden (hafta sonu ve tatiller sayılmaz)")
        en.append(f"At least {p.min_notice_workdays} working day(s) ahead (weekends and holidays not counted)")
    if p.max_advance_days is not None:
        tr.append(f"En fazla {p.max_advance_days} gün sonrası için")
        en.append(f"At most {p.max_advance_days} day(s) ahead")
    if p.max_duration_minutes:
        tr.append(f"Aynı odada art arda en fazla {p.max_duration_minutes} dakika")
        en.append(f"At most {p.max_duration_minutes} minutes back to back in one room")
    if p.max_active_bookings is not None:
        tr.append(f"Kişi başına en fazla {p.max_active_bookings} etkin rezervasyon")
        en.append(f"At most {p.max_active_bookings} active booking(s) per person")
    if p.buffer_minutes:
        tr.append(f"Başka bir rezervasyonla arasında en az {p.buffer_minutes} dakika")
        en.append(f"At least {p.buffer_minutes} minutes between bookings")
    for w in p.quiet_hours or []:
        days = w.get("weekdays") or []
        tr.append(f"Rezervasyon yok: {', '.join(DAY_TR[d] for d in days)} {w['start']}-{w['end']}")
        en.append(f"No bookings: {', '.join(DAY_EN[d] for d in days)} {w['start']}-{w['end']}")
    for b in p.blackouts or []:
        d0, d1 = date.fromisoformat(b["from"]), date.fromisoformat(b["to"])
        span = f"{d0:%d.%m.%Y}" if d0 == d1 else f"{d0:%d.%m.%Y}-{d1:%d.%m.%Y}"
        tr.append(f"Kapalı: {span}" + (f" ({b['label']})" if b.get("label") else ""))
        en.append(f"Closed: {span}" + (f" ({b['label']})" if b.get("label") else ""))
    if p.effect == "request":
        tr.append("Kurala uymayan rezervasyon onaya gider")
        en.append("A booking outside the rule goes to the approvers")
    return {"tr": tr, "en": en}


# --------------------------------------------------------------------------------------------------
# Exam-period mode
# --------------------------------------------------------------------------------------------------


async def exam_settings(session: AsyncSession) -> dict[str, Any]:
    mode = str(await get_value(session, "policies", "exam_period_mode") or "off")
    rooms = await get_value(session, "policies", "exam_period_rooms") or {}
    if not isinstance(rooms, dict):
        rooms = {}
    return {
        "mode": mode if mode in EXAM_MODES else "off",
        "from_exam_timetable": bool(rooms.get("from_exam_timetable", True)),
        "room_ids": sorted({int(x) for x in rooms.get("room_ids") or []}),
    }


async def set_exam_settings(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    cur = await exam_settings(session)
    mode = str(data.get("mode", cur["mode"]))
    if mode not in EXAM_MODES:
        raise PolicyError("mode", "mode: off, request or closed", "sınav dönemi kipi: off, request ya da closed")
    room_ids = data.get("room_ids", cur["room_ids"])
    ids = sorted({int(x) for x in room_ids or []})
    if ids:
        found = set((await session.execute(select(Room.id).where(Room.id.in_(ids)))).scalars())
        missing = [i for i in ids if i not in found]
        if missing:
            raise PolicyError("room_ids", f"rooms not found: {missing}", f"bulunamayan odalar: {missing}")
    from_tt = bool(data.get("from_exam_timetable", cur["from_exam_timetable"]))
    await set_group(
        session,
        "policies",
        {"exam_period_mode": mode, "exam_period_rooms": {"from_exam_timetable": from_tt, "room_ids": ids}},
    )
    return await exam_settings(session)


async def exam_timetable_rooms(session: AsyncSession, term_id: int) -> set[int]:
    """Rooms of the term's exam timetable: the published EXAM run, else the latest finished one."""
    runs = list(
        (
            await session.execute(
                select(ScheduleRun)
                .where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "EXAM", ScheduleRun.status.in_(PUBLISHABLE))
                .order_by(ScheduleRun.is_active.desc(), ScheduleRun.id.desc())
            )
        ).scalars()
    )
    if not runs:
        return set()
    q = select(Assignment.room_ids).where(Assignment.run_id == runs[0].id, Assignment.archived.is_(False))
    out: set[int] = set()
    for ids in (await session.execute(q)).scalars():
        out |= {int(r) for r in ids or []}
    return out


async def exam_weeks(session: AsyncSession, term_id: int) -> list[tuple[date, date, str]]:
    q = select(Week).where(Week.term_id == term_id, Week.kind.in_(EXAM_WEEK_KINDS), Week.start_date.is_not(None))
    return [
        (w.start_date, w.start_date + timedelta(days=6), w.label or w.kind)
        for w in (await session.execute(q.order_by(Week.index))).scalars()
        if w.start_date is not None
    ]


# --------------------------------------------------------------------------------------------------
# The index: rules loaded once per request
# --------------------------------------------------------------------------------------------------


def _covers(p: BookingPolicy, room: Room, term_id: int | None) -> bool:
    if p.term_id is not None and p.term_id != term_id:
        return False
    if p.scope_type == "all":
        return True
    if p.scope_type == "room":
        return p.scope_id == room.id
    if p.scope_type == "room_group":
        return room.room_group_id is not None and p.scope_id == room.room_group_id
    if p.scope_type == "tag":
        return bool(p.tag) and p.tag in [n.tr_upper(str(t)) for t in (room.tags or [])]
    return False


def role_code(access: Access) -> str | None:
    if access.role is not None and access.role.code:
        return str(access.role.code).upper()
    return str(access.user.role).upper() if access.user.role else None


def exempt(access: Access) -> bool:
    return access.can("planning.admin")


def exam_exempt(access: Access) -> bool:
    from app.services.approvals import skips_approval

    return skips_approval(access)


@dataclass
class PolicyIndex:
    policies: list[BookingPolicy]
    exam: dict[str, Any]
    _exam_rooms: dict[int, set[int]] = field(default_factory=dict)
    _exam_weeks: dict[int, list[tuple[date, date, str]]] = field(default_factory=dict)

    @classmethod
    async def load(cls, session: AsyncSession) -> PolicyIndex:
        q = select(BookingPolicy).where(BookingPolicy.enabled.is_(True)).order_by(BookingPolicy.id)
        return cls(list((await session.execute(q)).scalars()), await exam_settings(session))

    def for_access(self, access: Access, room: Room, term_id: int | None) -> list[BookingPolicy]:
        if exempt(access):
            return []
        code = role_code(access)
        return [
            p
            for p in self.policies
            if _covers(p, room, term_id) and (not p.role_codes or (code is not None and code in p.role_codes))
        ]

    async def exam_week(self, session: AsyncSession, term_id: int, d: date) -> str | None:
        if term_id not in self._exam_weeks:
            self._exam_weeks[term_id] = await exam_weeks(session, term_id)
        return next((label for d0, d1, label in self._exam_weeks[term_id] if d0 <= d <= d1), None)

    async def is_exam_room(self, session: AsyncSession, term_id: int, room: Room) -> bool:
        if room.id in self.exam["room_ids"]:
            return True
        if not self.exam["from_exam_timetable"]:
            return False
        if term_id not in self._exam_rooms:
            self._exam_rooms[term_id] = await exam_timetable_rooms(session, term_id)
        return room.id in self._exam_rooms[term_id]

    async def exam_violation(
        self, session: AsyncSession, access: Access, room: Room, term_id: int, d: date
    ) -> Violation | None:
        mode = self.exam["mode"]
        if mode == "off" or exam_exempt(access):
            return None
        label = await self.exam_week(session, term_id, d)
        if label is None or not await self.is_exam_room(session, term_id, room):
            return None
        if mode == "request":
            return Violation(
                "exam_period",
                "request",
                f"Sınav döneminde ({label}) {room.display_name} yalnızca talep ile ayrılır; talebiniz onaya gider",
                f"During the exam period ({label}) {room.display_name} can only be requested; your request goes to "
                "the approvers",
                data={"exam_week": label},
            )
        return Violation(
            "exam_period",
            "refuse",
            f"Sınav döneminde ({label}) {room.display_name} rezervasyona kapalıdır",
            f"{room.display_name} is closed for bookings during the exam period ({label})",
            data={"exam_week": label},
        )

    async def static_violations(
        self,
        session: AsyncSession,
        access: Access,
        room: Room,
        term_id: int,
        d: date,
        t_start: time,
        t_end: time,
        today: date,
    ) -> list[Violation]:
        """Rules that need no other booking: notice, advance, quiet hours, blackouts and exam-period mode (the grid
        and the finder evaluate these per slot)."""
        from app.services.approvals import add_workdays

        out: list[Violation] = []
        for p in self.for_access(access, room, term_id):
            if p.min_notice_workdays:
                earliest = await add_workdays(session, term_id, today, p.min_notice_workdays)
                if d < earliest:
                    out.append(
                        Violation(
                            "min_notice",
                            p.effect,
                            f"Bu rezervasyon en az {p.min_notice_workdays} iş günü önceden yapılır; en erken "
                            f"{earliest:%d.%m.%Y} için rezervasyon yapabilirsiniz (hafta sonu ve tatiller "
                            "sayılmaz)",
                            f"This booking must be made at least {p.min_notice_workdays} working day(s) ahead; the "
                            f"earliest date is {earliest:%d.%m.%Y} (weekends and holidays are not counted)",
                            p.id,
                            p.name,
                            {"earliest": earliest.isoformat(), "workdays": p.min_notice_workdays},
                        )
                    )
            if p.max_advance_days is not None:
                latest = today + timedelta(days=p.max_advance_days)
                if d > latest:
                    out.append(
                        Violation(
                            "max_advance",
                            p.effect,
                            f"En fazla {p.max_advance_days} gün sonrası için rezervasyon yapılabilir (en geç "
                            f"{latest:%d.%m.%Y})",
                            f"Bookings can be made at most {p.max_advance_days} day(s) ahead (until {latest:%d.%m.%Y})",
                            p.id,
                            p.name,
                            {"latest": latest.isoformat(), "days": p.max_advance_days},
                        )
                    )
            for w in p.quiet_hours or []:
                if d.isoweekday() not in (w.get("weekdays") or []):
                    continue
                ws, we = parse_clock(w["start"]), parse_clock(w["end"])
                spans = [(ws, we)] if ws < we else [(ws, time(23, 59)), (time(0, 0), we)]
                if any(t_start < e and s < t_end for s, e in spans):
                    out.append(
                        Violation(
                            "quiet_hours",
                            p.effect,
                            f"{DAY_TR[d.isoweekday()]} {w['start']}-{w['end']} arası rezervasyon yapılmaz",
                            f"No bookings on {DAY_EN[d.isoweekday()]} between {w['start']} and {w['end']}",
                            p.id,
                            p.name,
                            {"window": w},
                        )
                    )
                    break
            for b in p.blackouts or []:
                if date.fromisoformat(b["from"]) <= d <= date.fromisoformat(b["to"]):
                    label = b.get("label")
                    out.append(
                        Violation(
                            "blackout",
                            p.effect,
                            f"{d:%d.%m.%Y} rezervasyona kapalı" + (f" ({label})" if label else ""),
                            f"{d:%d.%m.%Y} is closed for bookings" + (f" ({label})" if label else ""),
                            p.id,
                            p.name,
                            {"blackout": b},
                        )
                    )
                    break
        ev = await self.exam_violation(session, access, room, term_id, d)
        if ev is not None:
            out.append(ev)
        return out


# --------------------------------------------------------------------------------------------------
# Rules that look at other bookings
# --------------------------------------------------------------------------------------------------


async def _active_count(session: AsyncSession, user_id: int, today: date, exclude: set[int]) -> int:
    singles = (
        await session.execute(
            select(func.count(Booking.id)).where(
                Booking.user_id == user_id,
                Booking.status.in_((BOOKED, PENDING)),
                Booking.series_id.is_(None),
                Booking.date >= today,
                Booking.id.not_in(exclude or {0}),
            )
        )
    ).scalar_one()
    series = (
        await session.execute(
            select(func.count(func.distinct(Booking.series_id)))
            .join(BookingSeries, BookingSeries.id == Booking.series_id)
            .where(
                Booking.user_id == user_id,
                Booking.status.in_((BOOKED, PENDING)),
                Booking.date >= today,
                Booking.id.not_in(exclude or {0}),
            )
        )
    ).scalar_one()
    return int(singles or 0) + int(series or 0)


async def _day_bookings(
    session: AsyncSession, room_id: int, d: date, exclude: set[int]
) -> list[tuple[Booking, BookingPeriod]]:
    q = (
        select(Booking, BookingPeriod)
        .join(BookingPeriod, BookingPeriod.id == Booking.period_id)
        .where(Booking.room_id == room_id, Booking.date == d, Booking.status.in_((BOOKED, PENDING)))
    )
    return [(b, p) for b, p in (await session.execute(q)).all() if b.id not in exclude]


async def dynamic_violations(
    session: AsyncSession,
    access: Access,
    index: PolicyIndex,
    room: Room,
    term_id: int,
    d: date,
    t_start: time,
    t_end: time,
    user_id: int | None,
    today: date,
    *,
    exclude: set[int] | None = None,
    pending_new: int = 0,
    count_active: bool = True,
) -> list[Violation]:
    policies = index.for_access(access, room, term_id)
    if not policies:
        return []
    ex = set(exclude or ())
    out: list[Violation] = []
    day: list[tuple[Booking, BookingPeriod]] | None = None
    for p in policies:
        if p.max_active_bookings is not None and user_id is not None:
            have = await _active_count(session, user_id, today, ex) + pending_new
            if count_active and have + 1 > p.max_active_bookings:
                out.append(
                    Violation(
                        "max_active",
                        p.effect,
                        f"Kişi başına en fazla {p.max_active_bookings} etkin rezervasyon olabilir; şu an {have} "
                        "etkin rezervasyon var",
                        f"At most {p.max_active_bookings} active booking(s) per person; there are {have} already",
                        p.id,
                        p.name,
                        {"limit": p.max_active_bookings, "active": have},
                    )
                )
        if p.max_duration_minutes or p.buffer_minutes:
            if day is None:
                day = await _day_bookings(session, room.id, d, ex)
        if p.max_duration_minutes and user_id is not None and day is not None:
            mine = sorted(
                [(per.time_start, per.time_end) for b, per in day if b.user_id == user_id] + [(t_start, t_end)]
            )
            # the contiguous block that contains the new booking: neighbours within the 10-minute grid break
            block_s, block_e = t_start, t_end
            changed = True
            while changed:
                changed = False
                for s, e in mine:
                    if _gap(e, block_s) <= 10 and s < block_s:
                        block_s, changed = s, True
                    if _gap(block_e, s) <= 10 and e > block_e:
                        block_e, changed = e, True
            minutes = _gap(block_s, block_e)
            if minutes > p.max_duration_minutes:
                out.append(
                    Violation(
                        "max_duration",
                        p.effect,
                        f"Aynı odada art arda en fazla {p.max_duration_minutes} dakika rezervasyon yapılabilir; bu "
                        f"rezervasyonla {_hm(block_s)}-{_hm(block_e)} ({minutes} dakika) olur",
                        f"At most {p.max_duration_minutes} minutes back to back in one room; with this booking it "
                        f"would be {_hm(block_s)}-{_hm(block_e)} ({minutes} minutes)",
                        p.id,
                        p.name,
                        {"limit": p.max_duration_minutes, "minutes": minutes},
                    )
                )
        if p.buffer_minutes and day is not None:
            for b, per in day:
                if user_id is not None and b.user_id == user_id:
                    continue
                before = _gap(per.time_end, t_start) if per.time_end <= t_start else None
                after = _gap(t_end, per.time_start) if per.time_start >= t_end else None
                close = [g for g in (before, after) if g is not None and g < p.buffer_minutes]
                if close:
                    out.append(
                        Violation(
                            "buffer",
                            p.effect,
                            f"Bu odada iki rezervasyon arasında en az {p.buffer_minutes} dakika olmalı (hazırlık ve "
                            f"toplama); {_hm(per.time_start)}-{_hm(per.time_end)} rezervasyonuna {close[0]} dakika "
                            "kalıyor",
                            f"This room needs at least {p.buffer_minutes} minutes between bookings (setup and "
                            f"teardown); the booking at {_hm(per.time_start)}-{_hm(per.time_end)} is {close[0]} "
                            "minutes away",
                            p.id,
                            p.name,
                            {"limit": p.buffer_minutes, "gap": close[0]},
                        )
                    )
                    break
    return out


def _gap(a: time, b: time) -> int:
    """Minutes from ``a`` to ``b`` (negative when ``b`` is earlier)."""
    return int((datetime.combine(date.min, b) - datetime.combine(date.min, a)).total_seconds() // 60)


# --------------------------------------------------------------------------------------------------
# Enforcement (called by app.services.bookings)
# --------------------------------------------------------------------------------------------------


def refusal(v: Violation) -> Exception:
    from app.services.bookings import BookingError

    return BookingError(
        409,
        f"policy_{v.rule}",
        v.message_en,
        message_en=v.message_en,
        message_tr=v.message_tr,
        policy={"id": v.policy_id, "name": v.policy_name, "rule": v.rule},
        why=v.as_dict(),
    )


def request_need(v: Violation) -> Any:
    from app.services.approvals import Need, rule_snapshot

    return Need(
        None,
        {
            **rule_snapshot(None),
            "source": "exam_period" if v.rule == "exam_period" else "policy",
            "policy_id": v.policy_id,
            "policy_rule": v.rule,
            "reason_tr": v.message_tr,
            "reason_en": v.message_en,
        },
    )


async def violations(
    session: AsyncSession,
    access: Access,
    room: Room,
    term_id: int,
    d: date,
    period: BookingPeriod,
    user_id: int | None,
    *,
    index: PolicyIndex | None = None,
    exclude: set[int] | None = None,
    pending_new: int = 0,
    count_active: bool = True,
) -> list[Violation]:
    from app.services import bookings as bsvc

    idx = index or await PolicyIndex.load(session)
    today = await bsvc.today(session)
    out = await idx.static_violations(session, access, room, term_id, d, period.time_start, period.time_end, today)
    out += await dynamic_violations(
        session,
        access,
        idx,
        room,
        term_id,
        d,
        period.time_start,
        period.time_end,
        user_id,
        today,
        exclude=exclude,
        pending_new=pending_new,
        count_active=count_active,
    )
    return out


async def enforce(
    session: AsyncSession,
    access: Access,
    room: Room,
    term_id: int,
    d: date,
    period: BookingPeriod,
    user_id: int | None,
    need: Any,
    *,
    index: PolicyIndex | None = None,
    exclude: set[int] | None = None,
    pending_new: int = 0,
    count_active: bool = True,
) -> Any:
    """Refuse (409 ``policy_<rule>``) or turn into a request; returns the approval ``need`` to use (unchanged when
    every rule holds)."""
    found = await violations(
        session,
        access,
        room,
        term_id,
        d,
        period,
        user_id,
        index=index,
        exclude=exclude,
        pending_new=pending_new,
        count_active=count_active,
    )
    refuse = [v for v in found if v.effect == "refuse"]
    if refuse:
        raise refusal(refuse[0])
    request = [v for v in found if v.effect == "request"]
    if request and need is None:
        if not (access.can("book_single.create", room) or access.can("book_single.request", room)):
            raise refusal(request[0])
        return request_need(request[0])
    return need


async def effective(
    session: AsyncSession, access: Access, room: Room, term_id: int, d: date | None, period: BookingPeriod | None
) -> dict[str, Any]:
    """``GET /booking-policies/effective``: the rules that apply to the caller in ``room`` and, with a date and a
    period, what they say about that slot (the "Neden?" link)."""
    idx = await PolicyIndex.load(session)
    rules = [policy_out(p) for p in idx.for_access(access, room, term_id)]
    out: dict[str, Any] = {
        "room_id": room.id,
        "term_id": term_id,
        "exempt": exempt(access),
        "policies": rules,
        "exam_period": {"mode": idx.exam["mode"], "exam_room": await idx.is_exam_room(session, term_id, room)},
    }
    if d is not None and period is not None:
        uid = access.user_id
        found = await violations(session, access, room, term_id, d, period, uid, index=idx)
        out["date"], out["period_id"] = d.isoformat(), period.id
        out["violations"] = [v.as_dict() for v in found]
        out["verdict"] = "refuse" if any(v.effect == "refuse" for v in found) else ("request" if found else "book")
    return out
