"""Critic / verifier: cross-check the records against each other and against the solver's static checker.

Deterministic checks (always run):

* ``time_order``: end not after start (from the extractor's warnings);
* ``unknown_room``: an assigned room that no room list or timetable header defines;
* ``capacity``: enrolment above the seats of the assigned room(s);
* ``source_double_booking``: two different requests in the same room, day and time, in overlapping weeks;
* ``exam_weekend``: an exam on a Saturday or Sunday (information only);
* ``solver_static``: the records are built into a :class:`app.solver.model.SolverInput` (rooms, fixed-time
  events, cohort and instructor keys, locked rooms) and :func:`app.solver.diagnose.static_check` runs on it.
  This finds requests that no room can host, clashes between fixed requests, and slots with more
  requests than rooms.

The model-based judge (:func:`app.council.llm.judge`) adds ``judge_mismatch`` issues for sampled records
whose fields disagree with their source row. It flags records and never edits them.
"""

from __future__ import annotations

import logging
import time as _time
from collections import defaultdict
from datetime import date
from typing import Any

from app.council import text as tx
from app.council.reconcile import rid, room_key

log = logging.getLogger(__name__)

Record = dict[str, Any]
MAX_SAMPLES = 8


def _issue(code: str, severity: str, message: str, refs: list[str], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "records": refs[:50],
        "sources": sources[:MAX_SAMPLES],
    }


def _overlap(a: Record, b: Record) -> bool:
    a_s, a_e = tx.from_hhmm(a.get("start")), tx.from_hhmm(a.get("end"))
    b_s, b_e = tx.from_hhmm(b.get("start")), tx.from_hhmm(b.get("end"))
    if not (a_s and a_e and b_s and b_e):
        return False
    if tx.minutes(a_s) >= tx.minutes(b_e) or tx.minutes(b_s) >= tx.minutes(a_e):
        return False
    wa, wb = set(a.get("weeks") or []), set(b.get("weeks") or [])
    return not wa or not wb or bool(wa & wb)


def period_index(periods: list[dict[str, Any]], t: str | None, kind: str) -> int | None:
    """Clock time -> 1-based period of ``periods`` (start: the period containing it; end: the last
    period starting before it)."""
    tt = tx.from_hhmm(t)
    if tt is None or not periods:
        return None
    m = tx.minutes(tt)
    starts = [tx.minutes(tx.from_hhmm(p["start"]) or tt) for p in periods]
    ends = [tx.minutes(tx.from_hhmm(p["end"]) or tt) for p in periods]
    if kind == "start":
        for i, (s, e) in enumerate(zip(starts, ends, strict=True)):
            if s <= m < e or m < s:
                return i + 1
        return None
    cand = [i + 1 for i, s in enumerate(starts) if s < m]
    return cand[-1] if cand else None


def _static(
    dataset: dict[str, Any], records: dict[int, list[Record]], periods: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    from app.solver import model as sm
    from app.solver.build import prepare
    from app.solver.diagnose import static_check

    rooms: list[sm.Room] = []
    room_ids: dict[str, int] = {}
    for i, r in enumerate(dataset.get("rooms", []), start=1):
        cap = int(r.get("capacity") or 0)
        if cap <= 0:
            continue
        room_ids[r["key"]] = i
        rooms.append(
            sm.Room(
                i,
                r["code"],
                cap,
                int(r.get("exam_capacity") or cap),
                str(r.get("building") or ""),
                frozenset(r.get("tags") or []),
            )
        )
    if not rooms:
        return []
    events: list[sm.Event] = []
    labels: dict[int, tuple[str, dict[str, Any]]] = {}
    duplicates = dataset.get("duplicates", {})
    n_periods = len(periods)
    eid = 0
    for fi, recs in records.items():
        for i, r in enumerate(recs):
            if r["type"] != "meeting" or rid(fi, i) in duplicates or not r.get("needs_room"):
                continue
            days = r.get("days") or []
            s = period_index(periods, r.get("start"), "start")
            e = period_index(periods, r.get("end"), "end")
            if len(days) != 1 or s is None or e is None or e < s:
                continue
            eid += 1
            ids = [room_ids[k] for k in (room_key(c) for c in r.get("rooms") or []) if k in room_ids]
            weeks = frozenset(r.get("weeks") or range(1, 15))
            locked = sm.Assignment(eid, days[0], s, e, tuple(ids), weeks) if ids else None
            prog = tx.fold(r.get("program") or "")
            cohorts = frozenset(f"PROG:{prog}:Y{y}" for y in (r.get("class_years") or [])) if prog else frozenset()
            ins = frozenset(f"INS:{tx.person_key(p)}" for p in r.get("instructors") or [] if tx.person_key(p))
            label = f"{tx.display_course(r['course_code'])}" + (f" §{r['section']}" if r.get("section") else "")
            events.append(
                sm.Event(
                    eid,
                    "course",
                    label,
                    int(r.get("enrolment") or 0),
                    e - s + 1,
                    weeks,
                    days[0],
                    s,
                    frozenset(days),
                    1,
                    n_periods,
                    locked=locked,
                    cohort_keys=cohorts,
                    instructor_keys=ins,
                )
            )
            labels[eid] = (rid(fi, i), r["source"])
    if not events:
        return []
    inp = sm.SolverInput(
        rooms=tuple(rooms),
        events=tuple(events),
        constraints=(),
        periods_per_day=n_periods,
        trust_locked_rooms=True,
        fixed_conflicts_as_warnings=False,
    )
    t0 = _time.perf_counter()
    try:
        diags = static_check(prepare(inp))
    except Exception as exc:  # noqa: BLE001 - the critic must not fail the job
        log.warning("static check failed: %s", type(exc).__name__)
        return [
            _issue("solver_static_failed", "info", f"solver static check could not run ({type(exc).__name__})", [], [])
        ]
    log.info("council static check: %d events, %d diagnoses, %.2fs", len(events), len(diags), _time.perf_counter() - t0)
    grouped: dict[str, list[Any]] = defaultdict(list)
    for d in diags:
        grouped[d.code or "diagnosis"].append(d)
    out = []
    for code, ds in grouped.items():
        refs = [labels[e][0] for d in ds for e in d.event_ids if e in labels]
        srcs = [labels[e][1] for d in ds for e in d.event_ids if e in labels]
        # findings describe the source data as the planner wrote it (shared rooms, joint lectures):
        # the reviewer decides; the solver's real-data modes treat them as warnings too
        sev = "error" if code == "no_room" else "warning"
        examples = "; ".join(d.message for d in ds[:2])
        msg = f"solver pre-check ({code}): {len(ds)} finding(s); e.g. {examples}"
        out.append(_issue(f"solver_static:{code}", sev, msg[:1200], refs, srcs))
    return out


def check(
    dataset: dict[str, Any], records: dict[int, list[Record]], plan: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    duplicates = dataset.get("duplicates", {})
    rooms = {r["key"]: r for r in dataset.get("rooms", [])}
    room_defined = {
        r["key"]
        for r in dataset.get("rooms", [])
        if r.get("capacity") or any("sheet" in s or "table" in s or "row" in s for s in r.get("sources", []))
    }

    bad_time: list[tuple[str, dict[str, Any]]] = []
    unknown: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    over: list[tuple[str, dict[str, Any], str]] = []
    weekend: list[tuple[str, dict[str, Any]]] = []
    by_slot: dict[tuple[str, int], list[tuple[str, Record]]] = defaultdict(list)
    for fi, recs in records.items():
        for i, r in enumerate(recs):
            ref = rid(fi, i)
            if ref in duplicates or r["type"] not in ("meeting", "exam"):
                continue
            if any("is not after start" in w for w in r.get("warnings", [])):
                bad_time.append((ref, r["source"]))
            keys = [room_key(c) for c in r.get("rooms") or []]
            for c, k in zip(r.get("rooms") or [], keys, strict=True):
                if room_defined and k not in room_defined:
                    unknown[c].append((ref, r["source"]))
            seats = sum(
                int((rooms.get(k) or {}).get("exam_capacity" if r["type"] == "exam" else "capacity") or 0) for k in keys
            )
            if keys and seats and r.get("enrolment") and int(r["enrolment"]) > seats:
                over.append(
                    (
                        ref,
                        r["source"],
                        f"{r['course_code']}: {r['enrolment']} students, {seats} seats in {', '.join(r['rooms'])}",
                    )
                )
            if r["type"] == "exam" and r.get("date"):
                if date.fromisoformat(r["date"]).isoweekday() >= 6:
                    weekend.append((ref, r["source"]))
            if r["type"] == "meeting" and r.get("needs_room") and len(r.get("days") or []) == 1:
                for k in set(keys):
                    by_slot[(k, r["days"][0])].append((ref, r))
    if bad_time:
        issues.append(
            _issue(
                "time_order",
                "error",
                f"{len(bad_time)} request(s) end before they start",
                [x[0] for x in bad_time],
                [x[1] for x in bad_time],
            )
        )
    for code, hits in sorted(unknown.items(), key=lambda kv: -len(kv[1]))[:20]:
        issues.append(
            _issue(
                "unknown_room",
                "warning",
                f"room {code} is assigned {len(hits)} time(s) but no room list or timetable header defines it",
                [h[0] for h in hits],
                [h[1] for h in hits],
            )
        )
    if over:
        issues.append(
            _issue(
                "capacity",
                "warning",
                f"{len(over)} request(s) have more students than seats in their assigned room(s); e.g. "
                + "; ".join(o[2] for o in over[:3]),
                [o[0] for o in over],
                [o[1] for o in over],
            )
        )
    clashes: list[tuple[str, str, dict[str, Any], str]] = []
    for (k, day), items in by_slot.items():
        items.sort(key=lambda x: x[1].get("start") or "")
        for a_i in range(len(items)):
            for b_i in range(a_i + 1, len(items)):
                ra, a = items[a_i]
                rb, b = items[b_i]
                if (b.get("start") or "") >= (a.get("end") or ""):
                    break
                if a["course_code"] != b["course_code"] and _overlap(a, b):
                    clashes.append(
                        (
                            ra,
                            rb,
                            b["source"],
                            f"{(rooms.get(k) or {}).get('code', k)} day {day}: "
                            f"{a['course_code']} {a.get('start')}-{a.get('end')} vs "
                            f"{b['course_code']} {b.get('start')}-{b.get('end')}",
                        )
                    )
    periods = (plan or {}).get("period_grid", {}).get("periods") or []
    static = _static(dataset, records, periods) if periods else []
    # the solver's locked_overlap finding covers the same clashes; report ours only without it
    if clashes and not any(s["code"] == "solver_static:locked_overlap" for s in static):
        issues.append(
            _issue(
                "source_double_booking",
                "warning",
                f"{len(clashes)} pair(s) of requests hold the same room at overlapping times in the source files; e.g. "
                + "; ".join(c[3] for c in clashes[:3]),
                [c[0] for c in clashes] + [c[1] for c in clashes],
                [c[2] for c in clashes],
            )
        )
    if weekend:
        issues.append(
            _issue(
                "exam_weekend",
                "info",
                f"{len(weekend)} exam(s) are on a Saturday or Sunday",
                [w[0] for w in weekend],
                [w[1] for w in weekend],
            )
        )
    for c in dataset.get("conflicts", []):
        issues.append(
            _issue(
                "room_capacity_conflict",
                "warning",
                f"room {c['room']}: room lists disagree on capacity {c['values']}; using {c['chosen']}",
                [],
                c.get("sources", []),
            )
        )
    issues.extend(static)
    return issues


__all__ = ["check", "period_index"]
