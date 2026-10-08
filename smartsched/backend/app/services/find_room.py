"""T1 "find me a room" (docs/product/booking-enhancements.md §4.2): a deterministic free-room search.

Given dates (one date, a list, a date range with weekdays, or a weekday in term weeks), a slot on the 18-period
grid (``start``/``end`` as ``HH:MM``, ``HH.MM`` or a period number, or ``start`` + a duration, optionally sliding
up to ``window_end``), a headcount, required features (typed features of P10 or solver tags), buildings and free
text, it answers every room the caller may view with a status and the reasons, free rooms ranked by fit:

* occupancy = the published timetable (active runs) + blocks + bookings, including PENDING requests that hold
  their slot (``app.services.bookings.booking_occupancy``), loaded once for all rooms and dates;
* holidays, dates outside the term and dates without a timetable week are closed (the count shows them);
* room ACL: only rooms with ``room.view`` (role or room ACL); ``action`` says whether the caller can book,
  must request approval (P1) or can only look;
* score = wasted seats ``(capacity - headcount) / capacity`` + 0.15 per solver tag the room has but the search
  did not ask for (do not give the PC lab to a lecture) - 0.2 when the room is in the preferred building (given,
  or the building of most of the caller's bookings in the last 90 days); ties: room order, Turkish name;
* fewer than 3 free rooms: alternatives (same rooms ±1/±2 periods, other weekdays of that week, near misses
  with ≤ 10 % fewer seats or one feature missing), each with a reason.

Text matching is Turkish-aware (``tr_casefold``: İ/ı, NBSP); times accept dots (``10.10``)."""

from __future__ import annotations

import re
import time as _time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import Booking, Building, Program, User
from app.models.booking import BOOKED
from app.models.catalog import Room
from app.services import bookings as bsvc
from app.services import rooms_features as feat
from app.services.bookings_calendar import CalendarError, TermInfo, date_infos, resolve_term
from app.services.bookings_collation import tr_sort_key
from app.services.bookings_perms import Access
from app.services.calendar import date_for

GRID_START, GRID_END = n.PERIODS[0].start, n.PERIODS[-1].end
MAX_DATES = 120
SURPLUS_PENALTY = 0.15
BUILDING_BONUS = 0.2
DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


class FindError(Exception):
    def __init__(self, status: int, code: str, message: str, message_tr: str, **data: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr, self.data = status, code, message, message_tr, data

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "message_tr": self.message_tr, **self.data}


@dataclass
class FeatureReq:
    field: Any  # feature id or name
    op: str | None = None
    value: Any = None


@dataclass
class FindQuery:
    term_id: int | None = None
    dates: list[date] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    weekdays: list[int] = field(default_factory=list)
    weekday: int | None = None
    weeks: list[int] = field(default_factory=list)
    start: str | int | None = None
    end: str | int | None = None
    duration_periods: int | None = None
    duration_min: int | None = None
    window_end: str | int | None = None
    headcount: int = 0
    purpose: str = "teaching"  # teaching | exam
    features: list[FeatureReq] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    buildings: list[str] = field(default_factory=list)
    preferred_building: str | None = None
    room_group_id: int | None = None
    text: str | None = None
    include_busy: bool = True
    include_requestable: bool = True
    flex_periods: int = 2
    other_days: bool = False
    limit: int = 50


def _reason(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# --------------------------------------------------------------------------------------------------
# Query resolution
# --------------------------------------------------------------------------------------------------


def _bad_time(value: Any) -> FindError:
    return FindError(
        422,
        "time_outside_grid",
        f"{value} is outside the 08:30-22:50 teaching day",
        f"{value} saati 08:30-22:50 ders gününün dışında",
    )


def _clock(value: str | int | None, kind: str) -> tuple[int | None, time | None]:
    """A period number (1..18) or a clock time (``10:10``, ``10.10``, NBSP tolerated) -> (period, time)."""
    if value is None:
        return None, None
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit() and len(value.strip()) <= 2):
        p = int(value)
        if not 1 <= p <= n.PERIODS_PER_DAY:
            raise FindError(422, "period", f"period {p} is not on the grid (1-18)", f"P{p} ders saatlerinde yok (1-18)")
        return p, None
    t = n.parse_time(value)
    if t is None:
        raise FindError(422, "time", f"cannot read the time {value!r}", f"{value!r} saati okunamadı")
    if t < GRID_START or t > GRID_END or (kind == "start" and t >= GRID_END):
        raise _bad_time(f"{t:%H:%M}")
    m = n.time_to_period(t, kind)
    if m.period is None:
        raise _bad_time(f"{t:%H:%M}")
    return m.period, t


def resolve_periods(q: FindQuery) -> tuple[int, int, int]:
    """(first start, last start, duration) on the grid; ``first start == last start`` without a window."""
    s, s_time = _clock(q.start, "start")
    if s is None:
        raise FindError(422, "start", "a start time or period is needed", "başlangıç saati gerekli")
    e, e_time = _clock(q.end, "end") if q.end is not None else (None, None)
    if s_time is not None and e_time is not None:
        rng = n.time_range_to_periods(s_time, e_time)
        if rng.start_period is None or rng.end_period is None:
            raise FindError(422, "time_range", "; ".join(rng.warnings), "saat aralığı geçersiz")
        s, e = rng.start_period, rng.end_period
    if q.duration_periods is not None:
        dur = q.duration_periods
    elif q.duration_min is not None:
        start_p = n.PERIODS[s - 1]
        need = start_p.start.hour * 60 + start_p.start.minute + q.duration_min
        dur = next(
            (p.index - s + 1 for p in n.PERIODS[s - 1 :] if p.end.hour * 60 + p.end.minute >= need),
            n.PERIODS_PER_DAY - s + 2,
        )
    elif e is not None:
        dur = e - s + 1
    else:
        dur = 1
    if dur < 1:
        raise FindError(422, "duration", "the end is before the start", "bitiş başlangıçtan önce")
    last = s
    if q.window_end is not None:
        w, _ = _clock(q.window_end, "end")
        assert w is not None
        last = w - dur + 1
        if last < s:
            raise FindError(422, "window", "the window is shorter than the duration", "aralık süreden kısa")
    if last + dur - 1 > n.PERIODS_PER_DAY:
        raise _bad_time(f"P{last + dur - 1}")
    return s, last, dur


def resolve_dates(q: FindQuery, info: TermInfo | None) -> list[date]:
    out: set[date] = set(q.dates)
    if q.date_from is not None:
        end = q.date_to or q.date_from
        if (end - q.date_from).days > 366:
            raise FindError(422, "range", "the date range is longer than a year", "tarih aralığı bir yıldan uzun")
        d = q.date_from
        while d <= end:
            if not q.weekdays or d.isoweekday() in q.weekdays:
                out.add(d)
            d += timedelta(days=1)
    if q.weekday is not None:
        if info is None:
            raise FindError(422, "term", "weekday + weeks needs a term", "gün + hafta için dönem gerekli")
        weeks = (
            q.weeks or [w.index for w in info.weeks if w.kind != "HOLIDAY"] or list(range(1, info.term.week_count + 1))
        )
        for w in weeks:
            d2 = date_for(info.term, w, q.weekday, info.weeks)
            if d2 is not None:
                out.add(d2)
    if not out:
        raise FindError(422, "no_dates", "choose a date, a date range or a weekday", "tarih ya da gün seçin")
    if len(out) > MAX_DATES:
        raise FindError(422, "too_many_dates", f"at most {MAX_DATES} dates", f"en çok {MAX_DATES} tarih")
    return sorted(out)


async def _building_codes(session: AsyncSession, texts: list[str]) -> set[str]:
    """``A``, ``a blok``, ``A Blok'ta``, ``C BLOĞU`` -> building codes (Turkish-insensitive)."""
    buildings = list((await session.execute(select(Building))).scalars())
    out: set[str] = set()
    for raw in texts:
        text = n.clean_text(raw)
        if not text:
            continue
        key = n.tr_casefold(text)
        hit = next((b.code for b in buildings if key in (n.tr_casefold(b.code), n.tr_casefold(b.name))), None)
        if hit is None:
            m = re.match(r"^\s*([a-zçğıöşü])(?:\s*blo[kğ]\w*|\s*$|['’]\w*)", key)
            if m:
                hit = n.tr_upper(m.group(1))
        if hit is None:
            raise FindError(422, "building", f"unknown building {raw!r}", f"{raw!r} binası bulunamadı")
        out.add(hit)
    return out


def _tags_from_words(words: list[str]) -> set[str]:
    out = set()
    for w in words:
        key = n.tr_casefold(w)
        for tag, syns in feat.TAG_SYNONYMS.items():
            if key == tag.lower() or key in syns:
                out.add(tag)
        if not any(key in syns or key == tag.lower() for tag, syns in feat.TAG_SYNONYMS.items()):
            out.add(feat.ascii_upper(w.strip()).replace(" ", "_"))
    return out


async def _usual_building(session: AsyncSession, access: Access, today: date) -> str | None:
    since = datetime.combine(today - timedelta(days=90), time())
    q = (
        select(Room.building_id)
        .join(Booking, Booking.room_id == Room.id)
        .where(Booking.user_id == access.user_id, Booking.created_at >= since, Booking.status == BOOKED)
    )
    counts = Counter(bid for bid in (await session.execute(q)).scalars() if bid is not None)
    if not counts:
        return None
    (bid, top), *rest = counts.most_common(2)
    if rest and rest[0][1] == top:
        return None
    b = await session.get(Building, bid)
    return b.code if b else None


# --------------------------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------------------------


@dataclass
class _Cand:
    room: Room
    building: str | None
    cap: int
    static: str | None = None  # capacity_unknown | too_small | feature_missing
    missing: list[str] = field(default_factory=list)
    short_pct: float = 0.0


def _free_on(occ: list[bsvc.Held], s: int, e: int) -> bsvc.Held | None:
    return next((h for h in occ if h.overlaps(s, e)), None)


async def _busy_label(session: AsyncSession, access: Access, held: bsvc.Held, room: Room) -> str:
    if held.kind != "booking":
        return held.label or ("Ders" if held.kind == "timetable" else "Blok")
    b = await session.get(Booking, held.ref_id)
    if b is None:
        return "Rezervasyon"
    parts = ["Rezervasyon" if b.status == BOOKED else "Onay bekleyen talep"]
    if bsvc.can_view_user(access, b, room):
        u = await session.get(User, b.user_id) if b.user_id else None
        if u is not None:
            parts.append(u.full_name or u.username or u.email or "")
        if b.department_id:
            dep = await session.get(Program, b.department_id)
            if dep is not None:
                parts.append(dep.name)
    return " · ".join(p for p in parts if p)


async def find_rooms(session: AsyncSession, access: Access, q: FindQuery) -> dict[str, Any]:
    from app.services import approvals

    t0 = _time.perf_counter()
    view_all = access.can("system.view_all_sessions")
    first = sorted(q.dates)[0] if q.dates else q.date_from
    info: TermInfo | None = None
    try:
        if first is not None:
            info = await resolve_term(session, first, q.term_id, view_all=view_all)
        elif q.term_id is not None:
            from app.models import Term
            from app.services.bookings_calendar import term_info

            term = await session.get(Term, q.term_id)
            info = await term_info(session, term) if term else None
            if info is not None and not (view_all or info.is_selectable):
                raise CalendarError(f"term {info.term.code} is not open for bookings")
    except CalendarError as exc:
        raise FindError(409, "calendar", str(exc), "bu tarih için açık bir dönem yok") from exc
    dates = resolve_dates(q, info)
    if info is None:
        try:
            info = await resolve_term(session, dates[0], None, view_all=view_all)
        except CalendarError as exc:
            raise FindError(409, "calendar", str(exc), "bu tarih için açık bir dönem yok") from exc
    s0, s1, dur = resolve_periods(q)
    dinfos = await date_infos(session, info, dates)
    open_dates = [d for d in dates if dinfos[d].open]
    closed = [
        {"date": d.isoformat(), "reason": dinfos[d].reason, "holiday": dinfos[d].holiday}
        for d in dates
        if not dinfos[d].open
    ]

    # candidates: rooms the caller may view (role or ACL), bookable, CRBS ungrouped rule, filters
    rooms = await bsvc.visible_rooms(session, access, q.room_group_id)
    bcodes = {b.id: b.code for b in (await session.execute(select(Building))).scalars()}
    if q.buildings:
        wanted_b = await _building_codes(session, q.buildings)
        rooms = [r for r in rooms if bcodes.get(r.building_id or 0, r.code[:1]) in wanted_b]
    preferred = None
    if q.preferred_building:
        preferred = next(iter(await _building_codes(session, [q.preferred_building])))
    else:
        preferred = await _usual_building(session, access, await bsvc.today(session))
    fields = await feat.catalogue(session)
    try:
        crit = [feat.criterion(fields, fr.field, fr.op, fr.value) for fr in q.features]
    except feat.FeatureError as exc:
        raise FindError(exc.status, exc.code, exc.message, exc.message) from exc
    tags = _tags_from_words(q.tags)
    vals = await feat.room_values(session, rooms, fields)
    if q.text:
        words = [w for w in n.tr_casefold(q.text).split(" ") if w]

        def hay(r: Room) -> str:
            names = [f.name for f in fields if feat.truthy(f, vals[r.id].get(f.id))]
            syn = [s for t in (r.tags or []) for s in feat.TAG_SYNONYMS.get(str(t), (str(t),))]
            return n.tr_casefold(" ".join([r.code, r.display_name, r.location or "", r.notes or "", *names, *syn]))

        rooms = [r for r in rooms if all(w in hay(r) for w in words)]

    exam = q.purpose == "exam"
    cands: list[_Cand] = []
    for r in rooms:
        cap = (r.exam_capacity if exam else r.capacity) or 0
        c = _Cand(r, bcodes.get(r.building_id or 0, r.code[:1]), cap)
        missing = [cr.label() for cr in crit if not feat.matches(cr, vals[r.id].get(cr.field.id))]
        missing += [t for t in sorted(tags) if t not in (r.tags or [])]
        c.missing = missing
        if missing:
            c.static = "feature_missing"
        elif cap <= 0 and q.headcount > 0:
            c.static = "capacity_unknown"
        elif q.headcount > cap:
            c.static = "too_small"
            c.short_pct = (q.headcount - cap) / q.headcount
        cands.append(c)

    ids = {c.room.id for c in cands}
    if open_dates:
        d0, d1 = min(open_dates), max(open_dates)
        if q.other_days:
            d0, d1 = d0 - timedelta(days=d0.isoweekday() - 1), d1 + timedelta(days=7 - d1.isoweekday())
        bocc = await bsvc.booking_occupancy(session, ids, d0, d1)
        tocc = await bsvc.timetable_occupancy(session, ids, d0, d1)
    else:
        bocc, tocc = {}, {}

    def holders(rid: int, d: date) -> list[bsvc.Held]:
        return [*bocc.get((rid, d), []), *tocc.get((rid, d), [])]

    rules = await approvals.RulesIndex.load(session)

    def scan(c: _Cand, ds: list[date], first_s: int, last_s: int) -> tuple[int | None, dict[date, bsvc.Held | None]]:
        """Earliest start in [first_s, last_s] free on the most dates (all, ideally)."""
        best: tuple[int | None, dict[date, bsvc.Held | None]] = (None, {})
        best_free = -1
        for s in range(first_s, last_s + 1):
            per = {d: _free_on(holders(c.room.id, d), s, s + dur - 1) for d in ds}
            free = sum(1 for h in per.values() if h is None)
            if free > best_free:
                best, best_free = (s, per), free
            if free == len(ds):
                break
        return best

    results: list[dict[str, Any]] = []
    free_count = 0
    for c in cands:
        r = c.room
        mode = await rules.mode_for(session, access, r, info.term.id)
        start, per = scan(c, open_dates, s0, s1) if open_dates else (s0, {})
        start = start or s0
        busy_n = sum(1 for h in per.values() if h is not None)
        free_n = len(per) - busy_n
        if c.static:
            status = c.static
        elif not open_dates:
            status = "closed"
        elif busy_n == 0:
            status = "requestable" if mode == "request" else "free"
        elif free_n == 0:
            status = "busy"
        else:
            status = "partial"
        if status == "requestable" and not q.include_requestable:
            continue
        reasons: list[dict[str, str]] = []
        waste = None
        score = 0.0
        if c.cap > 0 and q.headcount > 0 and c.cap >= q.headcount:
            waste = (c.cap - q.headcount) / c.cap
            score += waste
            reasons.append(
                _reason(
                    f"Kapasite {c.cap}: {q.headcount} kişi için %{round(waste * 100)} boş koltuk",
                    f"Capacity {c.cap}: {round(waste * 100)}% empty seats for {q.headcount}",
                )
            )
        surplus = sorted(str(t) for t in (r.tags or []) if str(t) not in tags)
        if surplus:
            score += SURPLUS_PENALTY * len(surplus)
            reasons.append(
                _reason(
                    f"{', '.join(surplus)} özellikli oda; istenmedi, sona alındı",
                    f"{', '.join(surplus)} room not asked for; ranked lower",
                )
            )
        if preferred and c.building == preferred:
            score -= BUILDING_BONUS
            reasons.append(_reason(f"Tercih edilen bina ({preferred})", f"Preferred building ({preferred})"))
        if status == "too_small":
            reasons.insert(
                0, _reason(f"{c.cap} kişilik; {q.headcount} kişi sığmaz", f"Seats {c.cap}; {q.headcount} do not fit")
            )
        elif status == "capacity_unknown":
            reasons.insert(0, _reason("Kapasite bilinmiyor", "Capacity unknown"))
        elif status == "feature_missing":
            reasons.insert(0, _reason("Eksik: " + ", ".join(c.missing), "Missing: " + ", ".join(c.missing)))
        elif status == "requestable":
            reasons.insert(0, _reason("Onay gerekli: talep oluşturulur", "Needs approval: a request is created"))
        elif status == "partial":
            reasons.insert(0, _reason(f"{free_n}/{len(per)} tarih boş", f"free on {free_n} of {len(per)} dates"))
        busy_with = None
        if status in ("busy", "partial"):
            first_held = next(h for h in per.values() if h is not None)
            busy_with = await _busy_label(session, access, first_held, r)
            if status == "busy":
                reasons.insert(0, _reason(f"Dolu: {busy_with}", f"Busy: {busy_with}"))
        item: dict[str, Any] = {
            "room_id": r.id,
            "code": r.code,
            "name": r.display_name,
            "building": c.building,
            "capacity": r.capacity or 0,
            "exam_capacity": r.exam_capacity or 0,
            "tags": list(r.tags or []),
            "features": [f.name for f in fields if feat.truthy(f, vals[r.id].get(f.id)) and (f.public is not False)],
            "status": status,
            "action": mode if status in ("free", "requestable", "partial") else "none",
            "start_period": start,
            "end_period": start + dur - 1,
            "reason": reasons[0] if reasons else _reason("Uygun", "Fits"),
            "reasons": reasons,
            "busy_with": busy_with,
            "fit": {"waste_pct": round(waste * 100) if waste is not None else None, "score": round(score, 4)},
            "free_dates": free_n,
            "open_dates": len(per),
            "pos": r.pos or 0,
        }
        if len(dates) > 1:
            item["per_date"] = [
                {"date": d.isoformat(), "status": "closed", "reason": dinfos[d].reason}
                if d not in per
                else {"date": d.isoformat(), "status": "free" if per[d] is None else "busy"}
                for d in dates
            ]
        if status in ("free", "requestable"):
            free_count += 1
        results.append(item)

    rank = {
        "free": 0,
        "requestable": 0,
        "partial": 1,
        "busy": 2,
        "too_small": 3,
        "feature_missing": 4,
        "capacity_unknown": 5,
        "closed": 6,
    }
    results.sort(key=lambda x: (rank[x["status"]], x["fit"]["score"], x["pos"], tr_sort_key(x["name"]), x["room_id"]))
    if not q.include_busy:
        results = [x for x in results if x["status"] in ("free", "requestable", "partial")]

    alternatives: list[dict[str, Any]] = []
    if free_count < 3 and open_dates:
        alternatives = await _alternatives(session, access, q, cands, open_dates, s0, s1, dur, holders, rules, info)
    for x in results:
        x.pop("pos", None)
    return {
        "query_echo": _echo(q),
        "term_id": info.term.id,
        "slots": [{"date": d.isoformat(), "start_period": s0, "end_period": s1 + dur - 1} for d in open_dates],
        "duration_periods": dur,
        "time": {"start": f"{n.PERIODS[s0 - 1].start:%H:%M}", "end": f"{n.PERIODS[s1 + dur - 2].end:%H:%M}"},
        "closed_dates": closed,
        "preferred_building": preferred,
        "summary": {
            "rooms": len(results),
            "free": free_count,
            "dates": len(dates),
            "open_dates": len(open_dates),
            "text_tr": f"{free_count} boş oda · {len(open_dates)}/{len(dates)} tarih açık",
            "text_en": f"{free_count} free rooms · {len(open_dates)}/{len(dates)} dates open",
        },
        "results": results[: max(1, q.limit)],
        "alternatives": alternatives,
        "timing_ms": round((_time.perf_counter() - t0) * 1000, 1),
    }


async def _alternatives(
    session: AsyncSession,
    access: Access,
    q: FindQuery,
    cands: list[_Cand],
    dates: list[date],
    s0: int,
    s1: int,
    dur: int,
    holders: Any,
    rules: Any,
    info: TermInfo,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def all_free(c: _Cand, ds: list[date], s: int) -> bool:
        return all(_free_on(holders(c.room.id, d), s, s + dur - 1) is None for d in ds)

    # rooms that fit but are taken at the asked time (free ones are results already)
    fits = [c for c in cands if c.static is None and not all_free(c, dates, s0)]

    # same rooms, earlier / later
    for shift in [1, -1, 2, -2][: max(0, min(q.flex_periods, 2)) * 2]:
        s = s0 + shift
        if s < 1 or s + dur - 1 > n.PERIODS_PER_DAY:
            continue
        for c in fits:
            if all_free(c, dates, s):
                p0, p1 = n.PERIODS[s - 1], n.PERIODS[s + dur - 2]
                out.append(
                    {
                        "kind": "time",
                        "room_id": c.room.id,
                        "code": c.room.code,
                        "name": c.room.display_name,
                        "dates": [d.isoformat() for d in dates],
                        "start_period": s,
                        "end_period": s + dur - 1,
                        "reason": _reason(
                            f"{c.room.display_name} {p0.start:%H:%M}-{p1.end:%H:%M} boş ({shift:+d} ders saati)",
                            f"{c.room.display_name} free {p0.start:%H:%M}-{p1.end:%H:%M} ({shift:+d} period)",
                        ),
                    }
                )
    # other weekdays of the same week (single date searches)
    if q.other_days and len(dates) == 1:
        d = dates[0]
        monday = d - timedelta(days=d.isoweekday() - 1)
        others = [monday + timedelta(days=i) for i in range(5) if monday + timedelta(days=i) != d]
        infos = await date_infos(session, info, others)
        for od in others:
            if not infos[od].open:
                continue
            for c in fits:
                if all_free(c, [od], s0):
                    out.append(
                        {
                            "kind": "day",
                            "room_id": c.room.id,
                            "code": c.room.code,
                            "name": c.room.display_name,
                            "dates": [od.isoformat()],
                            "start_period": s0,
                            "end_period": s0 + dur - 1,
                            "reason": _reason(
                                f"{c.room.display_name} {DAY_TR[od.isoweekday()]} {od:%d.%m} aynı saatte boş",
                                f"{c.room.display_name} free on {DAY_EN[od.isoweekday()]} {od:%d.%m} at the same time",
                            ),
                        }
                    )
    # near misses: a little too small, or one feature missing
    for c in cands:
        near = (c.static == "too_small" and c.short_pct <= 0.10) or (
            c.static == "feature_missing" and len(c.missing) == 1
        )
        if near and all_free(c, dates, s0):
            why_tr = (
                f"{c.cap} kişilik (%{round(c.short_pct * 100)} eksik)"
                if c.static == "too_small"
                else f"eksik özellik: {c.missing[0]}"
            )
            why_en = (
                f"{c.cap} seats ({round(c.short_pct * 100)}% short)"
                if c.static == "too_small"
                else f"missing: {c.missing[0]}"
            )
            out.append(
                {
                    "kind": "near_miss",
                    "room_id": c.room.id,
                    "code": c.room.code,
                    "name": c.room.display_name,
                    "dates": [d.isoformat() for d in dates],
                    "start_period": s0,
                    "end_period": s0 + dur - 1,
                    "reason": _reason(f"{c.room.display_name} boş; {why_tr}", f"{c.room.display_name} free; {why_en}"),
                }
            )
    seen: set[tuple[Any, ...]] = set()
    unique = []
    for a in out:
        key = (a["kind"], a["room_id"], tuple(a["dates"]), a["start_period"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique[:20]


def _echo(q: FindQuery) -> dict[str, Any]:
    from app.services.audit import jsonable

    out = {k: jsonable(v) for k, v in q.__dict__.items() if v not in (None, [], "")}
    out["features"] = [jsonable(f.__dict__) for f in q.features]
    return out


async def alternatives_for(
    session: AsyncSession, access: Access, room: Room, d: date, start: int, end: int, headcount: int | None = None
) -> list[dict[str, Any]]:
    """Top free rooms for a slot that could not be booked (undo, approvals): same date and periods, at least the
    original room's capacity (or ``headcount``), the original room's solver tags."""
    q = FindQuery(
        dates=[d],
        start=start,
        end=end,
        headcount=headcount if headcount is not None else (room.capacity or 0),
        tags=[str(t) for t in (room.tags or [])],
        include_busy=False,
        limit=5,
    )
    try:
        res = await find_rooms(session, access, q)
    except FindError:
        return []
    return [
        {k: x[k] for k in ("room_id", "code", "name", "capacity", "start_period", "end_period", "status", "reason")}
        for x in res["results"]
        if x["room_id"] != room.id and x["status"] in ("free", "requestable")
    ][:3]
