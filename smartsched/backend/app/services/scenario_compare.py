"""Scenario comparison: two runs of the same term and kind side by side (docs/design/run-report.md §2.5).

``compare(a, b)`` reads the two stored runs (nothing is re-solved, so the same pair always gives the same answer):

* scores: status, hard / soft score, placed / unplaced, waived rules, diagnoses by code, with the direction that
  is better for each metric;
* per class (course runs: meeting requests, exam runs: exam requests): unchanged, moved (time, room or both, with
  the from / to cells), placed only in A, placed only in B; the request-level placement is the moderation read
  model's (:func:`app.services.moderation.place_of`), so the comparison and the re-solve diff agree;
* per instructor (course runs): periods per week, idle gaps, teaching days, busiest day in A and in B
  (:mod:`app.services.utilisation`); exam runs: exams per day per named instructor;
* per room: occupied room-periods and utilisation % in A and B, and the delta;
* rule by rule: the soft penalty of every objective term in A and B (``stats.objective_breakdown``).

Run A is the baseline ("before"), B the scenario ("after"); deltas are ``B - A``.
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.export_safety import safe_writer
from app.importers import normalize as n
from app.models import Assignment, ExamRequest, Instructor, Room, ScheduleRun, Term
from app.services import moderation as mod
from app.services import utilisation as util

#: statuses a comparison accepts (an INFEASIBLE run is compared by its scores and whatever it placed)
COMPARABLE = frozenset({"OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL", "INFEASIBLE"})
MAX_ITEMS = 2000

# the moderation module's read helpers (read-only; one placement rule for the diff and the comparison)
_cell_set = mod._cell_set  # noqa: SLF001
_place_out = mod._place_out  # noqa: SLF001
_in_horizon = mod._in_horizon  # noqa: SLF001


class CompareError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# ------------------------------------------------------------------------------------------- metric helpers

#: +1: a higher value is better, -1: lower is better, 0: neutral
DIRECTION = {
    "hard_score": 1,
    "soft_score": 1,
    "placed": 1,
    "unplaced": -1,
    "diagnoses_errors": -1,
    "waived_rules": -1,
    "objective": -1,
    "gaps_per_week_total": -1,
    "instructors_with_gaps": -1,
    "periods_per_week_max": -1,
    "utilisation_pct": 0,
}

METRIC_LABEL = {
    "hard_score": ("Sert puan", "Hard score"),
    "soft_score": ("Yumuşak puan", "Soft score"),
    "placed": ("Yerleşen", "Placed"),
    "unplaced": ("Yerleşmeyen", "Unplaced"),
    "diagnoses_errors": ("Hata tanıları", "Error diagnoses"),
    "waived_rules": ("Esnetilen kurallar", "Waived rules"),
    "objective": ("Toplam yumuşak ceza", "Total soft penalty"),
    "gaps_per_week_total": ("Eğitmen boşlukları (haftalık)", "Instructor gaps (per week)"),
    "instructors_with_gaps": ("Boşluğu olan eğitmen", "Instructors with gaps"),
    "periods_per_week_max": ("En yüksek haftalık yük", "Highest weekly load"),
    "utilisation_pct": ("Oda doluluğu %", "Room utilisation %"),
}


def _metric(key: str, a: float | int | None, b: float | int | None, *, comparable: bool = True) -> dict[str, Any]:
    """One metric row. ``comparable=False`` (round-1 R1-M-10): one side has no data for it (a week run against a
    term run outside the shared weeks): the values are ``None`` and nothing is "better"."""
    direction = DIRECTION.get(key, 0)
    if not comparable:
        a = b = None
    delta = None if a is None or b is None else round(float(b) - float(a), 2)
    if delta is None or direction == 0 or delta == 0:
        better = "same" if delta == 0 else None
    else:
        better = "b" if delta * direction > 0 else "a"
    tr, en = METRIC_LABEL.get(key, (key, key))
    return {
        "key": key,
        "label": _t(tr, en),
        "a": a,
        "b": b,
        "delta": delta,
        "better": better,
        "direction": direction,
        "comparable": comparable and a is not None and b is not None,
    }


def _weeks_text(weeks: list[int], lang: str) -> str:
    ws = sorted(set(weeks))
    if not ws:
        return "hafta yok" if lang == "tr" else "no week"
    span = f"{ws[0]}–{ws[-1]}" if len(ws) > 1 and ws == list(range(ws[0], ws[-1] + 1)) else ", ".join(map(str, ws))
    if lang == "tr":
        return f"{span}. hafta" if len(ws) == 1 else f"{span}. haftalar"
    return f"week {span}" if len(ws) == 1 else f"weeks {span}"


def _rule_label(name: str) -> dict[str, str]:
    from app.ai.catalog import KINDS

    base = name.removeprefix("learned_")
    spec = KINDS.get(base)
    extra = {
        "stability": ("Kararlılık", "Stability"),
        "stability_room": ("Kararlılık (derslik)", "Stability (room)"),
        "stability_time": ("Kararlılık (saat)", "Stability (time)"),
    }
    if spec is not None:
        tr, en = spec.title["tr"], spec.title["en"]
    elif base in extra:
        tr, en = extra[base]
    else:
        tr = en = base
    if name.startswith("learned_"):
        tr, en = f"{tr} (öğrenilmiş)", f"{en} (learned)"
    return _t(tr, en)


def _placed_counts(run: ScheduleRun, placed_requests: int, total_requests: int) -> tuple[int, int]:
    st = run.stats or {}
    if st.get("placed") is not None and st.get("events_total") is not None:
        placed = int(st["placed"])
        return placed, max(0, int(st["events_total"]) - placed)
    return placed_requests, max(0, total_requests - placed_requests)


def _diag_codes(run: ScheduleRun) -> dict[str, int]:
    c: Counter[str] = Counter()
    for d in run.diagnosis or []:
        if isinstance(d, dict) and d.get("severity") == "error":
            c[str(d.get("code") or "other")] += 1
    return dict(sorted(c.items()))


def _run_brief(run: ScheduleRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "label": run.label,
        "kind": run.kind,
        "status": run.status,
        "horizon": run.horizon,
        "horizon_params": run.horizon_params or {},
        "is_active": bool(run.is_active),
        "parent_run_id": run.parent_run_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "hard_score": run.hard_score,
        "soft_score": run.soft_score,
    }


async def _pair(session: AsyncSession, a_id: int, b_id: int) -> tuple[Term, ScheduleRun, ScheduleRun]:
    if a_id == b_id:
        raise CompareError(422, _t("Aynı çalıştırma iki kez seçildi", "The same run was picked twice"))
    a = await session.get(ScheduleRun, a_id)
    b = await session.get(ScheduleRun, b_id)
    for rid, r in ((a_id, a), (b_id, b)):
        if r is None:
            raise CompareError(404, f"run {rid} not found")
    assert a is not None and b is not None
    if a.term_id != b.term_id or a.kind != b.kind:
        raise CompareError(
            422,
            _t(
                f"#{a.id} ve #{b.id} aynı dönemin aynı türden çalıştırmaları değil",
                f"runs {a.id} and {b.id} are not runs of the same term and kind",
            ),
        )
    for r in (a, b):
        if r.status not in COMPARABLE:
            raise CompareError(
                409,
                _t(
                    f"#{r.id} durumu {r.status}; bitmiş bir çalıştırma ile karşılaştırın",
                    f"run {r.id} is {r.status}; compare finished runs",
                ),
            )
    term = await session.get(Term, a.term_id)
    assert term is not None
    return term, a, b


# ------------------------------------------------------------------------------------------- per class


def _change_kind(pa: mod.Place, pb: mod.Place, date_a: Any = None, date_b: Any = None) -> str:
    time_changed = (pa.day, pa.start, pa.end) != (pb.day, pb.start, pb.end) or date_a != date_b
    room_changed = sorted(pa.room_ids) != sorted(pb.room_ids)
    weeks_changed = sorted(pa.weeks) != sorted(pb.weeks)
    if time_changed and room_changed:
        return "time_room"
    if time_changed:
        return "time"
    if room_changed:
        return "room"
    return "weeks" if weeks_changed else "split"


CHANGE_TEXT = {
    "time": ("Saat değişti", "Time changed"),
    "room": ("Derslik değişti", "Room changed"),
    "time_room": ("Saat ve derslik değişti", "Time and room changed"),
    "weeks": ("Haftalar değişti", "Weeks changed"),
    "split": ("Bölünme değişti", "Split changed"),
}


def _classify(
    keys: Iterable[int],
    labels: Mapping[int, str],
    rows_a: Mapping[int, list[Assignment]],
    rows_b: Mapping[int, list[Assignment]],
    rooms: Mapping[int, Room],
    extra: Mapping[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    moved: list[dict[str, Any]] = []
    only_a: list[dict[str, Any]] = []
    only_b: list[dict[str, Any]] = []
    unchanged = neither = 0
    by_change: Counter[str] = Counter()
    for rid in keys:
        ra, rb = list(rows_a.get(rid, [])), list(rows_b.get(rid, []))
        pa, pb = mod.place_of(ra), mod.place_of(rb)
        base = {"request_id": rid, "label": labels.get(rid, f"#{rid}"), **((extra or {}).get(rid) or {})}
        if pa is None and pb is None:
            neither += 1
            continue
        if pb is None:
            only_a.append({**base, "a": _place_out(pa, rooms), "b": None})
            continue
        if pa is None:
            only_b.append({**base, "a": None, "b": _place_out(pb, rooms)})
            continue
        if _cell_set(ra) == _cell_set(rb):
            unchanged += 1
            continue
        da = sorted({x.date.isoformat() for x in ra if x.date})
        db = sorted({x.date.isoformat() for x in rb if x.date})
        kind = _change_kind(pa, pb, da, db)
        by_change[kind] += 1
        oa, ob = _place_out(pa, rooms), _place_out(pb, rooms)
        if da or db:
            assert oa is not None and ob is not None
            oa, ob = {**oa, "dates": da}, {**ob, "dates": db}
        tr, en = CHANGE_TEXT[kind]
        moved.append({**base, "change": kind, "change_text": _t(tr, en), "a": oa, "b": ob})
    return {
        "counts": {
            "unchanged": unchanged,
            "moved": len(moved),
            "only_in_a": len(only_a),
            "only_in_b": len(only_b),
            "unplaced_in_both": neither,
            "by_change": dict(sorted(by_change.items())),
        },
        "moved": moved[:MAX_ITEMS],
        "only_in_a": only_a[:MAX_ITEMS],
        "only_in_b": only_b[:MAX_ITEMS],
        "truncated": max(len(moved), len(only_a), len(only_b)) > MAX_ITEMS,
    }


async def _course_classes(
    session: AsyncSession, term: Term, a: ScheduleRun, b: ScheduleRun, rooms: dict[int, Room]
) -> tuple[dict[str, Any], int, int, int]:
    ta = await mod.load_term(session, term, a, rooms=rooms)
    tb = await mod.load_term(session, term, b, rooms=rooms)
    scope = [mr for mr in ta.meetings if mr.needs_room and (_in_horizon(mr, a) or _in_horizon(mr, b))]
    labels = {mr.id: mod.label_of(mr) for mr in scope}
    extra = {mr.id: {"instructor_ids": [si.instructor_id for si in mr.section.instructors]} for mr in scope}
    out = _classify([mr.id for mr in scope], labels, ta.rows_by_mr, tb.rows_by_mr, rooms, extra)
    placed_a = sum(1 for mr in scope if ta.rows_by_mr.get(mr.id))
    placed_b = sum(1 for mr in scope if tb.rows_by_mr.get(mr.id))
    return out, placed_a, placed_b, len(scope)


def _exam_rows(rows: Iterable[Assignment]) -> dict[int, list[Assignment]]:
    out: dict[int, list[Assignment]] = defaultdict(list)
    for x in rows:
        if x.exam_request_id is not None:
            out[int(x.exam_request_id)].append(x)
    return out


def exam_label(er: ExamRequest) -> str:
    years = ",".join(str(y) for y in (er.class_years or ([er.class_year] if er.class_year else [])))
    prog = er.program.name if er.program is not None else None
    return " · ".join(x for x in (er.course_code, prog, f"{years}. sınıf" if years else None) if x)


async def _exam_classes(
    session: AsyncSession, term: Term, a: ScheduleRun, b: ScheduleRun, rooms: dict[int, Room]
) -> tuple[dict[str, Any], int, int, int, list[ExamRequest], dict[int, list[Assignment]], dict[int, list[Assignment]]]:
    from sqlalchemy.orm import selectinload

    reqs = list(
        (
            await session.execute(
                select(ExamRequest)
                .options(selectinload(ExamRequest.program))
                .where(ExamRequest.term_id == term.id, ExamRequest.archived.is_(False))
                .order_by(ExamRequest.source_row_index, ExamRequest.id)
            )
        ).scalars()
    )
    scope = [er for er in reqs if er.needs_room and not er.no_exam]
    rows_a = _exam_rows(await util._rows(session, a))  # noqa: SLF001
    rows_b = _exam_rows(await util._rows(session, b))  # noqa: SLF001
    labels = {er.id: exam_label(er) for er in scope}
    extra = {er.id: {"instructor_text": er.instructor_text, "enrolment": er.enrolment} for er in scope}
    out = _classify([er.id for er in scope], labels, rows_a, rows_b, rooms, extra)
    placed_a = sum(1 for er in scope if rows_a.get(er.id))
    placed_b = sum(1 for er in scope if rows_b.get(er.id))
    return out, placed_a, placed_b, len(scope), scope, rows_a, rows_b


# ------------------------------------------------------------------------------------------- per instructor


async def _course_instructors(
    session: AsyncSession, a: ScheduleRun, b: ScheduleRun, weeks: list[int]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pa = util.instructor_profiles(await util.teaching_spans(session, a, weeks), weeks)
    pb = util.instructor_profiles(await util.teaching_spans(session, b, weeks), weeks)
    ids = sorted(set(pa) | set(pb))
    names = {
        i.id: i for i in (await session.execute(select(Instructor).where(Instructor.id.in_(ids or [0])))).scalars()
    }
    zero = {"periods_per_week": 0, "gaps_per_week": 0, "days_per_week": 0, "max_periods_day": 0, "by_day": {}}
    rows: list[dict[str, Any]] = []
    for i in ids:
        x, y = pa.get(i, zero), pb.get(i, zero)
        d_load = round(y["periods_per_week"] - x["periods_per_week"], 2)
        d_gaps = round(y["gaps_per_week"] - x["gaps_per_week"], 2)
        d_days = round(y["days_per_week"] - x["days_per_week"], 2)
        if d_load == 0 and d_gaps == 0 and d_days == 0 and x.get("by_day") == y.get("by_day"):
            continue
        ins = names.get(i)
        rows.append(
            {
                "instructor_id": i,
                "name": ins.full_name if ins is not None else f"#{i}",
                "a": {k: x[k] for k in zero},
                "b": {k: y[k] for k in zero},
                "delta": {"periods_per_week": d_load, "gaps_per_week": d_gaps, "days_per_week": d_days},
            }
        )
    rows.sort(key=lambda r: (-abs(r["delta"]["gaps_per_week"]), -abs(r["delta"]["periods_per_week"]), r["name"]))

    def agg(p: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
        loads = [v["periods_per_week"] for v in p.values()]
        return {
            "gaps_per_week_total": round(sum(v["gaps_per_week"] for v in p.values()), 2),
            "instructors_with_gaps": sum(1 for v in p.values() if v["gaps_per_week"] > 0),
            "periods_per_week_max": max(loads) if loads else 0,
            "instructors": len(p),
        }

    return rows[:MAX_ITEMS], {"a": agg(pa), "b": agg(pb), "changed": len(rows)}


def _exam_people(reqs: Iterable[ExamRequest], rows: Mapping[int, list[Assignment]]) -> dict[str, dict[str, Any]]:
    """Named exam instructors (the exam list's free-text column, split into people): exams per date."""
    out: dict[str, dict[str, Any]] = {}
    for er in reqs:
        placed = rows.get(er.id) or []
        if not placed:
            continue
        dates = sorted({x.date.isoformat() for x in placed if x.date})
        for raw in n.split_person_names(er.instructor_text):
            if n.non_person_reason(raw) is not None:
                continue
            p = n.canon_person_name(raw)
            if p is None:
                continue
            e = out.setdefault(p.canonical, {"name": p.full_name, "per_date": Counter()})
            for d in dates:
                e["per_date"][d] += 1
    return out


def _exam_instructors(
    reqs: list[ExamRequest], rows_a: Mapping[int, list[Assignment]], rows_b: Mapping[int, list[Assignment]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pa, pb = _exam_people(reqs, rows_a), _exam_people(reqs, rows_b)
    rows: list[dict[str, Any]] = []
    for key in sorted(set(pa) | set(pb)):
        x = pa.get(key, {"per_date": Counter()})
        y = pb.get(key, {"per_date": Counter()})
        if x["per_date"] == y["per_date"]:
            continue
        rows.append(
            {
                "key": key,
                "name": (pa.get(key) or pb.get(key) or {}).get("name", key),
                "a": {"exams": sum(x["per_date"].values()), "max_per_day": max(x["per_date"].values(), default=0)},
                "b": {"exams": sum(y["per_date"].values()), "max_per_day": max(y["per_date"].values(), default=0)},
                "a_dates": dict(sorted(x["per_date"].items())),
                "b_dates": dict(sorted(y["per_date"].items())),
            }
        )

    def agg(p: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "instructors": len(p),
            "with_two_or_more_a_day": sum(1 for v in p.values() if max(v["per_date"].values(), default=0) >= 2),
        }

    return rows[:MAX_ITEMS], {"a": agg(pa), "b": agg(pb), "changed": len(rows)}


# ------------------------------------------------------------------------------------------- per room


def _room_deltas(ua: Mapping[int, dict[str, Any]], ub: Mapping[int, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for rid in sorted(set(ua) | set(ub)):
        x, y = ua.get(rid), ub.get(rid)
        base = x or y
        assert base is not None
        ox, oy = (x or {}).get("occupied", 0), (y or {}).get("occupied", 0)
        if ox == oy:
            continue
        px, py = (x or {}).get("pct", 0.0), (y or {}).get("pct", 0.0)
        rows.append(
            {
                "room_id": rid,
                "code": base["code"],
                "building": base["building"],
                "a": {"occupied": ox, "pct": px},
                "b": {"occupied": oy, "pct": py},
                "delta": {"occupied": oy - ox, "pct": round(py - px, 1)},
            }
        )
    rows.sort(key=lambda r: (-abs(r["delta"]["occupied"]), r["code"]))
    return rows


def _by_building(u: Mapping[int, dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"occupied": 0, "capacity": 0, "blocked": 0})
    for v in u.values():
        b = out[v["building"]]
        b["occupied"] += v["occupied"]
        b["capacity"] += v["capacity"]
        b["blocked"] += v["blocked"]
    return out


def _pct(x: Mapping[str, int]) -> float:
    free = x["capacity"] - x["blocked"]
    return round(100 * x["occupied"] / free, 1) if free > 0 else 0.0


# ------------------------------------------------------------------------------------------- compare


async def compare(session: AsyncSession, a_id: int, b_id: int, week: int | None = None) -> dict[str, Any]:
    term, a, b = await _pair(session, a_id, b_id)
    rooms = await mod.all_rooms(session)
    exam = a.kind == "EXAM"
    # round-1 R1-M-10: runs with different horizons (a week run against a term run) are compared on the weeks
    # they share; metrics a side has no data for are "not comparable", never "B is better"
    from app.services.publish_guard import run_weeks

    weeks_a, weeks_b = await run_weeks(session, a), await run_weeks(session, b)
    common = sorted(set(weeks_a) & set(weeks_b))
    scope_differs = sorted(weeks_a) != sorted(weeks_b)
    if not exam and week is None and scope_differs and common:
        week = common[0]
    if exam:
        classes, pl_a, pl_b, total, reqs, rows_a, rows_b = await _exam_classes(session, term, a, b, rooms)
    else:
        classes, pl_a, pl_b, total = await _course_classes(session, term, a, b, rooms)
    # rooms: one set of weeks for both runs, so the percentages are comparable
    scope = "term" if exam else "week"
    sa = await util.build_scope(session, run_id=a.id, week=week, scope=scope, bookings=False)
    if exam:
        sb = await util.build_scope(session, run_id=b.id, week=week, scope=scope, bookings=False)
        if sorted(sb.weeks) != sorted(sa.weeks):
            union = sorted(set(sa.weeks) | set(sb.weeks))
            sa = await util.build_scope(session, run_id=a.id, weeks=union, bookings=False)
            sb = await util.build_scope(session, run_id=b.id, weeks=union, bookings=False)
    else:
        sb = await util.build_scope(session, run_id=b.id, weeks=sa.weeks, bookings=False)
    weeks = sa.weeks
    ua, ub = util.room_usage(sa), util.room_usage(sb)
    ba, bb = _by_building(ua), _by_building(ub)
    tot_a = {k: sum(v[k] for v in ba.values()) for k in ("occupied", "capacity", "blocked")}
    tot_b = {k: sum(v[k] for v in bb.values()) for k in ("occupied", "capacity", "blocked")}
    if exam:
        instructors, ins_agg = _exam_instructors(reqs, rows_a, rows_b)
    else:
        instructors, ins_agg = await _course_instructors(session, a, b, weeks)
    placed_a, unplaced_a = _placed_counts(a, pl_a, total)
    placed_b, unplaced_b = _placed_counts(b, pl_b, total)
    br_a = dict((a.stats or {}).get("objective_breakdown") or {})
    br_b = dict((b.stats or {}).get("objective_breakdown") or {})
    rules = []
    for name in sorted(set(br_a) | set(br_b)):
        va, vb = int(br_a.get(name) or 0), int(br_b.get(name) or 0)
        rules.append(
            {
                "rule": name,
                "label": _rule_label(name),
                "a": va,
                "b": vb,
                "delta": vb - va,
                "better": None if scope_differs else ("same" if va == vb else ("b" if vb < va else "a")),
                "comparable": not scope_differs,
            }
        )
    waived_a = list((a.stats or {}).get("waived_rules") or [])
    waived_b = list((b.stats or {}).get("waived_rules") or [])
    errs_a, errs_b = _diag_codes(a), _diag_codes(b)
    # the scoped weeks hold rows of both runs? (a week run has none outside its weeks)
    both = bool(tot_a["occupied"]) == bool(tot_b["occupied"]) and (not scope_differs or bool(common))
    metrics = [
        _metric("hard_score", a.hard_score, b.hard_score),
        _metric("soft_score", a.soft_score, b.soft_score),
        _metric("placed", placed_a, placed_b),
        _metric("unplaced", unplaced_a, unplaced_b),
        _metric("diagnoses_errors", sum(errs_a.values()), sum(errs_b.values())),
        _metric("waived_rules", len(waived_a), len(waived_b)),
        _metric("objective", sum(int(v or 0) for v in br_a.values()), sum(int(v or 0) for v in br_b.values())),
        _metric("utilisation_pct", _pct(tot_a), _pct(tot_b), comparable=both),
    ]
    if not exam:
        for k in ("gaps_per_week_total", "instructors_with_gaps", "periods_per_week_max"):
            metrics.append(_metric(k, ins_agg["a"][k], ins_agg["b"][k], comparable=both))
    if scope_differs:
        # placement counts of a week run and a term run measure different things
        for m in metrics:
            if m["key"] in ("placed", "unplaced", "objective", "soft_score", "diagnoses_errors"):
                m.update(_metric(m["key"], None, None, comparable=False))
                m["a"], m["b"] = (
                    {"placed": placed_a, "unplaced": unplaced_a}.get(m["key"]),
                    {"placed": placed_b, "unplaced": unplaced_b}.get(m["key"]),
                )
    c = classes["counts"]
    soft_d = (b.soft_score or 0) - (a.soft_score or 0)
    headline = _t(
        f"#{b.id}, #{a.id} ile karşılaştırıldı: {c['moved']} {'sınav' if exam else 'ders'} taşındı, "
        f"{c['only_in_b']} yalnız B'de, {c['only_in_a']} yalnız A'da yerleşti; "
        f"sert {a.hard_score}→{b.hard_score}, yumuşak {a.soft_score}→{b.soft_score} ({soft_d:+d})",
        f"#{b.id} against #{a.id}: {c['moved']} {'exam(s)' if exam else 'class(es)'} moved, "
        f"{c['only_in_b']} placed only in B, {c['only_in_a']} only in A; "
        f"hard {a.hard_score}→{b.hard_score}, soft {a.soft_score}→{b.soft_score} ({soft_d:+d})",
    )
    scope_info = {
        "a_weeks": weeks_a,
        "b_weeks": weeks_b,
        "common_weeks": common,
        "compared_weeks": list(weeks),
        "differs": scope_differs,
        "note": _t(
            f"Kapsamlar farklı (A {_weeks_text(weeks_a, 'tr')}, B {_weeks_text(weeks_b, 'tr')}); "
            + (
                f"yalnız ortak {_weeks_text(list(weeks), 'tr')} karşılaştırıldı, diğer değerler karşılaştırılamaz."
                if common
                else "ortak hafta yok: değerler karşılaştırılamaz."
            ),
            f"The scopes differ (A {_weeks_text(weeks_a, 'en')}, B {_weeks_text(weeks_b, 'en')}); "
            + (
                f"only the shared {_weeks_text(list(weeks), 'en')} are compared, other values are not comparable."
                if common
                else "no shared week: the values are not comparable."
            ),
        )
        if scope_differs
        else None,
    }
    if scope_differs:
        headline = {k: f"{headline[k]} · {scope_info['note'][k]}" for k in ("tr", "en")}  # type: ignore[index]
    return {
        "term_id": term.id,
        "term_code": term.code,
        "kind": a.kind,
        "a": _run_brief(a),
        "b": _run_brief(b),
        "scope": scope_info,
        "headline": headline,
        "metrics": metrics,
        "classes": classes,
        "requests_in_scope": total,
        "instructors": {"rows": instructors, **ins_agg},
        "rooms": {
            "weeks": weeks,
            "a": {**tot_a, "pct": _pct(tot_a)},
            "b": {**tot_b, "pct": _pct(tot_b)},
            "by_building": [
                {
                    "building": k,
                    "a": {
                        **ba.get(k, {"occupied": 0, "capacity": 0, "blocked": 0}),
                        "pct": _pct(ba[k]) if k in ba else 0.0,
                    },
                    "b": {
                        **bb.get(k, {"occupied": 0, "capacity": 0, "blocked": 0}),
                        "pct": _pct(bb[k]) if k in bb else 0.0,
                    },
                }
                for k in sorted(set(ba) | set(bb))
            ],
            "changed": _room_deltas(ua, ub),
        },
        "rules": rules,
        "waived_rules": {"a": waived_a, "b": waived_b},
        "diagnoses": {"a": errs_a, "b": errs_b},
        "definitions": {
            "delta": _t("Fark = B − A (A temel, B senaryo)", "Delta = B − A (A is the baseline, B the scenario)"),
            "moved": _t(
                "Taşındı: iki çalıştırmada da yerleşti ama gün, saat, derslik ya da haftalar farklı",
                "Moved: placed in both runs, at a different day, time, room or weeks",
            ),
            "rooms": _t(
                "Doluluk aynı haftalar üzerinden hesaplanır (bkz. weeks)",
                "Utilisation is counted over the same weeks for both runs (see weeks)",
            ),
        },
    }


def compare_csv(data: Mapping[str, Any], part: str = "classes") -> str:
    """CSV of one part of a comparison: ``classes`` (moved / only in A / only in B), ``instructors``, ``rooms``,
    ``rules`` or ``metrics``."""
    buf = io.StringIO()
    w = safe_writer(csv.writer(buf))  # formula injection (W3-SEC)
    if part == "classes":
        w.writerow(
            ["status", "request_id", "label", "change", "a_when", "a_rooms", "a_weeks", "b_when", "b_rooms", "b_weeks"]
        )
        cl = data["classes"]
        for status, items in (("moved", cl["moved"]), ("only_in_a", cl["only_in_a"]), ("only_in_b", cl["only_in_b"])):
            for it in items:
                pa, pb = it.get("a") or {}, it.get("b") or {}
                w.writerow(
                    [
                        status,
                        it["request_id"],
                        it["label"],
                        it.get("change", ""),
                        (pa.get("when") or {}).get("tr", ""),
                        " + ".join(pa.get("rooms") or []),
                        " ".join(str(x) for x in pa.get("weeks") or []),
                        (pb.get("when") or {}).get("tr", ""),
                        " + ".join(pb.get("rooms") or []),
                        " ".join(str(x) for x in pb.get("weeks") or []),
                    ]
                )
    elif part == "instructors":
        rows = data["instructors"]["rows"]
        if data["kind"] == "EXAM":
            w.writerow(["key", "name", "a_exams", "a_max_per_day", "b_exams", "b_max_per_day"])
            for r in rows:
                w.writerow(
                    [
                        r["key"],
                        r["name"],
                        r["a"]["exams"],
                        r["a"]["max_per_day"],
                        r["b"]["exams"],
                        r["b"]["max_per_day"],
                    ]
                )
        else:
            w.writerow(
                [
                    "instructor_id",
                    "name",
                    "a_periods_week",
                    "b_periods_week",
                    "a_gaps_week",
                    "b_gaps_week",
                    "a_days",
                    "b_days",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r["instructor_id"],
                        r["name"],
                        r["a"]["periods_per_week"],
                        r["b"]["periods_per_week"],
                        r["a"]["gaps_per_week"],
                        r["b"]["gaps_per_week"],
                        r["a"]["days_per_week"],
                        r["b"]["days_per_week"],
                    ]
                )
    elif part == "rooms":
        w.writerow(
            ["room_id", "code", "building", "a_occupied", "b_occupied", "delta_occupied", "a_pct", "b_pct", "delta_pct"]
        )
        for r in data["rooms"]["changed"]:
            w.writerow(
                [
                    r["room_id"],
                    r["code"],
                    r["building"],
                    r["a"]["occupied"],
                    r["b"]["occupied"],
                    r["delta"]["occupied"],
                    r["a"]["pct"],
                    r["b"]["pct"],
                    r["delta"]["pct"],
                ]
            )
    elif part == "rules":
        w.writerow(["rule", "label_tr", "label_en", "a", "b", "delta"])
        for r in data["rules"]:
            w.writerow([r["rule"], r["label"]["tr"], r["label"]["en"], r["a"], r["b"], r["delta"]])
    elif part == "metrics":
        w.writerow(["metric", "label_tr", "label_en", "a", "b", "delta", "better"])
        for m in data["metrics"]:
            w.writerow([m["key"], m["label"]["tr"], m["label"]["en"], m["a"], m["b"], m["delta"], m["better"] or ""])
    else:
        raise CompareError(422, "part must be classes, instructors, rooms, rules or metrics")
    return buf.getvalue()
