"""JSON (de)serialisation of the solver contract (plain dicts; no pydantic dependency)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from app.solver.model import Assignment, Block, Constraint, Diagnosis, Event, Room, SolverInput, SolverResult


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def assignment_to_dict(a: Assignment) -> dict[str, Any]:
    return {
        "event_id": a.event_id,
        "day": a.day,
        "start": a.start,
        "end": a.end,
        "room_ids": list(a.room_ids),
        "weeks": sorted(a.weeks),
        "date": a.date.isoformat() if a.date else None,
    }


def assignment_from_dict(d: Mapping[str, Any]) -> Assignment:
    return Assignment(
        event_id=int(d["event_id"]),
        day=int(d["day"]),
        start=int(d["start"]),
        end=int(d["end"]),
        room_ids=tuple(int(r) for r in d.get("room_ids", [])),
        weeks=frozenset(int(w) for w in d.get("weeks", [])),
        date=_date(d.get("date")),
    )


def room_to_dict(r: Room) -> dict[str, Any]:
    return {"id": r.id, "code": r.code, "capacity": r.capacity, "exam_capacity": r.exam_capacity, "building": r.building, "tags": sorted(r.tags)}


def room_from_dict(d: Mapping[str, Any]) -> Room:
    cap = int(d["capacity"])
    return Room(
        id=int(d["id"]),
        code=str(d["code"]),
        capacity=cap,
        exam_capacity=int(d.get("exam_capacity", cap // 2)),
        building=str(d.get("building", "")),
        tags=frozenset(str(t) for t in d.get("tags", [])),
    )


def event_to_dict(e: Event) -> dict[str, Any]:
    d = asdict(e)
    for k in ("weeks", "allowed_days", "required_tags", "forbidden_tags", "required_room_ids", "forbidden_room_ids", "cohort_keys", "instructor_keys"):
        d[k] = sorted(getattr(e, k))
    d["preferred_room_ids"] = list(e.preferred_room_ids)
    d["fixed_date"] = e.fixed_date.isoformat() if e.fixed_date else None
    d["locked"] = assignment_to_dict(e.locked) if e.locked else None
    return d


def event_from_dict(d: Mapping[str, Any]) -> Event:
    return Event(
        id=int(d["id"]),
        kind="exam" if d.get("kind") == "exam" else "course",
        label=str(d.get("label", f"#{d['id']}")),
        size=int(d.get("size", 0)),
        duration=int(d.get("duration", 1)),
        weeks=frozenset(int(w) for w in d.get("weeks", [])),
        fixed_day=None if d.get("fixed_day") is None else int(d["fixed_day"]),
        fixed_start=None if d.get("fixed_start") is None else int(d["fixed_start"]),
        allowed_days=frozenset(int(x) for x in d.get("allowed_days", [])),
        earliest_start=int(d.get("earliest_start", 1)),
        latest_end=int(d.get("latest_end", 18)),
        fixed_date=_date(d.get("fixed_date")),
        required_tags=frozenset(str(t) for t in d.get("required_tags", [])),
        forbidden_tags=frozenset(str(t) for t in d.get("forbidden_tags", [])),
        required_room_ids=frozenset(int(x) for x in d.get("required_room_ids", [])),
        preferred_room_ids=tuple(int(x) for x in d.get("preferred_room_ids", [])),
        preferred_building=d.get("preferred_building"),
        forbidden_room_ids=frozenset(int(x) for x in d.get("forbidden_room_ids", [])),
        min_rooms=int(d.get("min_rooms", 1)),
        max_rooms=int(d.get("max_rooms", 1)),
        cohort_keys=frozenset(str(k) for k in d.get("cohort_keys", [])),
        instructor_keys=frozenset(str(k) for k in d.get("instructor_keys", [])),
        same_room_group=d.get("same_room_group"),
        locked=assignment_from_dict(d["locked"]) if d.get("locked") else None,
        needs_room=bool(d.get("needs_room", True)),
    )


def constraint_to_dict(c: Constraint) -> dict[str, Any]:
    return {"kind": c.kind, "params": dict(c.params), "hard": c.hard, "weight": c.weight, "id": c.id}


def constraint_from_dict(d: Mapping[str, Any]) -> Constraint:
    return Constraint(kind=str(d["kind"]), params=dict(d.get("params", {})), hard=bool(d.get("hard", True)), weight=int(d.get("weight", 1)), id=d.get("id"))


def block_to_dict(b: Block) -> dict[str, Any]:
    return {"room_id": b.room_id, "week": b.week, "day": b.day, "start": b.start, "end": b.end}


def block_from_dict(d: Mapping[str, Any]) -> Block:
    return Block(int(d["room_id"]), None if d.get("week") is None else int(d["week"]), int(d["day"]), int(d["start"]), int(d["end"]))


def input_to_dict(inp: SolverInput) -> dict[str, Any]:
    return {
        "rooms": [room_to_dict(r) for r in inp.rooms],
        "events": [event_to_dict(e) for e in inp.events],
        "constraints": [constraint_to_dict(c) for c in inp.constraints],
        "days": list(inp.days),
        "periods_per_day": inp.periods_per_day,
        "weeks": list(inp.weeks),
        "blocks": [block_to_dict(b) for b in inp.blocks],
        "previous": [assignment_to_dict(a) for a in inp.previous],
        "time_limit_s": inp.time_limit_s,
        "seed": inp.seed,
        "workers": inp.workers,
        "weights": dict(inp.weights),
    }


def input_from_dict(d: Mapping[str, Any]) -> SolverInput:
    return SolverInput(
        rooms=tuple(room_from_dict(r) for r in d.get("rooms", [])),
        events=tuple(event_from_dict(e) for e in d.get("events", [])),
        constraints=tuple(constraint_from_dict(c) for c in d.get("constraints", [])),
        days=tuple(int(x) for x in d.get("days", (1, 2, 3, 4, 5, 6, 7))),
        periods_per_day=int(d.get("periods_per_day", 18)),
        weeks=tuple(int(w) for w in d.get("weeks", range(1, 15))),
        blocks=tuple(block_from_dict(b) for b in d.get("blocks", [])),
        previous=tuple(assignment_from_dict(a) for a in d.get("previous", [])),
        time_limit_s=float(d.get("time_limit_s", 60.0)),
        seed=int(d.get("seed", 0)),
        workers=int(d.get("workers", 8)),
        weights={str(k): int(v) for k, v in d.get("weights", {}).items()},
    )


def result_to_dict(res: SolverResult) -> dict[str, Any]:
    return {
        "status": res.status,
        "assignments": [assignment_to_dict(a) for a in res.assignments],
        "hard_score": res.hard_score,
        "soft_score": res.soft_score,
        "objective_breakdown": dict(res.objective_breakdown),
        "diagnoses": [asdict(d) for d in res.diagnoses],
        "stats": {k: v for k, v in res.stats.items() if k != "traceback"},
    }


def result_from_dict(d: Mapping[str, Any]) -> SolverResult:
    return SolverResult(
        status=d["status"],
        assignments=[assignment_from_dict(a) for a in d.get("assignments", [])],
        hard_score=int(d.get("hard_score", 0)),
        soft_score=int(d.get("soft_score", 0)),
        objective_breakdown={str(k): int(v) for k, v in d.get("objective_breakdown", {}).items()},
        diagnoses=[Diagnosis(list(x.get("event_ids", [])), list(x.get("constraint_kinds", [])), str(x.get("message", "")), list(x.get("suggestions", [])), str(x.get("severity", "error"))) for x in d.get("diagnoses", [])],
        stats=dict(d.get("stats", {})),
    )


def dump_input(inp: SolverInput, path: str | Path) -> None:
    Path(path).write_text(json.dumps(input_to_dict(inp), indent=1, ensure_ascii=False), encoding="utf-8")


def load_input(path: str | Path) -> SolverInput:
    return input_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = [
    "assignment_from_dict",
    "assignment_to_dict",
    "dump_input",
    "input_from_dict",
    "input_to_dict",
    "load_input",
    "result_from_dict",
    "result_to_dict",
]
