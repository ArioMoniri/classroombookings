"""Exam-period demand (adaptive scheduling AS-11; docs/research/2026-10-17-adaptive-scheduling.md §3.4-2, §3.5).

* **Structural load** (always available from the exam list): exams and seats per day and per start slot against
  the rooms' ``exam_capacity``; the peak day and its ratio to the weekday mean (Final 2026: Wednesday 3 June,
  98 sittings, 1.67x). The unit is the **sitting**: a shared exam listed once per programme (one merge key) counts
  once, here, in the ``exam_load`` data issues and in the exam advisor (AS20-F13, FIX-G; before, the advisor and
  B6/B6a counted exam-list rows: 126, 1.87x).
* **Invigilators**: ``Σ ceil(seated / students_per_invigilator)`` per slot against the pool size, an early warning
  before an invigilation plan is run.
* **Booking demand in exam weeks**: bookings and blocks per day in EXAM / MAKEUP weeks against the lecture weeks of
  the same term (the exam-week multiplier per room group); ``confidence: none`` without a booking history.
* **Draft slot holds**: what ``slots`` would hold vs the whole-week closure (``booking_policies.slot_hold_summary``).

Every number comes from the exam requests, the exam runs, bookings and blocks of the database. Nothing is changed:
this is advice; a coordinator edits the requests (owner decision 6).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

_DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
_DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
_MONTH_TR = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
             9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}  # fmt: skip
DEFAULT_STUDENTS_PER_INVIGILATOR = 40


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def day_label(d: date) -> dict[str, str]:
    return _t(
        f"{d.day} {_MONTH_TR[d.month]} {d.year} {_DAY_TR[d.isoweekday()]}", f"{_DAY_EN[d.isoweekday()]} {d:%d %B %Y}"
    )


def day_load(exams: Iterable[tuple[date, int]]) -> dict[str, Any]:
    """Exams and seats per date (weekdays only for the mean): the peak day and peak / weekday mean."""
    count: Counter[date] = Counter()
    seats: Counter[date] = Counter()
    for d, n in exams:
        count[d] += 1
        seats[d] += max(0, int(n))
    total = sum(count.values())
    if not total:
        return {"days": [], "peak_day": None, "peak_exams": 0, "weekday_mean": 0.0, "peak_to_mean": 0.0}
    # the exam period: the weeks holding at least 5 % of the exams (a stray early exam does not stretch it); the
    # mean is over every weekday of those weeks, days without an exam included
    per_week: Counter[date] = Counter()
    for d, k in count.items():
        per_week[_week_monday(d)] += k
    mondays = sorted(m for m, k in per_week.items() if k >= 0.05 * total) or sorted(per_week)
    weekdays = [m + timedelta(days=i) for m in mondays for i in range(5)]
    mean = sum(count[d] for d in weekdays) / len(weekdays)
    peak = max(weekdays, key=lambda d: (count[d], seats[d], -d.toordinal()))
    return {
        "days": [
            {"date": d.isoformat(), "label": day_label(d), "exams": count[d], "seats": seats[d]} for d in sorted(count)
        ],
        "peak_day": peak.isoformat(),
        "peak_label": day_label(peak),
        "peak_exams": count[peak],
        "peak_seats": seats[peak],
        "weekday_mean": round(mean, 2),
        "peak_to_mean": round(count[peak] / mean, 3) if mean else 0.0,
        "weekend_exams": sum(count[d] for d in count if d.isoweekday() > 5),
        "period_weeks": [m.isoformat() for m in mondays],
        "outside_period_exams": total - sum(count[d] for d in count if _week_monday(d) in set(mondays)),
    }


def slot_load(exams: Iterable[tuple[date, int, int, int]]) -> dict[tuple[date, int], dict[str, int]]:
    """(date, period) -> exams and seats sitting then: (date, start, end, seats) per exam."""
    out: dict[tuple[date, int], dict[str, int]] = defaultdict(lambda: {"exams": 0, "seats": 0})
    for d, s, e, n in exams:
        for p in range(s, e + 1):
            out[(d, p)]["exams"] += 1
            out[(d, p)]["seats"] += max(0, int(n))
    return dict(out)


async def exam_forecast(session: Any, term_id: int, *, students_per_invigilator: int | None = None) -> dict[str, Any]:
    """``GET /analytics/forecast/exams``: seats per day and slot vs exam capacity, expected invigilators vs the
    pool, exam-week booking demand and the draft ``slots`` hold."""
    from sqlalchemy import func, select

    from app.models import ExamRequest, Room, Term
    from app.services import booking_policies as bp

    term = await session.get(Term, term_id)
    if term is None:
        raise LookupError(term_id)
    rows = list(
        (
            await session.execute(
                select(ExamRequest).where(
                    ExamRequest.term_id == term_id,
                    ExamRequest.archived.is_(False),
                    ExamRequest.needs_room.is_(True),
                    ExamRequest.date.is_not(None),
                )
            )
        ).scalars()
    )
    # one exam per merge key (a shared exam listed once per programme sits once)
    merged: dict[Any, ExamRequest] = {}
    sizes: Counter[Any] = Counter()
    for r in rows:
        key = getattr(r, "merge_key", None) or ("id", r.id)
        merged.setdefault(key, r)
        sizes[key] += int(r.enrolment or 0)
    exams = [(r.date, sizes[k]) for k, r in merged.items() if r.date is not None]
    timed = [
        (r.date, int(r.start_period), int(r.end_period), sizes[k])
        for k, r in merged.items()
        if r.date is not None and r.start_period and r.end_period
    ]
    cap_total = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Room.exam_capacity), 0)).where(Room.is_bookable.is_(True))
            )
        ).scalar_one()
    )
    load = day_load(exams)
    slots = slot_load(timed)
    spi = int(students_per_invigilator or await _students_per_invigilator(session) or DEFAULT_STUDENTS_PER_INVIGILATOR)
    pool = await _pool_size(session, term_id)
    slot_rows = []
    for (d, p), v in sorted(slots.items()):
        need = math.ceil(v["seats"] / spi) if v["seats"] else 0
        slot_rows.append(
            {
                "date": d.isoformat(),
                "period": p,
                "exams": v["exams"],
                "seats": v["seats"],
                "exam_capacity": cap_total,
                "seat_pct": round(100.0 * v["seats"] / cap_total, 1) if cap_total else None,
                "invigilators": need,
                "pool": pool,
                "invigilators_short": max(0, need - pool) if pool else None,
            }
        )
    peak_slot = max(slot_rows, key=lambda x: (x["seats"], x["exams"]), default=None)
    holds = await bp.slot_hold_summary(session, term_id, 1)
    bookings = await exam_week_bookings(session, term_id)
    if not exams:
        conf, needs = (
            "none",
            _t(
                "Bu dönemin tarihli sınav talebi yok: sınav listesini içe aktarın",
                "No dated exam requests: import the exam list",
            ),
        )
    else:
        conf, needs = "high", None
    return {
        "term_id": term_id,
        "term_code": term.code,
        "method": "requests" if exams else "none",
        "confidence": conf,
        "needs": needs,
        "basis": _t(
            f"{len(merged)} sınav (birleşik sınavlar bir kez), {cap_total} sınav koltuğu",
            f"{len(merged)} exams (shared exams once), {cap_total} exam seats",
        ),
        "days": load["days"],
        "peak_day": load.get("peak_day"),
        "peak_label": load.get("peak_label"),
        "peak_exams": load.get("peak_exams"),
        "weekday_mean": load.get("weekday_mean"),
        "peak_to_mean": load.get("peak_to_mean"),
        "slots": slot_rows,
        "peak_slot": peak_slot,
        "students_per_invigilator": spi,
        "invigilator_pool": pool,
        "holds": holds,
        "bookings": bookings,
    }


async def _students_per_invigilator(session: Any) -> int | None:
    try:
        from app.services import invigilation as inv

        value = getattr(inv, "DEFAULTS", {}).get("students_per_invigilator")
        return int(value) if value else None
    except Exception:  # noqa: BLE001 - a read-only helper; the default applies
        return None


async def _pool_size(session: Any, term_id: int) -> int:
    from sqlalchemy import func, select

    try:
        from app.models import InvigilatorPoolMember

        col = getattr(InvigilatorPoolMember, "term_id", None)
        q = select(func.count()).select_from(InvigilatorPoolMember)
        if col is not None:
            q = q.where(col == term_id)
        return int((await session.execute(q)).scalar_one() or 0)
    except Exception:  # noqa: BLE001
        return 0


async def exam_week_bookings(session: Any, term_id: int) -> dict[str, Any]:
    """Bookings + dated blocks per day in EXAM / MAKEUP weeks vs lecture weeks of the term, per room type (the
    exam-week multiplier). ``none`` without bookings in exam weeks."""
    from sqlalchemy import select

    from app.models import Block, Booking, Room, Term
    from app.services import seasons
    from app.services.utilisation import room_type_of

    term = await session.get(Term, term_id)
    weeks_rows, holidays, segs = await seasons.load_calendar(session, term)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    per: dict[str, dict[str, Counter[date]]] = defaultdict(lambda: {"exam": Counter(), "lecture": Counter()})
    q = select(Booking.room_id, Booking.date).where(Booking.term_id == term_id, Booking.status == "BOOKED")
    qb = select(Block.room_id, Block.date).where(
        Block.term_id == term_id, Block.date.is_not(None), Block.archived.is_(False)
    )
    for rid, d in [*(await session.execute(q)).all(), *(await session.execute(qb)).all()]:
        kind = seasons.period_kind_on(term, d, weeks_rows, holidays, segs)
        side = "exam" if kind in ("EXAM", "MAKEUP") else ("lecture" if kind == "LECTURE" else None)
        if side is None or rid not in rooms:
            continue
        per[room_type_of(rooms[rid])][side][d] += 1
    groups = []
    for g, sides in sorted(per.items()):
        e_days, l_days = sides["exam"], sides["lecture"]
        e_mean = sum(e_days.values()) / len(e_days) if e_days else 0.0
        l_mean = sum(l_days.values()) / len(l_days) if l_days else 0.0
        groups.append(
            {
                "group": g,
                "exam_per_day": round(e_mean, 2),
                "lecture_per_day": round(l_mean, 2),
                "multiplier": round(e_mean / l_mean, 2) if l_mean and e_days else None,
            }
        )
    has_exam = any(x["exam_per_day"] for x in groups)
    return {
        "groups": groups,
        "confidence": "low" if has_exam else "none",
        "needs": None
        if has_exam
        else _t("En az bir sınav döneminin rezervasyon geçmişi", "The booking history of at least one exam period"),
    }


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


__all__ = ["day_label", "day_load", "exam_forecast", "exam_week_bookings", "slot_load"]


def exam_issues(
    exams: Iterable[tuple[int, date, int, int, int, frozenset[str]]],
    exam_capacity: int,
    threshold_pct: float = 85.0,
    peak_ratio: float = 1.5,
) -> list[dict[str, Any]]:
    """``exam_load`` findings: seats in a slot above ``threshold_pct`` of the exam capacity, a cohort with more than
    two exams on one day, a day with more than ``peak_ratio`` x the weekday mean of exams. ``exams``: (request id,
    date, start, end, seats, cohort keys)."""
    rows = list(exams)
    out: list[dict[str, Any]] = []
    load = day_load([(d, n) for _i, d, _s, _e, n, _c in rows])
    mean = load["weekday_mean"] or 0.0
    for day in load["days"]:
        d = date.fromisoformat(day["date"])
        if mean and day["exams"] > peak_ratio * mean:
            ratio = day["exams"] / mean
            out.append(
                {
                    "kind": "peak_day",
                    "date": day["date"],
                    "request_ids": sorted(i for i, dd, *_r in rows if dd == d),
                    "params": {"exams": day["exams"], "seats": day["seats"], "ratio": round(ratio, 2)},
                    "text": _t(
                        f"{day_label(d)['tr']}: {day['exams']} sınav, hafta içi ortalamanın {ratio:.2f}".replace(
                            ".", ","
                        )
                        + " katı",
                        f"{day_label(d)['en']}: {day['exams']} exams, {ratio:.2f}x the weekday mean",
                    ),
                }
            )
    for (d, p), v in sorted(slot_load([(dd, s, e, n) for _i, dd, s, e, n, _c in rows]).items()):
        if exam_capacity and v["seats"] > exam_capacity * threshold_pct / 100.0:
            out.append(
                {
                    "kind": "seats",
                    "date": d.isoformat(),
                    "period": p,
                    "request_ids": sorted(i for i, dd, s, e, *_r in rows if dd == d and s <= p <= e),
                    "params": {"seats": v["seats"], "exam_capacity": exam_capacity},
                    "text": _t(
                        f"{day_label(d)['tr']} {p}. ders: {v['seats']} öğrenci, sınav koltuğu {exam_capacity}",
                        f"{day_label(d)['en']} period {p}: {v['seats']} students, {exam_capacity} exam seats",
                    ),
                }
            )
    per_cohort: dict[tuple[str, date], list[int]] = defaultdict(list)
    for i, d, _s, _e, _n, cohorts in rows:
        for c in cohorts:
            per_cohort[(c, d)].append(i)
    for (c, d), ids in sorted(per_cohort.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if len(ids) > 2:
            name = c.split(":", 1)[-1]
            out.append(
                {
                    "kind": "cohort_day",
                    "date": d.isoformat(),
                    "request_ids": sorted(ids),
                    "params": {"cohort": name, "exams": len(ids)},
                    "text": _t(
                        f"{name}: {day_label(d)['tr']} günü {len(ids)} sınav (en çok 2)",
                        f"{name}: {len(ids)} exams on {day_label(d)['en']} (at most 2)",
                    ),
                }
            )
    return out


async def exam_load_issues(session: Any, term_id: int) -> list[dict[str, Any]]:
    """The ``exam_load`` data issues of a term's exam list (no run needed)."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from app.models import ExamRequest, Room

    rows = list(
        (
            await session.execute(
                select(ExamRequest)
                .where(
                    ExamRequest.term_id == term_id,
                    ExamRequest.archived.is_(False),
                    ExamRequest.needs_room.is_(True),
                    ExamRequest.date.is_not(None),
                )
                .options(selectinload(ExamRequest.program))
            )
        ).scalars()
    )
    merged: dict[Any, list[ExamRequest]] = defaultdict(list)
    for r in rows:
        merged[r.merge_key or ("id", r.id)].append(r)
    exams = []
    for group in merged.values():
        head = group[0]
        if head.date is None:
            continue
        cohorts = frozenset(
            f"COH:{(r.program.name if r.program else '?')} {y}. sınıf"
            for r in group
            for y in ([int(x) for x in (r.class_years or [])] or ([r.class_year] if r.class_year else []))
            if r.program is not None
        )
        exams.append(
            (
                head.id,
                head.date,
                int(head.start_period or 0),
                int(head.end_period or head.start_period or 0),
                sum(int(r.enrolment or 0) for r in group),
                cohorts,
            )
        )
    cap = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Room.exam_capacity), 0)).where(Room.is_bookable.is_(True))
            )
        ).scalar_one()
    )
    out = []
    for f in exam_issues([e for e in exams if e[2]], cap):
        out.append(
            {
                "diagnosis_index": -1,
                "code": "exam_load",
                "severity": "warning" if f["kind"] != "peak_day" else "info",
                "message": f["text"]["en"],
                "message_tr": f["text"]["tr"],
                "detail": f["kind"],
                "suggestions": ["move an exam to a lighter day or slot (advice only; edit the exam request)"],
                "event_ids": [],
                "request_ids": f["request_ids"],
                "unplaced": False,
                "params": {"kind": f["kind"], "date": f["date"], **f["params"]},
                "classes": [],
            }
        )
    return out
