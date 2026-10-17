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
EXAM_MODES = ("off", "request", "closed", "slots")
#: AS-04 ``slots``: only the room-periods of the term's exam timetable (± ``buffer_periods``) are held
SLOT_EFFECTS = ("request", "refuse")
MAX_BUFFER_PERIODS = 4
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
    out["role_codes"] = sorted({(n.clean_text(str(r)) or "").upper() for r in roles if str(r).strip()})
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
    slots = await get_value(session, "policies", "exam_period_slots") or {}
    if not isinstance(slots, dict):
        slots = {}
    try:
        buffer = int(slots.get("buffer_periods", 1))
    except (TypeError, ValueError):
        buffer = 1
    effect = str(slots.get("effect") or "request")
    return {
        "mode": mode if mode in EXAM_MODES else "off",
        "from_exam_timetable": bool(rooms.get("from_exam_timetable", True)),
        "room_ids": sorted({int(x) for x in rooms.get("room_ids") or []}),
        "buffer_periods": max(0, min(buffer, MAX_BUFFER_PERIODS)),
        "slots_effect": effect if effect in SLOT_EFFECTS else "request",
    }


async def set_exam_settings(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    cur = await exam_settings(session)
    mode = str(data.get("mode", cur["mode"]))
    if mode not in EXAM_MODES:
        raise PolicyError(
            "mode", "mode: off, request, closed or slots", "sınav dönemi kipi: off, request, closed ya da slots"
        )
    buffer = data.get("buffer_periods", cur["buffer_periods"])
    if isinstance(buffer, bool) or not isinstance(buffer, int) or not 0 <= buffer <= MAX_BUFFER_PERIODS:
        raise PolicyError(
            "buffer_periods",
            f"buffer_periods must be 0..{MAX_BUFFER_PERIODS}",
            f"sınav öncesi/sonrası tampon 0 ile {MAX_BUFFER_PERIODS} ders arasında olmalı",
        )
    slots_effect = str(data.get("slots_effect", cur["slots_effect"]))
    if slots_effect not in SLOT_EFFECTS:
        raise PolicyError("slots_effect", "slots_effect: request or refuse", "etki: request (talep) ya da refuse (ret)")
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
        {
            "exam_period_mode": mode,
            "exam_period_rooms": {"from_exam_timetable": from_tt, "room_ids": ids},
            "exam_period_slots": {"buffer_periods": int(buffer), "effect": slots_effect},
        },
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
# AS-04 slot-level exam holds
# --------------------------------------------------------------------------------------------------


def periods_of(t_start: time, t_end: time) -> tuple[int, int] | None:
    """The solver periods (1..18) a clock span overlaps: ``12:40-13:30`` -> (6, 6)."""
    hit = [p.index for p in n.PERIODS if p.start < t_end and t_start < p.end]
    return (min(hit), max(hit)) if hit else None


async def exam_run(session: AsyncSession, term_id: int) -> ScheduleRun | None:
    """The term's exam timetable: the published EXAM run, else the latest finished one."""
    return (
        await session.execute(
            select(ScheduleRun)
            .where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "EXAM", ScheduleRun.status.in_(PUBLISHABLE))
            .order_by(ScheduleRun.is_active.desc(), ScheduleRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@dataclass
class ExamSlotIndex:
    """(room, date) -> the exam spans (start, end period) of the term's exam timetable."""

    run_id: int | None
    buffer: int
    spans: dict[tuple[int, date], list[tuple[int, int]]] = field(default_factory=dict)

    def covers(self, room_id: int, d: date | None, p0: int, p1: int) -> tuple[int, int] | None:
        """The exam span whose held window (± buffer) overlaps periods ``p0..p1`` of ``room_id`` on ``d``."""
        if d is None:
            return None
        for s0, s1 in self.spans.get((room_id, d), []):
            if p0 <= s1 + self.buffer and s0 - self.buffer <= p1:
                return (s0, s1)
        return None

    def held_room_periods(self) -> set[tuple[int, date, int]]:
        out: set[tuple[int, date, int]] = set()
        for (rid, d), spans in self.spans.items():
            for s0, s1 in spans:
                for p in range(max(1, s0 - self.buffer), min(n.PERIODS_PER_DAY, s1 + self.buffer) + 1):
                    out.add((rid, d, p))
        return out


async def exam_slot_index(session: AsyncSession, term_id: int, buffer_periods: int) -> ExamSlotIndex:
    from app.models import Term
    from app.services.calendar import date_for

    run = await exam_run(session, term_id)
    idx = ExamSlotIndex(run.id if run is not None else None, max(0, int(buffer_periods)))
    if run is None:
        return idx
    term = await session.get(Term, term_id)
    weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term_id))).scalars())
    q = select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
    for a in (await session.execute(q)).scalars():
        d = a.date
        if d is None and term is not None:
            wk = a.week or (int(a.weeks[0]) if a.weeks else None)
            d = date_for(term, int(wk), a.day, weeks_rows) if wk else None
        if d is None:
            continue
        for rid in a.room_ids or []:
            idx.spans.setdefault((int(rid), d), []).append((int(a.start_period), int(a.end_period)))
    return idx


async def slot_hold_summary(session: AsyncSession, term_id: int, buffer_periods: int = 1) -> dict[str, Any]:
    """Room-periods ``slots`` holds against the whole-week closure of ``closed`` (backtest B7, the draft hold of
    AS-11): the closure is every exam room on every day of the exam weeks (EXAM / MAKEUP weeks, else the weeks the
    exam dates fall in) x 18 periods."""
    idx = await exam_slot_index(session, term_id, buffer_periods)
    held = idx.held_room_periods()
    rooms = sorted({rid for rid, _d in idx.spans})
    weeks = await exam_weeks(session, term_id)
    if not weeks:
        mondays = sorted({d - timedelta(days=d.weekday()) for _r, d in idx.spans})
        weeks = [(m, m + timedelta(days=6), "") for m in mondays]
    days = sorted({d0 + timedelta(days=i) for d0, _d1, _l in weeks for i in range(7)})
    closed = len(rooms) * len(days) * n.PERIODS_PER_DAY
    held_in = {(r, d, p) for r, d, p in held if d in set(days)} if days else held
    return {
        "exam_run_id": idx.run_id,
        "buffer_periods": idx.buffer,
        "rooms": len(rooms),
        "days": len(days),
        "held_room_periods": len(held_in),
        "closed_room_periods": closed,
        "freed_room_periods": max(0, closed - len(held_in)),
        "exams": sum(len(v) for v in idx.spans.values()),
    }


# --------------------------------------------------------------------------------------------------
# AS-04 season-profile overlays
# --------------------------------------------------------------------------------------------------


@dataclass
class OverlayRule:
    """One overlay of the active season profile that applies to a booking's date and room."""

    policy: BookingPolicy  # transient (never added to the session): the limits in booking-policy columns
    raw: dict[str, Any]
    profile_label: str
    profile_name: dict[str, str]
    period_kind: str

    def describe(self) -> dict[str, Any]:
        from app.services.seasons import KIND_LABEL

        tr, en = KIND_LABEL.get(self.period_kind, (self.period_kind, self.period_kind))
        return {
            "profile": self.profile_label,
            "name": self.profile_name,
            "period_kind": self.period_kind,
            "period_label": {"tr": tr, "en": en},
            "overlay": dict(self.raw),
            "summary": describe(self.policy),
        }

    def prefix(self, v: Violation) -> Violation:
        from app.services.seasons import KIND_LABEL

        tr, en = KIND_LABEL.get(self.period_kind, (self.period_kind, self.period_kind))
        v.message_tr = f"{self.profile_name['tr']} profili ({tr}): {v.message_tr}"
        v.message_en = f"{self.profile_name['en']} profile ({en}): {v.message_en}"
        v.policy_name = f"{self.profile_name['tr']} ({self.profile_label})"
        v.data = {**v.data, "source": "season_profile", "profile": self.profile_label, "period_kind": self.period_kind}
        return v


def _overlay_scope_ok(raw: dict[str, Any], room: Room) -> bool:
    scope = str(raw.get("scope") or "all")
    kind, _sep, value = scope.partition(":")
    if kind == "all":
        return True
    if kind == "tag":
        return value in [n.tr_upper(str(t)) for t in (room.tags or [])]
    if kind == "building":
        return (room.code or "")[:1].upper() == value[:1]
    if kind == "room":
        return (room.code or "").replace(" ", "").upper() == value
    return False


def _transient_policy(raw: dict[str, Any], name: str) -> BookingPolicy:
    return BookingPolicy(
        id=None,
        name=name[:120],
        enabled=True,
        scope_type="all",
        role_codes=[],
        effect=str(raw.get("effect") or "refuse"),
        min_notice_workdays=raw.get("min_notice_workdays"),
        max_advance_days=raw.get("max_advance_days"),
        max_duration_minutes=raw.get("max_duration_minutes"),
        max_active_bookings=raw.get("max_active_bookings"),
        buffer_minutes=raw.get("buffer_minutes"),
        quiet_hours=[],
        blackouts=[],
    )


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
    _earliest: dict[tuple[int, date, int], date] = field(default_factory=dict)
    #: AS-04: (term, date) -> (period kind, profile, its overlays); term -> calendar rows; term -> exam slots
    _season: dict[tuple[int, date], tuple[str, Any]] = field(default_factory=dict)
    _calendar: dict[int, Any] = field(default_factory=dict)
    _slots: dict[int, ExamSlotIndex] = field(default_factory=dict)
    _profiles: list[Any] | None = None

    async def season_of_date(self, session: AsyncSession, term_id: int, d: date) -> tuple[str, Any]:
        """(period kind of ``d``, the season profile that applies then or None)."""
        from app.models import Term
        from app.services import seasons

        key = (term_id, d)
        if key not in self._season:
            term = await session.get(Term, term_id)
            if term is None:
                self._season[key] = ("LECTURE", None)
            else:
                if term_id not in self._calendar:
                    self._calendar[term_id] = await seasons.load_calendar(session, term)
                weeks_rows, holidays, segs = self._calendar[term_id]
                kind = seasons.period_kind_on(term, d, weeks_rows, holidays, segs)
                if self._profiles is None:
                    self._profiles = await seasons.active_profiles(session)
                self._season[key] = (kind, seasons.pick_profile(self._profiles, seasons.season_of(term), kind))
        return self._season[key]

    async def overlays_for(
        self, session: AsyncSession, access: Access | None, room: Room, term_id: int, d: date
    ) -> list[OverlayRule]:
        """The active season profile's overlays for ``d``'s period kind and ``room`` (none for exempt users)."""
        if access is not None and exempt(access):
            return []
        kind, profile = await self.season_of_date(session, term_id, d)
        if profile is None or not profile.booking_overlays:
            return []
        default_kinds = {str(a.get("period_kind") or "*").upper() for a in profile.applies_to}
        out: list[OverlayRule] = []
        for raw in profile.booking_overlays:
            kinds = set(raw.get("period_kinds") or default_kinds)
            if "*" not in kinds and kind not in kinds:
                continue
            if not _overlay_scope_ok(raw, room):
                continue
            out.append(OverlayRule(_transient_policy(raw, profile.name["tr"]), raw, profile.label, profile.name, kind))
        return out

    async def exam_slots(self, session: AsyncSession, term_id: int) -> ExamSlotIndex:
        if term_id not in self._slots:
            self._slots[term_id] = await exam_slot_index(session, term_id, int(self.exam.get("buffer_periods", 1)))
        return self._slots[term_id]

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
        self,
        session: AsyncSession,
        access: Access,
        room: Room,
        term_id: int,
        d: date,
        t_start: time | None = None,
        t_end: time | None = None,
        mode: str | None = None,
    ) -> Violation | None:
        mode = mode or self.exam["mode"]
        if mode == "off" or exam_exempt(access):
            return None
        if mode == "slots":
            return await self._slot_violation(session, room, term_id, d, t_start, t_end)
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

    async def _slot_violation(
        self, session: AsyncSession, room: Room, term_id: int, d: date, t_start: time | None, t_end: time | None
    ) -> Violation | None:
        span = periods_of(t_start, t_end) if t_start is not None and t_end is not None else (1, n.PERIODS_PER_DAY)
        if span is None:
            return None
        idx = await self.exam_slots(session, term_id)
        hit = idx.covers(room.id, d, span[0], span[1])
        if hit is None:
            return None
        effect = str(self.exam.get("slots_effect") or "request")
        b = idx.buffer
        window_tr = f"{hit[0]}.–{hit[1]}. ders" if hit[0] != hit[1] else f"{hit[0]}. ders"
        window_en = f"periods {hit[0]}–{hit[1]}" if hit[0] != hit[1] else f"period {hit[0]}"
        data = {"exam_slot": {"start": hit[0], "end": hit[1], "buffer": b}, "exam_run_id": idx.run_id}
        buf_tr = f" (öncesi ve sonrası {b} ders dahil)" if b else ""
        buf_en = f" ({b} period(s) before and after included)" if b else ""
        if effect == "request":
            return Violation(
                "exam_period",
                "request",
                f"{room.display_name} {d:%d.%m.%Y} günü {window_tr} sınavda{buf_tr}; bu saat yalnızca talep ile "
                "ayrılır, talebiniz onaya gider",
                f"{room.display_name} holds an exam on {d:%d.%m.%Y}, {window_en}{buf_en}; this time can only be "
                "requested and your request goes to the approvers",
                data=data,
            )
        return Violation(
            "exam_period",
            "refuse",
            f"{room.display_name} {d:%d.%m.%Y} günü {window_tr} sınavda{buf_tr}; bu saat rezervasyona kapalıdır",
            f"{room.display_name} holds an exam on {d:%d.%m.%Y}, {window_en}{buf_en}; this time is closed for bookings",
            data=data,
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
        out = await self._static_for(session, self.for_access(access, room, term_id), term_id, d, t_start, t_end, today)
        overlays = await self.overlays_for(session, access, room, term_id, d)
        for o in overlays:
            out += [o.prefix(v) for v in await self._static_for(session, [o.policy], term_id, d, t_start, t_end, today)]
        hold = next((str(o.raw["exam_hold"]) for o in overlays if o.raw.get("exam_hold")), None)
        ev = await self.exam_violation(session, access, room, term_id, d, t_start, t_end, mode=hold)
        if ev is not None:
            if hold is not None:
                ev = next(o for o in overlays if o.raw.get("exam_hold")).prefix(ev)
            out.append(ev)
        return out

    async def _static_for(
        self,
        session: AsyncSession,
        policies: list[BookingPolicy],
        term_id: int,
        d: date,
        t_start: time,
        t_end: time,
        today: date,
    ) -> list[Violation]:
        from app.services.approvals import add_workdays

        out: list[Violation] = []
        for p in policies:
            if p.min_notice_workdays:
                key = (term_id, today, p.min_notice_workdays)
                if key not in self._earliest:
                    self._earliest[key] = await add_workdays(session, term_id, today, p.min_notice_workdays)
                earliest = self._earliest[key]
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
    ex = set(exclude or ())
    out = await _dynamic_for(
        session,
        index.for_access(access, room, term_id),
        room,
        d,
        t_start,
        t_end,
        user_id,
        today,
        ex,
        pending_new,
        count_active,
        None,
    )
    for o in await index.overlays_for(session, access, room, term_id, d):
        scoped = await _scoped_active_count(session, index, o, term_id, user_id, today, ex) if user_id else 0
        found = await _dynamic_for(
            session, [o.policy], room, d, t_start, t_end, user_id, today, ex, pending_new, count_active, scoped
        )
        out += [o.prefix(v) for v in found]
    return out


async def _scoped_active_count(
    session: AsyncSession,
    index: PolicyIndex,
    o: OverlayRule,
    term_id: int,
    user_id: int,
    today: date,
    exclude: set[int],
) -> int:
    """Active future bookings of ``user_id`` inside an overlay's scope (rooms) and period kind (dates): a
    "PC labs in exam weeks" cap counts the person's exam-week PC-lab bookings only (a series counts once)."""
    q = (
        select(Booking, Room)
        .join(Room, Room.id == Booking.room_id)
        .where(Booking.user_id == user_id, Booking.status.in_((BOOKED, PENDING)), Booking.date >= today)
    )
    seen_series: set[int] = set()
    n_active = 0
    for b, r in (await session.execute(q)).all():
        if b.id in exclude or not _overlay_scope_ok(o.raw, r):
            continue
        kind, _profile = await index.season_of_date(session, b.term_id or term_id, b.date)
        if kind != o.period_kind:
            continue
        if b.series_id is not None:
            if b.series_id in seen_series:
                continue
            seen_series.add(b.series_id)
        n_active += 1
    return n_active


async def _dynamic_for(
    session: AsyncSession,
    policies: list[BookingPolicy],
    room: Room,
    d: date,
    t_start: time,
    t_end: time,
    user_id: int | None,
    today: date,
    ex: set[int],
    pending_new: int,
    count_active: bool,
    active_override: int | None,
) -> list[Violation]:
    if not policies:
        return []
    out: list[Violation] = []
    day: list[tuple[Booking, BookingPeriod]] | None = None
    for p in policies:
        if p.max_active_bookings is not None and user_id is not None:
            base = active_override if active_override is not None else await _active_count(session, user_id, today, ex)
            have = base + pending_new
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
    approval = await approval_state(session, access, room, term_id)
    out["approval"] = approval
    out["season_overlays"] = (
        [o.describe() for o in await idx.overlays_for(session, None, room, term_id, d)] if d is not None else []
    )
    if d is not None and period is not None:
        uid = access.user_id
        found = await violations(session, access, room, term_id, d, period, uid, index=idx)
        out["date"], out["period_id"] = d.isoformat(), period.id
        out["violations"] = [v.as_dict() for v in found]
        if any(v.effect == "refuse" for v in found):
            out["verdict"] = "refuse"
        elif found or approval["action"] == "request":
            # T-R1-10: approval-first (``bookings.approval_mode = all``) or the room's approval rule turns the slot
            # into a request even when no booking policy fires; the reason names that setting
            out["verdict"] = "request"
            if approval["action"] == "request":
                out["violations"].append(
                    Violation(approval["source"], "request", approval["message_tr"], approval["message_en"]).as_dict()
                )
        else:
            out["verdict"] = "book"
    return out


async def approval_state(session: AsyncSession, access: Access, room: Room, term_id: int | None) -> dict[str, Any]:
    """Does a booking by ``access`` in ``room`` go to the approvers (``action = request``), and why (``source``):
    ``approval_mode`` (every request is approved first, "Rezervasyon onayı: Her talep önce onaya"), ``approval_rule``
    (the room's own approval rule) or ``approver`` (the caller may only request; the room has designated approvers).
    ``first``: approval-first applies to the caller in every room (the grid and the free-slot list say "Talep et")."""
    from app.services import approvals

    rules = await approvals.RulesIndex.load(session)
    action = await rules.mode_for(session, access, room, term_id)
    rule = rules.rule_for(room, term_id)
    first = rules.mode == approvals.MODE_ALL and not approvals.skips_approval(access)
    if action != "request":
        source, tr, en = None, "", ""
    elif rule is not None:
        source = "approval_rule"
        tr = f"Onaylayıcılara gider: {room.display_name} için onay kuralı var; talebiniz onaylanınca rezerve edilir."
        en = f"Goes to the approvers: {room.display_name} has an approval rule; it is booked once approved."
    elif first:
        source = "approval_mode"
        tr = (
            "Onaylayıcılara gider: Rezervasyon onayı ayarı «Her talep önce onaya» olarak açık; "
            "talebiniz onaylanınca rezerve edilir."
        )
        en = "Goes to the approvers: Booking approval is set to «Every request first»; it is booked once approved."
    else:
        source = "approver"
        tr = "Onaylayıcılara gider: bu odada yalnız talep oluşturabilirsiniz; onaylanınca rezerve edilir."
        en = "Goes to the approvers: you may only request this room; it is booked once approved."
    return {
        "mode": rules.mode,
        "first": first,
        "action": action,
        "source": source,
        "message_tr": tr,
        "message_en": en,
    }
