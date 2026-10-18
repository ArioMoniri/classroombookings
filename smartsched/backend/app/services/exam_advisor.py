"""Exam date advisor (adaptive scheduling AS-12; docs/research/2026-10-17-adaptive-scheduling.md §3.5).

Checks a term's dated exam list and answers **advice only** (owner decision 6: nothing is changed; a coordinator
accepts a card by editing the exam request):

* ``cohort_day``   a cohort (programme + class year) with more than ``max_per_day`` (2) exams on one day;
* ``clash``        two exams of one cohort or one instructor at overlapping times;
* ``back_to_back`` two exams of one cohort or one instructor in consecutive periods of a day;
* ``front_load``   a large exam (``large_seats``, 100 seats) on one of the last ``last_days`` (2) exam days;
* ``seats``        seats sitting in a period above ``seat_pct`` (85 %) of the rooms' exam capacity;
* ``peak_day``     a day with more exams than ``ceil(peak_ratio × weekday mean)`` (1.25).

**Moves.** A greedy, deterministic search proposes one move at a time: an exam (a merge group moves as one) to
another day of the exam period at the same time, or to another start period of its day.  Each move is scored by
the change of a weighted conflict cost (``WEIGHTS``) and is offered only when it lowers the cost and adds **no**
cohort-day excess and **no** clash.  The moves are ranked in the order found; each assumes the earlier ones were
accepted (``basis`` says so).  Ties break on fewer seats, then the exam id, the date and the start, so the same
list always gives the same advice.

The exam count of a day is the number of exam-list rows (programme exams), the same unit as
``exam_load.day_load`` (Final 2026: Wednesday 3 June, 126); a merge group counts its rows.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from app.services.exam_load import day_label

#: conflict cost per unit (a clash outweighs everything; a peak-day row is the cheapest unit that still moves)
WEIGHTS: dict[str, int] = {
    "clash": 100,
    "cohort_day": 30,
    "back_to_back": 5,
    "front_load": 3,
    "seats": 2,
    "peak": 2,
}
SEAT_UNIT = 50  # seats above the threshold are counted in units of 50


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


@dataclass(frozen=True)
class ExamItem:
    """One exam as it sits (a merge group of exam-list rows is one item)."""

    id: int
    request_ids: tuple[int, ...]
    label: str
    date: date
    start: int
    end: int
    seats: int
    rows: int = 1
    cohorts: frozenset[str] = frozenset()
    instructors: frozenset[str] = frozenset()

    @property
    def keys(self) -> frozenset[str]:
        return self.cohorts | self.instructors


@dataclass(frozen=True)
class AdvisorConfig:
    max_per_day: int = 2
    peak_ratio: float = 1.25
    large_seats: int = 100
    last_days: int = 2
    seat_pct: float = 85.0
    max_moves: int = 200
    periods_per_day: int = 18


# ------------------------------------------------------------------------------------------------ the period


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def period_dates(items: Sequence[ExamItem]) -> list[date]:
    """Weekdays of the weeks that hold at least 5 % of the exam rows (the ``day_load`` period)."""
    total = sum(i.rows for i in items)
    per_week: Counter[date] = Counter()
    for i in items:
        per_week[_monday(i.date)] += i.rows
    mondays = sorted(m for m, k in per_week.items() if k >= 0.05 * total) or sorted(per_week)
    return [m + timedelta(days=k) for m in mondays for k in range(5)]


# ------------------------------------------------------------------------------------------------ day state


@dataclass
class _Day:
    rows: int = 0
    by_key: dict[str, dict[int, tuple[int, int]]] = field(default_factory=lambda: defaultdict(dict))
    seats: Counter[int] = field(default_factory=Counter)
    cohort_n: Counter[str] = field(default_factory=Counter)
    items: dict[int, ExamItem] = field(default_factory=dict)

    def add(self, x: ExamItem) -> None:
        self.rows += x.rows
        for k in x.keys:
            self.by_key[k][x.id] = (x.start, x.end)
        for c in x.cohorts:
            self.cohort_n[c] += 1
        for p in range(x.start, x.end + 1):
            self.seats[p] += x.seats
        self.items[x.id] = x

    def remove(self, x: ExamItem) -> None:
        self.rows -= x.rows
        for k in x.keys:
            self.by_key[k].pop(x.id, None)
        for c in x.cohorts:
            self.cohort_n[c] -= 1
        for p in range(x.start, x.end + 1):
            self.seats[p] -= x.seats
        self.items.pop(x.id, None)


class _Ctx:
    def __init__(
        self, items: Sequence[ExamItem], exam_capacity: int, cfg: AdvisorConfig, dates: Sequence[date] | None
    ) -> None:
        self.cfg = cfg
        self.dates = sorted(set(dates) if dates else set(period_dates(items)))
        on_period = [i for i in items if i.date in set(self.dates)]
        weekdays = [d for d in self.dates if d.isoweekday() <= 5] or self.dates
        self.mean = sum(i.rows for i in on_period if i.date in set(weekdays)) / max(1, len(weekdays))
        self.target = max(1, math.ceil(self.mean * cfg.peak_ratio)) if on_period else 0
        self.last = set(self.dates[-cfg.last_days :]) if cfg.last_days > 0 else set()
        self.threshold = exam_capacity * cfg.seat_pct / 100.0 if exam_capacity > 0 else None
        self.capacity = exam_capacity
        self.days: dict[date, _Day] = defaultdict(_Day)
        for i in items:
            self.days[i.date].add(i)
        self.starts = sorted({i.start for i in items})

    # -------------------------------------------------------------------- unit counts of one item on one day

    def _pairs(self, day: _Day, x: ExamItem, start: int, end: int) -> tuple[int, int]:
        """(clashes, back-to-back) of ``x`` placed at ``start..end`` against the others of ``day``."""
        clash: set[int] = set()
        b2b: set[int] = set()
        for k in x.keys:
            for oid, (s, e) in day.by_key.get(k, {}).items():
                if oid == x.id:
                    continue
                if s <= end and start <= e:
                    clash.add(oid)
                elif s == end + 1 or e + 1 == start:
                    b2b.add(oid)
        return len(clash), len(b2b - clash)

    def _seat_units(self, seats: int) -> int:
        if self.threshold is None:
            return 0
        return math.ceil(max(0.0, seats - self.threshold) / SEAT_UNIT)

    def _peak_units(self, rows: int) -> int:
        return max(0, rows - self.target) if self.target else 0

    def contribution(self, day: _Day, d: date, x: ExamItem, start: int, end: int, present: bool) -> dict[str, int]:
        """Units ``x`` adds to day ``d`` at ``start..end`` (``present``: ``x`` is already counted in ``day``)."""
        clash, b2b = self._pairs(day, x, start, end)
        cohort = 0
        for c in x.cohorts:
            n_other = day.cohort_n[c] - (1 if present else 0)
            cohort += int(n_other >= self.cfg.max_per_day)
        seats = 0
        for p in range(start, end + 1):
            other = day.seats[p] - (x.seats if present and x.start <= p <= x.end else 0)
            seats += self._seat_units(other + x.seats) - self._seat_units(other)
        rows_other = day.rows - (x.rows if present else 0)
        peak = self._peak_units(rows_other + x.rows) - self._peak_units(rows_other)
        front = int(d in self.last and x.seats >= self.cfg.large_seats)
        return {"clash": clash, "cohort_day": cohort, "back_to_back": b2b, "front_load": front, "seats": seats, "peak": peak}

    def move_delta(self, x: ExamItem, d: date, start: int) -> dict[str, int]:
        end = start + (x.end - x.start)
        here = self.contribution(self.days[x.date], x.date, x, x.start, x.end, True)
        if d == x.date:
            day = self.days[d]
            day.remove(x)
            there = self.contribution(day, d, x, start, end, False)
            day.add(x)
        else:
            there = self.contribution(self.days[d], d, x, start, end, False)
        delta = {k: there[k] - here[k] for k in WEIGHTS}
        delta["score"] = sum(WEIGHTS[k] * delta[k] for k in WEIGHTS)
        return delta

    def move(self, x: ExamItem, d: date, start: int) -> ExamItem:
        self.days[x.date].remove(x)
        y = replace(x, date=d, start=start, end=start + (x.end - x.start))
        self.days[d].add(y)
        return y


# ------------------------------------------------------------------------------------------------ findings


def _who(key: str) -> str:
    return "instructor" if key.startswith("INS:") else "cohort"


def _key_name(key: str) -> str:
    if key.startswith("PROG:"):
        _p, prog, year = key.split(":", 2)
        return f"{prog} {year.lstrip('Y')}"
    return key.split(":", 1)[-1]


def findings(ctx: _Ctx) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cfg = ctx.cfg
    for d in sorted(ctx.days):
        day = ctx.days[d]
        if not day.items:
            continue
        lab = day_label(d)
        if ctx.target and day.rows > ctx.target and d in set(ctx.dates):
            out.append(
                {
                    "kind": "peak_day",
                    "date": d.isoformat(),
                    "request_ids": sorted(r for x in day.items.values() for r in x.request_ids),
                    "params": {"exams": day.rows, "target": ctx.target, "weekday_mean": round(ctx.mean, 2)},
                    "text": _t(
                        f"{lab['tr']}: {day.rows} sınav; hedef en çok {ctx.target} (hafta içi ortalama "
                        f"{ctx.mean:.1f})".replace(".", ","),
                        f"{lab['en']}: {day.rows} exams; target at most {ctx.target} (weekday mean {ctx.mean:.1f})",
                    ),
                }
            )
        for c, n in sorted(day.cohort_n.items()):
            if n > cfg.max_per_day:
                ids = sorted(day.by_key[c])
                out.append(
                    {
                        "kind": "cohort_day",
                        "date": d.isoformat(),
                        "request_ids": sorted(r for i in ids for r in day.items[i].request_ids),
                        "exam_ids": ids,
                        "params": {"cohort": _key_name(c), "exams": n, "max": cfg.max_per_day},
                        "text": _t(
                            f"{_key_name(c)}. sınıf: {lab['tr']} günü {n} sınav (en çok {cfg.max_per_day})",
                            f"{_key_name(c)} (year): {n} exams on {lab['en']} (at most {cfg.max_per_day})",
                        ),
                    }
                )
        seen: set[tuple[str, int, int]] = set()
        for k in sorted(day.by_key):
            spans = sorted(day.by_key[k].items(), key=lambda kv: (kv[1], kv[0]))
            for a in range(len(spans)):
                for b in range(a + 1, len(spans)):
                    (ia, (sa, ea_)), (ib, (sb, eb)) = spans[a], spans[b]
                    kind = "clash" if sb <= ea_ and sa <= eb else ("back_to_back" if sb == ea_ + 1 else None)
                    if kind is None:
                        continue
                    pair = (kind, min(ia, ib), max(ia, ib))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    xa, xb = day.items[ia], day.items[ib]
                    who = _who(k)
                    who_tr = "öğretim elemanı" if who == "instructor" else "sınıf"
                    name = _key_name(k)
                    if kind == "clash":
                        tr = f"{name} ({who_tr}): {xa.label} ve {xb.label} {lab['tr']} aynı saatte"
                        en = f"{name} ({who}): {xa.label} and {xb.label} overlap on {lab['en']}"
                    else:
                        tr = f"{name} ({who_tr}): {xa.label} ve {xb.label} {lab['tr']} art arda"
                        en = f"{name} ({who}): {xa.label} and {xb.label} back to back on {lab['en']}"
                    out.append(
                        {
                            "kind": kind,
                            "date": d.isoformat(),
                            "request_ids": sorted([*xa.request_ids, *xb.request_ids]),
                            "exam_ids": sorted([ia, ib]),
                            "params": {"who": who, "name": name},
                            "text": _t(tr, en),
                        }
                    )
        if d in ctx.last:
            for x in sorted(day.items.values(), key=lambda x: (-x.seats, x.id)):
                if x.seats >= cfg.large_seats:
                    out.append(
                        {
                            "kind": "front_load",
                            "date": d.isoformat(),
                            "request_ids": list(x.request_ids),
                            "exam_ids": [x.id],
                            "params": {"seats": x.seats, "large_seats": cfg.large_seats, "last_days": cfg.last_days},
                            "text": _t(
                                f"{x.label}: {x.seats} öğrenci, sınav döneminin son {cfg.last_days} gününde "
                                f"({lab['tr']})",
                                f"{x.label}: {x.seats} students in the last {cfg.last_days} exam days ({lab['en']})",
                            ),
                        }
                    )
        if ctx.threshold is not None:
            for p in sorted(day.seats):
                s = day.seats[p]
                if s > ctx.threshold:
                    ids = sorted(i for i, x in day.items.items() if x.start <= p <= x.end)
                    out.append(
                        {
                            "kind": "seats",
                            "date": d.isoformat(),
                            "period": p,
                            "request_ids": sorted(r for i in ids for r in day.items[i].request_ids),
                            "exam_ids": ids,
                            "params": {"seats": s, "exam_capacity": ctx.capacity, "threshold_pct": cfg.seat_pct},
                            "text": _t(
                                f"{lab['tr']} {p}. ders: {s} öğrenci, sınav koltuğu {ctx.capacity}",
                                f"{lab['en']} period {p}: {s} students, {ctx.capacity} exam seats",
                            ),
                        }
                    )
    return out


def _counts(ctx: _Ctx) -> dict[str, Any]:
    f = findings(ctx)
    c = Counter(x["kind"] for x in f)
    per_day = {d: day.rows for d, day in ctx.days.items() if day.rows}
    period = [d for d in ctx.dates if d in per_day] or sorted(per_day)
    peak = max(period, key=lambda d: (per_day.get(d, 0), -d.toordinal()), default=None)
    return {
        "peak_day": peak.isoformat() if peak else None,
        "peak_exams": per_day.get(peak, 0) if peak else 0,
        "weekday_mean": round(ctx.mean, 2),
        "target_per_day": ctx.target,
        "days_over_target": c["peak_day"],
        "cohort_days_over": c["cohort_day"],
        "cohort_day_excess": sum(
            max(0, n - ctx.cfg.max_per_day) for day in ctx.days.values() for n in day.cohort_n.values()
        ),
        "clashes": c["clash"],
        "back_to_back": c["back_to_back"],
        "front_load": c["front_load"],
        "seat_slots_over": c["seats"],
    }


def summary(
    items: Sequence[ExamItem],
    *,
    exam_capacity: int = 0,
    cfg: AdvisorConfig | None = None,
    dates: Sequence[date] | None = None,
) -> dict[str, Any]:
    return _counts(_Ctx(items, exam_capacity, cfg or AdvisorConfig(), dates))


# ------------------------------------------------------------------------------------------------ moves


def _candidates(ctx: _Ctx, x: ExamItem) -> Iterable[tuple[date, int]]:
    dur = x.end - x.start
    for d in ctx.dates:
        if d != x.date:
            yield d, x.start
    for s in ctx.starts:
        if s != x.start and s + dur <= ctx.cfg.periods_per_day:
            yield x.date, s


def _movable(ctx: _Ctx) -> list[ExamItem]:
    """Exams on a day / slot with a finding (only they can lower the cost)."""
    out: dict[int, ExamItem] = {}
    for f in findings(ctx):
        day = ctx.days[date.fromisoformat(f["date"])]
        ids = f.get("exam_ids") or list(day.items)
        for i in ids:
            if i in day.items:
                out[i] = day.items[i]
    return [out[i] for i in sorted(out)]


def _move_text(x: ExamItem, d: date, start: int, end: int, delta: Mapping[str, int]) -> dict[str, str]:
    a, b = day_label(x.date), day_label(d)
    fixes_tr, fixes_en = [], []
    names = {
        "cohort_day": ("günde 2'den çok sınav", "more than 2 exams a day"),
        "clash": ("çakışma", "clash"),
        "back_to_back": ("art arda sınav", "back-to-back exam"),
        "front_load": ("son günlerde büyük sınav", "large exam in the last days"),
        "seats": ("koltuk yoğunluğu", "seat peak"),
        "peak": ("yoğun gün", "peak day"),
    }
    for k, (tr, en) in names.items():
        if delta.get(k, 0) < 0:
            fixes_tr.append(f"{tr} −{-delta[k]}")
            fixes_en.append(f"{en} −{-delta[k]}")
    where_tr = f"{b['tr']} {start}.–{end}. ders" if d != x.date else f"aynı gün {start}.–{end}. ders"
    where_en = f"{b['en']} periods {start}–{end}" if d != x.date else f"same day, periods {start}–{end}"
    return _t(
        f"{x.label}: {a['tr']} {x.start}.–{x.end}. ders → {where_tr} ({', '.join(fixes_tr) or 'daha az çakışma'})",
        f"{x.label}: {a['en']} periods {x.start}–{x.end} → {where_en} ({', '.join(fixes_en) or 'fewer conflicts'})",
    )


def suggest(ctx: _Ctx) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    moved: set[int] = set()
    for rank in range(1, ctx.cfg.max_moves + 1):
        best: tuple[tuple[Any, ...], ExamItem, date, int, dict[str, int]] | None = None
        for x in _movable(ctx):
            if x.id in moved:
                continue  # one suggestion per exam: a card is one edit
            for d, s in _candidates(ctx, x):
                delta = ctx.move_delta(x, d, s)
                if delta["score"] >= 0 or delta["cohort_day"] > 0 or delta["clash"] > 0:
                    continue
                key = (delta["score"], x.seats, x.id, d, s)
                if best is None or key < best[0]:
                    best = (key, x, d, s, delta)
        if best is None:
            break
        _k, x, d, s, delta = best
        end = s + (x.end - x.start)
        moves.append(
            {
                "rank": rank,
                "exam_id": x.id,
                "request_ids": list(x.request_ids),
                "label": x.label,
                "rows": x.rows,
                "seats": x.seats,
                "from": {"date": x.date.isoformat(), "start": x.start, "end": x.end, "label": day_label(x.date)},
                "to": {"date": d.isoformat(), "start": s, "end": end, "label": day_label(d)},
                "kind": "date" if d != x.date else "slot",
                "delta": delta,
                "text": _move_text(x, d, s, end, delta),
            }
        )
        ctx.move(x, d, s)
        moved.add(x.id)
    return moves


def apply_moves(items: Sequence[ExamItem], moves: Iterable[Mapping[str, Any]]) -> list[ExamItem]:
    """The exam list with the given suggestions accepted (for previews and the B6 backtest; never stored)."""
    by_id = {i.id: i for i in items}
    for m in moves:
        x = by_id.get(int(m["exam_id"]))
        if x is None:
            continue
        to = m["to"]
        by_id[x.id] = replace(x, date=date.fromisoformat(to["date"]), start=int(to["start"]), end=int(to["end"]))
    return [by_id[i.id] for i in items]


# ------------------------------------------------------------------------------------------------ entry point


def advise(
    items: Sequence[ExamItem],
    *,
    exam_capacity: int = 0,
    cfg: AdvisorConfig | None = None,
    dates: Sequence[date] | None = None,
) -> dict[str, Any]:
    """Advice cards and ranked moves for an exam list (nothing is changed)."""
    cfg = cfg or AdvisorConfig()
    ordered = sorted(items, key=lambda i: i.id)
    basis = _t(
        "Sınav listesindeki tarih ve saatlerden hesaplandı. Öneriler sırayla uygulanırsa geçerlidir (her biri "
        "öncekilerin kabul edildiğini varsayar); hiçbir şey otomatik değişmez, sınav talebini düzenleyerek kabul "
        "edilir.",
        "Computed from the dates and times of the exam list. The moves hold in order (each assumes the earlier ones "
        "were accepted); nothing changes automatically: accept one by editing the exam request.",
    )
    if not ordered:
        return {
            "method": "exam_advisor",
            "changes_nothing": True,
            "confidence": "none",
            "needs": _t("Tarihi ve saati olan bir sınav listesi gerekli", "An exam list with dates and times"),
            "basis": basis,
            "config": cfg.__dict__,
            "before": None,
            "after": None,
            "cards": [],
            "suggestions": [],
        }
    ctx = _Ctx(ordered, exam_capacity, cfg, dates)
    before = _counts(ctx)
    cards = findings(ctx)
    moves = suggest(ctx)
    after = _counts(ctx)
    for c in cards:
        ids = set(c.get("exam_ids") or [])
        if c["kind"] == "peak_day" or not ids:
            c["suggestion_ranks"] = [m["rank"] for m in moves if m["from"]["date"] == c["date"]]
        else:
            c["suggestion_ranks"] = [m["rank"] for m in moves if m["exam_id"] in ids]
    return {
        "method": "exam_advisor",
        "changes_nothing": True,
        "confidence": "high",
        "needs": None,
        "basis": basis,
        "config": cfg.__dict__,
        "period": [d.isoformat() for d in ctx.dates],
        "before": before,
        "after": after,
        "cards": cards,
        "suggestions": moves,
    }


# ------------------------------------------------------------------------------------------------ loaders


def _cohorts(program: Any, years: Iterable[Any]) -> frozenset[str]:
    from app.importers.normalize import cohort_key

    if not program:
        return frozenset()
    return frozenset(cohort_key(program, y) for y in years if y is not None and int(y) > 0)


def _instructor(text: Any) -> frozenset[str]:
    from app.importers.normalize import non_person_reason

    if not text or non_person_reason(text) is not None:
        return frozenset()
    return frozenset({f"INS:{str(text).strip()}"})


def _group(rows: Sequence[Any], key: Any) -> dict[Any, list[Any]]:
    out: dict[Any, list[Any]] = defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out


def items_from_exam_list(parsed: Any, *, with_room_only: bool = True) -> list[ExamItem]:
    """Exam items of a parsed exam list (the workbook through the production parser; ids are row numbers).
    ``with_room_only``: the rows with a definitive room, the unit of ``day_load`` / B6a."""
    rows = [
        r
        for r in parsed.rows
        if r.date is not None
        and r.periods.start_period
        and r.needs_room
        and (not with_room_only or getattr(r.definitive, "room_codes", None))
    ]
    out: list[ExamItem] = []
    for key, group in _group(rows, lambda r: r.merge_key or ("row", r.row)).items():
        group = sorted(group, key=lambda r: r.row)
        head = group[0]
        out.append(
            ExamItem(
                id=int(head.row),
                request_ids=tuple(int(r.row) for r in group),
                label=str(head.course_code),
                date=head.date,
                start=int(head.periods.start_period),
                end=max(int(r.periods.end_period or r.periods.start_period) for r in group),
                seats=sum(int(r.enrolment or 0) for r in group),
                rows=len(group),
                cohorts=frozenset().union(*(_cohorts(r.program, r.class_years) for r in group)),
                instructors=frozenset().union(*(_instructor(r.instructor) for r in group)),
            )
        )
    return sorted(out, key=lambda i: i.id)


async def load_items(session: Any, term_id: int) -> tuple[list[ExamItem], int]:
    """(exam items of the term's dated exam requests, total exam capacity of the bookable rooms)."""
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
                    ExamRequest.start_period.is_not(None),
                )
                .options(selectinload(ExamRequest.program))
            )
        ).scalars()
    )
    items: list[ExamItem] = []
    for _key, group in _group(rows, lambda r: r.merge_key or ("id", r.id)).items():
        group = sorted(group, key=lambda r: r.id)
        head = group[0]
        items.append(
            ExamItem(
                id=int(head.id),
                request_ids=tuple(int(r.id) for r in group),
                label=str(head.course_code),
                date=head.date,
                start=int(head.start_period),
                end=max(int(r.end_period or r.start_period) for r in group),
                seats=sum(int(r.enrolment or 0) for r in group),
                rows=len(group),
                cohorts=frozenset().union(
                    *(
                        _cohorts(
                            r.program.canonical_name if r.program else None,
                            [int(x) for x in (r.class_years or [])] or ([r.class_year] if r.class_year else []),
                        )
                        for r in group
                    )
                ),
                instructors=frozenset().union(*(_instructor(r.instructor_text) for r in group)),
            )
        )
    cap = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Room.exam_capacity), 0)).where(Room.is_bookable.is_(True))
            )
        ).scalar_one()
    )
    return sorted(items, key=lambda i: i.id), cap


async def advise_term(session: Any, term_id: int, *, cfg: AdvisorConfig | None = None) -> dict[str, Any]:
    """``GET /analytics/forecast/exams/advice?term_id=``: the advisor on the term's exam requests."""
    from app.models import Term

    term = await session.get(Term, term_id)
    if term is None:
        raise LookupError(term_id)
    items, cap = await load_items(session, term_id)
    out = advise(items, exam_capacity=cap, cfg=cfg)
    return {"term_id": term_id, "term_code": term.code, **out}


__all__ = [
    "WEIGHTS",
    "AdvisorConfig",
    "ExamItem",
    "advise",
    "advise_term",
    "apply_moves",
    "findings",
    "items_from_exam_list",
    "load_items",
    "period_dates",
    "summary",
]
