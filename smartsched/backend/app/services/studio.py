"""Generator Studio core: per-user drafts, the draft-aware ``SolverInput`` and studio runs.

The bridge (:func:`app.services.solver_bridge.build_solver_input`) builds the term-wide input; a
draft then edits that input through the frozen solver contract only (``dataclasses.replace``):

* **left-out classes** (``excluded_event_ids``, per draft, never term-wide): request ids are removed
  from the event -> requests map; an event whose requests are all left out is dropped, a merged joint
  lecture that keeps some members shrinks to the seats of the members that stay;
* **pins** (draft only): ``required_room_ids`` and/or fixed day + start period;
* **per-draft rule switches**: ``disabled_rule_ids`` drop term rules, ``rule_overrides`` change
  hardness / weight for this draft only;
* **built-in rules switched off** (ADMIN): recorded as ``constraints`` rows with ``source=BUILTIN``,
  ``enabled=false`` and ``source_ref={"draft_id": ...}`` (the plain bridge never loads disabled rows);
  honoured here: the overlap kinds are configured to check a key nobody carries (and instructor keys
  are cleared after instructor selectors were frozen into event ids, so every solver path honours
  it); ``capacity`` becomes a strong preference.

Runs generated from a draft carry the draft snapshot in ``params["studio"]`` and are solved by
:func:`run_draft_schedule`, so a draft edited while the run is queued does not change that run.
:func:`build_solver_input_for_run` honours the snapshot for any run (use it from the bridge's
``run_schedule`` to make child runs of studio runs keep their draft).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ConstraintRow,
    ExamRequest,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    StudioDraft,
    StudioPreset,
    Term,
    User,
    Week,
)
from app.services import settings_service as ss
from app.services import solver_bridge
from app.solver import model as sm
from app.workers.queue import JobState, get_queue, worker_id

log = logging.getLogger(__name__)

KINDS = ("COURSE", "EXAM")
HORIZONS = ("WEEK", "MONTH", "TERM")
#: always-on rules shown on Built-in cards; value = may an ADMIN switch it off in a draft?
BUILTINS: dict[str, bool] = {
    "no_room_overlap": False,
    "capacity": True,
    "no_cohort_overlap": True,
    "no_instructor_overlap": True,
}
BUILTIN_TEXT: dict[str, dict[str, str]] = {
    "no_room_overlap": {"tr": "Bir derslikte aynı anda tek ders", "en": "One class per room at a time"},
    "capacity": {"tr": "Derslik öğrencilere yetmeli", "en": "The room must seat the class"},
    "no_cohort_overlap": {
        "tr": "Aynı program ve sınıfın dersleri çakışmaz",
        "en": "No clash for a programme-year",
    },
    "no_instructor_overlap": {
        "tr": "Bir öğretim elemanı aynı anda iki derste olamaz",
        "en": "No clash for an instructor",
    },
}
#: a cohort / instructor key no event carries: the overlap kinds then check nothing
NO_KEY = "__studio_disabled__"
DRAFT_PARAM_KEYS = ("time_limit_s", "seed", "workers", "weights", "solver", "merge_joint_lectures", "parent_run_id")
_SELECTOR_KEYS = ("event_ids", "cohort", "cohorts", "program", "programs", "match", "instructor", "instructors")


def _check_solver(params: dict[str, Any]) -> None:
    from app.services.run_params import SOLVERS

    if "solver" in params and params["solver"] not in SOLVERS:
        raise StudioError(422, f"params.solver must be one of {SOLVERS}")


class StudioError(Exception):
    """Client error with an HTTP status (mapped by the router)."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------------- drafts


async def get_term(session: AsyncSession, term_id: int) -> Term:
    term = await session.get(Term, term_id)
    if term is None:
        raise StudioError(404, "term not found")
    return term


async def get_draft(
    session: AsyncSession, term_id: int, user_id: int, kind: str = "COURSE", *, create: bool = True
) -> StudioDraft:
    """The caller's draft for (term, kind); created on first access."""
    if kind not in KINDS:
        raise StudioError(422, f"kind must be one of {KINDS}")
    await get_term(session, term_id)
    draft = (
        await session.execute(
            select(StudioDraft).where(
                StudioDraft.term_id == term_id, StudioDraft.user_id == user_id, StudioDraft.kind == kind
            )
        )
    ).scalar_one_or_none()
    if draft is None:
        if not create:
            raise StudioError(404, "no studio draft for this term")
        return await _create_draft(session, term_id, user_id, kind)
    return draft


async def _create_draft(session: AsyncSession, term_id: int, user_id: int, kind: str) -> StudioDraft:
    """Idempotent get-or-create: two first visits racing on the unique (term, user, kind) key both get the
    one draft (the loser's INSERT fails, it re-reads the winner's row) instead of a 500 (usability U2)."""
    from sqlalchemy.exc import IntegrityError

    try:
        draft = StudioDraft(
            term_id=term_id,
            user_id=user_id,
            kind=kind,
            version=1,
            horizon="TERM",
            horizon_params={},
            excluded_event_ids=[],
            pins=[],
            disabled_rule_ids=[],
            rule_overrides={},
            params={},
        )
        session.add(draft)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        draft = (
            await session.execute(
                select(StudioDraft).where(
                    StudioDraft.term_id == term_id, StudioDraft.user_id == user_id, StudioDraft.kind == kind
                )
            )
        ).scalar_one()
        return draft
    await session.refresh(draft)
    return draft


async def builtin_rows(session: AsyncSession, draft: StudioDraft) -> list[ConstraintRow]:
    rows = (
        await session.execute(
            select(ConstraintRow).where(ConstraintRow.term_id == draft.term_id, ConstraintRow.source == "BUILTIN")
        )
    ).scalars()
    return [r for r in rows if (r.source_ref or {}).get("draft_id") == draft.id and not r.enabled]


async def disabled_builtins(session: AsyncSession, draft: StudioDraft) -> list[str]:
    return sorted({r.kind for r in await builtin_rows(session, draft)})


async def term_rules(session: AsyncSession, term_id: int, *, enabled_only: bool = True) -> list[ConstraintRow]:
    """Term-wide rules (no BUILTIN switches)."""
    q = select(ConstraintRow).where(ConstraintRow.term_id == term_id, ConstraintRow.source != "BUILTIN")
    if enabled_only:
        q = q.where(ConstraintRow.enabled.is_(True))
    return list((await session.execute(q.order_by(ConstraintRow.id))).scalars())


async def rules_in_play(session: AsyncSession, draft: StudioDraft) -> list[int]:
    off = {int(i) for i in draft.disabled_rule_ids or []}
    return [r.id for r in await term_rules(session, draft.term_id) if r.id not in off]


def resolve_weeks(term: Term, horizon: str, horizon_params: dict[str, Any] | None) -> list[int]:
    run = ScheduleRun(term_id=term.id, horizon=horizon, horizon_params=dict(horizon_params or {}))
    return solver_bridge.horizon_weeks(run, term)


async def scope_weeks(session: AsyncSession, term: Term, draft: StudioDraft) -> list[int]:
    """Weeks in scope. An exam draft over the whole term uses the term's exam weeks (its week calendar),
    not the 14-week lecture default (usability U5)."""
    hp = dict(draft.horizon_params or {})
    if draft.kind == "EXAM" and draft.horizon == "TERM" and not hp.get("weeks"):
        rows = (await session.execute(select(Week.index, Week.kind).where(Week.term_id == term.id))).all()
        exam = sorted({int(i) for i, k in rows if k == "EXAM" and int(i) >= 1})
        if exam or rows:
            return exam or sorted({int(i) for i, _k in rows if int(i) >= 1})
    return resolve_weeks(term, draft.horizon, hp)


def exam_event_weeks(inp: sm.SolverInput) -> tuple[list[int], int]:
    """(weeks the exams of ``inp`` sit in, number of exams dated outside the term's weeks)."""
    weeks = sorted({w for e in inp.events for w in e.weeks if w >= 1})
    outside = sum(1 for e in inp.events if any(w < 1 for w in e.weeks))
    return weeks, outside


async def draft_out(session: AsyncSession, draft: StudioDraft) -> dict[str, Any]:
    term = await get_term(session, draft.term_id)
    weeks = await scope_weeks(session, term, draft)
    holidays = set(
        (await session.execute(select(Week.index).where(Week.term_id == term.id, Week.kind == "HOLIDAY"))).scalars()
    )
    return {
        "draft_id": draft.id,
        "term_id": draft.term_id,
        "user_id": draft.user_id,
        "kind": draft.kind,
        "version": draft.version,
        "etag": f'"{draft.version}"',
        "scope": {
            "horizon": draft.horizon,
            "horizon_params": dict(draft.horizon_params or {}),
            "weeks": weeks,
            "holiday_weeks": sorted(w for w in weeks if w in holidays),
        },
        "excluded_event_ids": [int(i) for i in draft.excluded_event_ids or []],
        "pins": list(draft.pins or []),
        "disabled_builtin_kinds": await disabled_builtins(session, draft),
        "disabled_rule_ids": [int(i) for i in draft.disabled_rule_ids or []],
        "rule_overrides": dict(draft.rule_overrides or {}),
        "rule_ids": await rules_in_play(session, draft),
        "preset_id": draft.preset_id,
        "last_step": draft.last_step,
        "params": dict(draft.params or {}),
        "updated_at": draft.updated_at,
    }


async def request_ids_in_term(session: AsyncSession, term_id: int, kind: str, ids: Iterable[int]) -> set[int]:
    wanted = {int(i) for i in ids}
    if not wanted:
        return set()
    if kind == "EXAM":
        q = select(ExamRequest.id).where(ExamRequest.term_id == term_id, ExamRequest.id.in_(wanted))
    else:
        q = (
            select(MeetingRequest.id)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term_id, MeetingRequest.id.in_(wanted))
        )
    return set((await session.execute(q)).scalars())


async def _validate_patch(
    session: AsyncSession, draft: StudioDraft, term: Term, body: Any, user: User
) -> dict[str, Any]:
    """Validated, normalised field values from a :class:`~app.schemas.studio.DraftIn` (only set fields)."""
    data = body.model_dump(exclude_unset=True)
    data.pop("version", None)
    data.pop("kind", None)
    out: dict[str, Any] = {}
    max_week = int(term.week_count or 14) + 4
    if "horizon" in data and data["horizon"] is not None:
        out["horizon"] = data["horizon"]
    if "horizon_params" in data and data["horizon_params"] is not None:
        hp = dict(data["horizon_params"])
        for key in ("weeks",):
            if key in hp:
                weeks = sorted({int(w) for w in hp[key] or []})
                if any(not 1 <= w <= max_week for w in weeks):
                    raise StudioError(422, f"weeks must be within 1..{max_week}")
                hp[key] = weeks
        for key in ("week", "start_week"):
            if key in hp and hp[key] is not None and not 1 <= int(hp[key]) <= max_week:
                raise StudioError(422, f"{key} must be within 1..{max_week}")
        out["horizon_params"] = hp
    if data.get("excluded_event_ids") is not None:
        ids = list(dict.fromkeys(int(i) for i in data["excluded_event_ids"]))
        found = await request_ids_in_term(session, term.id, draft.kind, ids)
        missing = [i for i in ids if i not in found]
        if missing:
            raise StudioError(422, f"class ids not in this term: {missing[:20]}")
        out["excluded_event_ids"] = ids
    if data.get("pins") is not None:
        pins = [p for p in data["pins"]]
        found = await request_ids_in_term(session, term.id, draft.kind, [p["event_id"] for p in pins])
        rooms = {p_room for p in pins for p_room in p.get("room_ids") or []}
        known_rooms = (
            set((await session.execute(select(Room.id).where(Room.id.in_(rooms)))).scalars()) if rooms else set()
        )
        clean: list[dict[str, Any]] = []
        for p in pins:
            if p["event_id"] not in found:
                raise StudioError(422, f"pinned class {p['event_id']} is not in this term")
            bad = [r for r in p.get("room_ids") or [] if r not in known_rooms]
            if bad:
                raise StudioError(422, f"unknown room id(s) {bad}")
            overrides = ("unlock", "required_tags", "size", "max_rooms")
            if (
                not p.get("room_ids")
                and p.get("day") is None
                and p.get("start_period") is None
                and not any(p.get(k) not in (None, False) for k in overrides)
            ):
                raise StudioError(422, f"pin of class {p['event_id']} needs rooms, a day/time or an override")
            if p.get("required_tags") is not None:
                p = {**p, "required_tags": sorted({str(t).upper() for t in p["required_tags"]})}
            clean.append(
                {k: v for k, v in p.items() if (k == "required_tags" and v is not None) or v not in (None, [], False)}
            )
        out["pins"] = clean
    if data.get("disabled_rule_ids") is not None:
        ids = sorted({int(i) for i in data["disabled_rule_ids"]})
        known = {r.id for r in await term_rules(session, term.id, enabled_only=False)}
        bad = [i for i in ids if i not in known]
        if bad:
            raise StudioError(422, f"rules not in this term: {bad}")
        out["disabled_rule_ids"] = ids
    if data.get("rule_overrides") is not None:
        from app.ai.catalog import KINDS as CATALOG

        rules = {r.id: r for r in await term_rules(session, term.id, enabled_only=False)}
        ov: dict[str, dict[str, Any]] = {}
        for key, val in data["rule_overrides"].items():
            try:
                cid = int(key)
            except ValueError as exc:
                raise StudioError(422, f"rule override key {key!r} is not a rule id") from exc
            if cid not in rules:
                raise StudioError(422, f"rule {cid} is not in this term")
            clean_ov = {k: v for k, v in (val or {}).items() if v is not None}
            spec = CATALOG.get(rules[cid].kind)
            if spec and clean_ov.get("hardness") and clean_ov["hardness"] not in spec.allowed_hardness:
                raise StudioError(422, f"rule {cid} ({rules[cid].kind}) cannot be {clean_ov['hardness']}")
            if clean_ov:
                ov[str(cid)] = clean_ov
        out["rule_overrides"] = ov
    if "disabled_builtin_kinds" in data and data["disabled_builtin_kinds"] is not None:
        kinds = sorted(set(data["disabled_builtin_kinds"]))
        bad = [k for k in kinds if not BUILTINS.get(k)]
        if bad:
            raise StudioError(
                422,
                f"built-in rule(s) {bad} cannot be switched off (switchable: {[k for k, v in BUILTINS.items() if v]})",
            )
        if kinds != await disabled_builtins(session, draft) and user.role != "ADMIN":
            raise StudioError(403, "only an ADMIN can switch built-in rules off")
        out["disabled_builtin_kinds"] = kinds
    if "preset_id" in data:
        if data["preset_id"] is not None and await session.get(StudioPreset, data["preset_id"]) is None:
            raise StudioError(422, "preset not found")
        out["preset_id"] = data["preset_id"]
    if "last_step" in data:
        out["last_step"] = data["last_step"]
    if data.get("params") is not None:
        params = {k: v for k, v in data["params"].items() if k in DRAFT_PARAM_KEYS or k in ("stability", "label")}
        if "time_limit_s" in params and not 1 <= float(params["time_limit_s"]) <= 3600:
            raise StudioError(422, "time_limit_s must be within 1..3600")
        _check_solver(params)
        out["params"] = params
    return out


async def set_disabled_builtins(session: AsyncSession, draft: StudioDraft, kinds: list[str], user_id: int) -> bool:
    rows = await builtin_rows(session, draft)
    have = {r.kind: r for r in rows}
    changed = False
    for kind, row in have.items():
        if kind not in kinds:
            await session.delete(row)
            changed = True
    for kind in kinds:
        if kind not in have:
            session.add(
                ConstraintRow(
                    term_id=draft.term_id,
                    kind=kind,
                    params={},
                    hardness="hard",
                    weight=1,
                    source="BUILTIN",
                    source_ref={"draft_id": draft.id},
                    nl_text=BUILTIN_TEXT.get(kind, {}).get("en"),
                    enabled=False,
                    created_by=user_id,
                )
            )
            changed = True
    return changed


async def update_draft(
    session: AsyncSession, draft: StudioDraft, body: Any, user: User, *, expected_version: int | None
) -> StudioDraft:
    """Apply a partial update with optimistic concurrency. The same body twice changes nothing (and keeps
    the version); a stale ``expected_version`` that would change something answers 409."""
    term = await get_term(session, draft.term_id)
    values = await _validate_patch(session, draft, term, body, user)
    builtins = values.pop("disabled_builtin_kinds", None)
    current = {k: getattr(draft, k) for k in values}
    changes = {k: v for k, v in values.items() if current.get(k) != v}
    builtin_change = builtins is not None and builtins != await disabled_builtins(session, draft)
    if not changes and not builtin_change:
        return draft
    if expected_version is None:
        raise StudioError(428, "version (or If-Match) is required")
    if expected_version != draft.version:
        raise StudioError(409, {"message": "the draft changed since you loaded it", "current": None})
    for k, v in changes.items():
        setattr(draft, k, v)
    if builtin_change:
        await set_disabled_builtins(session, draft, list(builtins or []), user.id)
    draft.version = int(draft.version) + 1
    draft.last_precheck = None
    await commit_draft(session, draft)
    await session.refresh(draft)
    return draft


async def commit_draft(session: AsyncSession, draft: StudioDraft) -> None:
    """Commit a draft change; a concurrent writer that won the race (the conditional ``UPDATE ... WHERE
    version = <loaded>`` matched no row) rolls this one back and answers 409 (review M1)."""
    from sqlalchemy.orm.exc import StaleDataError

    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise StudioError(409, {"message": "the draft changed since you loaded it", "current": None}) from exc


async def bump(session: AsyncSession, draft: StudioDraft) -> None:
    draft.version = int(draft.version) + 1
    draft.last_precheck = None
    draft.updated_at = datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------- draft-aware solver input


def draft_snapshot(draft: StudioDraft, builtins: list[str]) -> dict[str, Any]:
    """Everything a run needs to reproduce the draft (stored in ``schedule_runs.params["studio"]``)."""
    return {
        "draft_id": draft.id,
        "version": draft.version,
        "kind": draft.kind,
        "excluded_event_ids": [int(i) for i in draft.excluded_event_ids or []],
        "pins": list(draft.pins or []),
        "disabled_rule_ids": [int(i) for i in draft.disabled_rule_ids or []],
        "rule_overrides": dict(draft.rule_overrides or {}),
        "disabled_builtin_kinds": list(builtins),
    }


@dataclass
class DraftInput:
    inp: sm.SolverInput
    members: dict[int, list[int]]  # solver event id -> request ids (after exclusions)
    excluded: list[int]  # request ids left out
    dropped_event_ids: list[int] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)  # bridge stats (merged lectures, rooms without capacity)

    def head_of(self) -> dict[int, int]:
        return {rid: ev for ev, ids in self.members.items() for rid in ids}


def _transient_run(draft: StudioDraft) -> ScheduleRun:
    """A never-persisted run describing the draft (id -1 so no run-scoped rule matches)."""
    params = dict(draft.params or {})
    return ScheduleRun(
        id=-1,
        term_id=draft.term_id,
        kind=draft.kind,
        horizon=draft.horizon,
        horizon_params=dict(draft.horizon_params or {}),
        params=params,
        parent_run_id=params.get("parent_run_id") if params.get("stability", True) else None,
        stats={},
    )


async def _request_sizes(
    session: AsyncSession, kind: str, ids: Iterable[int], fallbacks: dict[str, Any] | None = None
) -> dict[int, int]:
    """Seats of each request: its enrolment, else the bridge's fallback size for a missing enrolment
    (``run.stats["enrolment_fallbacks"]``, review M1) - the same size the solver event was built with, so a
    draft that leaves part of a joint lecture out never clips the rest to 0 or to the members with a number."""
    wanted = list({int(i) for i in ids})
    if not wanted:
        return {}
    fb = {int(k): int((v or {}).get("size") or 0) for k, v in (fallbacks or {}).items()}
    if kind == "EXAM":
        rows = (
            await session.execute(select(ExamRequest.id, ExamRequest.enrolment).where(ExamRequest.id.in_(wanted)))
        ).all()
        return {i: int(n or 0) or fb.get(i, 0) for i, n in rows}
    q = (
        select(MeetingRequest.id, Section.enrolment, MeetingRequest.requested_capacity)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(MeetingRequest.id.in_(wanted))
    )
    return {i: int(e or c or 0) or fb.get(i, 0) for i, e, c in (await session.execute(q)).all()}


def _freeze_selectors(inp: sm.SolverInput, c: sm.Constraint, keys: tuple[str, ...]) -> sm.Constraint:
    """Replace selectors that depend on event keys about to be cleared by the explicit event ids they
    select today (``[-1]`` = matches nothing; an empty selector would mean *every* event)."""
    from app.solver.constraints._common import select_events

    if not any(k in c.params for k in keys):
        return c
    ids = sorted(e.id for e in select_events(inp, c.params))
    params = {k: v for k, v in c.params.items() if k not in _SELECTOR_KEYS}
    params["event_ids"] = ids or [-1]
    return replace(c, params=params)


def apply_draft(
    inp: sm.SolverInput,
    members: dict[int, list[int]],
    snap: dict[str, Any],
    sizes: dict[int, int] | None = None,
) -> tuple[sm.SolverInput, dict[int, list[int]], list[int]]:
    """Pure: the bridge's input edited by a draft snapshot (see module doc). Returns (input, members,
    dropped event ids)."""
    excluded = {int(i) for i in snap.get("excluded_event_ids") or []}
    sizes = sizes or {}
    events: list[sm.Event] = []
    new_members: dict[int, list[int]] = {}
    dropped: list[int] = []
    for e in inp.events:
        mem = list(members.get(e.id, [e.id]))
        keep = [m for m in mem if m not in excluded]
        if not keep:
            dropped.append(e.id)
            continue
        if len(keep) < len(mem):
            kept_seats = sum(sizes.get(m, 0) for m in keep)
            # clip only when every kept member has a size (an unknown one would under-count the group)
            if kept_seats and all(sizes.get(m, 0) > 0 for m in keep):
                e = replace(e, size=min(e.size, kept_seats))
        events.append(e)
        new_members[e.id] = keep
    head_of = {rid: ev for ev, ids in new_members.items() for rid in ids}
    by_id = {e.id: i for i, e in enumerate(events)}
    for pin in snap.get("pins") or []:
        idx = by_id.get(head_of.get(int(pin["event_id"]), -1))
        if idx is None:
            continue
        ev = events[idx]
        rooms = tuple(int(r) for r in pin.get("room_ids") or [])
        day = int(pin["day"]) if pin.get("day") is not None else None
        start = int(pin["start_period"]) if pin.get("start_period") is not None else None
        if pin.get("unlock") and ev.locked is not None and not rooms:
            # draft-only unlock (pre-check fix): the planner's room becomes a preference; the medicine-room
            # (TIP) ban comes back unless that room is itself a TIP room
            tip = {r.id for r in inp.rooms if "TIP" in r.tags}
            held = tuple(ev.locked.room_ids)
            ev = replace(
                ev,
                locked=None,
                preferred_room_ids=tuple(dict.fromkeys([*held, *ev.preferred_room_ids])),
                forbidden_tags=ev.forbidden_tags if set(held) & tip else ev.forbidden_tags | {"TIP"},
            )
        if pin.get("required_tags") is not None:
            ev = replace(ev, required_tags=frozenset(str(t) for t in pin["required_tags"]))
        if pin.get("size") is not None:
            ev = replace(ev, size=int(pin["size"]))
        if pin.get("max_rooms") is not None:
            ev = replace(ev, max_rooms=max(ev.min_rooms, int(pin["max_rooms"])))
        if rooms:
            ev = replace(ev, required_room_ids=frozenset(rooms), forbidden_tags=frozenset())
        if day is not None:
            ev = replace(ev, fixed_day=day, allowed_days=frozenset({day}))
        if start is not None:
            ev = replace(ev, fixed_start=start)
        if ev.locked is not None and (rooms or day is not None or start is not None):
            # the pin is the newer planner intent: it overrides the lock
            lk = ev.locked
            if (rooms and len(rooms) > 1) or pin.get("unlock"):
                ev = replace(ev, locked=None)
            else:
                s0 = start if start is not None else lk.start
                ev = replace(
                    ev,
                    locked=replace(
                        lk,
                        room_ids=rooms or lk.room_ids,
                        day=day if day is not None else lk.day,
                        start=s0,
                        end=s0 + (lk.end - lk.start),
                    ),
                )
        events[idx] = ev
    off = {int(i) for i in snap.get("disabled_rule_ids") or []}
    overrides = snap.get("rule_overrides") or {}
    constraints: list[sm.Constraint] = []
    for c in inp.constraints:
        if c.id is not None and c.id in off:
            continue
        ov = overrides.get(str(c.id)) if c.id is not None else None
        if ov:
            c = replace(
                c,
                hard=(ov["hardness"] == "hard") if ov.get("hardness") else c.hard,
                weight=int(ov.get("weight") or c.weight),
            )
        constraints.append(c)
    builtins = set(snap.get("disabled_builtin_kinds") or [])
    staged = replace(inp, events=tuple(events), constraints=tuple(constraints))
    if "no_instructor_overlap" in builtins:
        frozen = [_freeze_selectors(staged, c, ("instructor", "instructors")) for c in staged.constraints]
        events = [replace(e, instructor_keys=frozenset()) if e.instructor_keys else e for e in events]
        constraints = [*frozen, sm.Constraint("no_instructor_overlap", {"keys": [NO_KEY]}, True, 1, None)]
    if "no_cohort_overlap" in builtins:
        constraints.append(sm.Constraint("no_cohort_overlap", {"keys": [NO_KEY]}, True, 1, None))
    if "capacity" in builtins:
        constraints.append(sm.Constraint("capacity", {}, False, 1, None))
    kept = {e.id for e in events}
    out = replace(
        inp,
        events=tuple(events),
        constraints=tuple(constraints),
        previous=tuple(a for a in inp.previous if a.event_id in kept),
    )
    return out, new_members, dropped


async def build_draft_input(
    session: AsyncSession,
    draft: StudioDraft,
    *,
    run: ScheduleRun | None = None,
    snapshot: dict[str, Any] | None = None,
) -> DraftInput:
    run = run or _transient_run(draft)
    snap = snapshot or draft_snapshot(draft, await disabled_builtins(session, draft))
    return await _build_for(session, run, snap)


async def _build_for(session: AsyncSession, run: ScheduleRun, snap: dict[str, Any]) -> DraftInput:
    inp, members = await solver_bridge.build_solver_input(session, run)
    excluded = [int(i) for i in snap.get("excluded_event_ids") or []]
    touched = {m for ids in members.values() if len(ids) > 1 and set(ids) & set(excluded) for m in ids}
    sizes = await _request_sizes(session, run.kind, touched, (run.stats or {}).get("enrolment_fallbacks"))
    inp2, members2, dropped = apply_draft(inp, members, snap, sizes)
    return DraftInput(inp2, members2, excluded, dropped, dict(run.stats or {}))


async def build_solver_input_for_draft(session: AsyncSession, draft: StudioDraft) -> sm.SolverInput:
    """The ``SolverInput`` a run generated from ``draft`` right now would get."""
    return (await build_draft_input(session, draft)).inp


async def build_solver_input_for_run(
    session: AsyncSession, run: ScheduleRun
) -> tuple[sm.SolverInput, dict[int, list[int]]]:
    """Bridge input for ``run``, edited by ``run.params["studio"]`` when the run came from a draft."""
    from app.services.run_params import trusted_studio_snapshot

    snap = trusted_studio_snapshot(run)  # a forged (unsealed) snapshot is ignored (review B3)
    if not snap:
        return await solver_bridge.build_solver_input(session, run)
    out = await _build_for(session, run, snap)
    run.stats = {**(run.stats or {}), "studio_dropped_events": len(out.dropped_event_ids)}
    return out.inp, out.members


# --------------------------------------------------------------------------- generate


async def run_draft_schedule(session_factory: Any, run_id: int, progress: Any = None) -> dict[str, Any]:
    """Queue job body for studio runs: the bridge's job body, which honours the sealed draft snapshot
    (one code path for cancellation, the wall-clock limit and the session handling during the solve)."""
    return await solver_bridge.run_schedule(session_factory, run_id, progress)


def enqueue_studio_run(run_id: int) -> None:
    from app.core.db import get_session_factory

    factory = get_session_factory()

    async def body_fn(progress: Any) -> dict[str, Any]:
        return await run_draft_schedule(factory, run_id, progress)

    async def on_status(st: JobState) -> None:
        async with factory() as session:
            row = await session.get(ScheduleRun, run_id)
            if row is None:
                return
            if st.status == "FAILED":
                row.status = "FAILED"
                row.error = st.error
                row.finished_at = datetime.now(UTC).replace(tzinfo=None)
            row.stats = {**(row.stats or {}), "progress": st.progress, "phase": st.phase}
            await session.commit()

    get_queue().enqueue(f"run:{run_id}", body_fn, on_status=on_status)


def _n(n: int, lang: str) -> str:
    s = f"{n:,}"
    return s.replace(",", ".") if lang == "tr" else s


def week_span(weeks: list[int]) -> str:
    if not weeks:
        return "-"
    if weeks == list(range(weeks[0], weeks[-1] + 1)):
        return f"{weeks[0]}-{weeks[-1]}" if len(weeks) > 1 else str(weeks[0])
    return ",".join(str(w) for w in weeks)


async def generate(session: AsyncSession, draft: StudioDraft, body: Any, user: User) -> dict[str, Any]:
    term = await get_term(session, draft.term_id)
    builtins = await disabled_builtins(session, draft)
    snap = draft_snapshot(draft, builtins)
    dparams = dict(draft.params or {})
    params: dict[str, Any] = {
        "time_limit_s": await ss.get_value(session, "solver_default_time_limit"),
        "workers": await ss.get_value(session, "solver_workers"),
        **{k: v for k, v in dparams.items() if k in DRAFT_PARAM_KEYS and k != "parent_run_id"},
        **{k: v for k, v in (body.params or {}).items() if k in DRAFT_PARAM_KEYS and k != "parent_run_id"},
        "studio": snap,
    }
    _check_solver(params)  # also a draft saved before the stub was removed (audit M1)
    params = _sealed_params(params, term.id, draft.kind)
    parent_id = body.parent_run_id if body.parent_run_id is not None else dparams.get("parent_run_id")
    stability = body.stability if body.stability is not None else bool(dparams.get("stability", True))
    if parent_id is not None:
        parent = await session.get(ScheduleRun, int(parent_id))
        if parent is None or parent.term_id != term.id or parent.kind != draft.kind:
            raise StudioError(422, "parent_run_id must be a run of the same term and kind")
    from app.workers.run_jobs import check_user_limit

    await check_user_limit(session, user.id)  # review M13: at most N active runs per user (429)
    din = await build_draft_input(session, draft, snapshot=snap)
    rules = [c for c in din.inp.constraints if c.id is not None]
    weeks = exam_event_weeks(din.inp)[0] if draft.kind == "EXAM" else list(din.inp.weeks)
    prompt = (
        f"Studio draft #{draft.id} v{draft.version}: {len(din.inp.events)} events "
        f"({sum(len(v) for v in din.members.values())} classes), {len(snap['excluded_event_ids'])} left out, "
        f"{sum(1 for c in rules if c.hard)} must / {sum(1 for c in rules if not c.hard)} try rules, "
        f"weeks {week_span(weeks)}"
        + (f", built-ins off: {', '.join(builtins)}" if builtins else "")
        + (f", pins: {len(snap['pins'])}" if snap["pins"] else "")
    )
    run = ScheduleRun(
        term_id=term.id,
        kind=draft.kind,
        horizon=draft.horizon,
        horizon_params=dict(draft.horizon_params or {}),
        params=params,
        prompt_text=prompt,
        parent_run_id=int(parent_id) if parent_id is not None and stability else None,
        label=body.label or dparams.get("label") or f"Studio {term.code}",
        status="QUEUED",
        stats={"progress": 0, "phase": "queued", "worker": worker_id(), "studio_draft_id": draft.id},
        created_by=user.id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    enqueue_studio_run(run.id)
    return {
        "run_id": run.id,
        "status": "QUEUED",
        "draft_id": draft.id,
        "draft_version": draft.version,
        "events": len(din.inp.events),
        "excluded": len(snap["excluded_event_ids"]),
        "prompt_text": prompt,
    }


def _sealed_params(params: dict[str, Any], term_id: int, kind: str) -> dict[str, Any]:
    """Bounded run params + the server seal of the draft snapshot (review B3/M13)."""
    from app.services import run_params as rp

    snap = params.pop("studio")
    try:
        clean = rp.clamp_server_params(rp.clean_client_params(params))
    except rp.ParamError as exc:
        raise StudioError(422, str(exc)) from exc
    return rp.seal_studio({**clean, "studio": snap}, term_id, kind)


# --------------------------------------------------------------------------- estimate


def estimate_seconds(n_events: int, n_rooms: int, n_weeks: int, time_limit_s: float) -> dict[str, Any]:
    """Run-time heuristic from the solver benchmarks (README: ~16 s for 300 events, ~100 s for 1 300
    events on 60 rooms x 14 weeks): ``t = 16 * (events/300)^1.25 * sqrt(rooms/60)``, capped by the
    time limit (+ the infeasibility diagnosis budget for the upper bound)."""
    if n_events <= 0:
        return {"low": 0, "high": 1, "words": {"tr": "birkaç saniye", "en": "a few seconds"}}
    base = 16.0 * (n_events / 300.0) ** 1.25 * max(0.5, (max(n_rooms, 1) / 60.0)) ** 0.5
    base *= max(0.6, min(1.2, (max(n_weeks, 1) / 14.0) ** 0.25))
    low = max(1, int(round(min(base * 0.6, time_limit_s))))
    high = max(low + 1, int(round(min(base * 2.0, time_limit_s + min(time_limit_s * 0.5, 120)))))
    return {"low": low, "high": high, "words": estimate_words(low, high)}


def estimate_words(low: int, high: int) -> dict[str, str]:
    mid = (low + high) / 2
    if high < 60:
        return {"tr": "bir dakikadan az", "en": "under a minute"}
    minutes = max(1, int(round(mid / 60)))
    hi_m = max(minutes, int(round(high / 60)))
    tail_tr = f" (en fazla {hi_m})" if hi_m > minutes else ""
    tail_en = f" (at most {hi_m})" if hi_m > minutes else ""
    if minutes == 1:
        return {"tr": "yaklaşık 1 dakika" + tail_tr, "en": "about a minute" + tail_en}
    return {"tr": f"yaklaşık {minutes} dakika" + tail_tr, "en": f"about {minutes} minutes" + tail_en}


# --------------------------------------------------------------------------- summary


async def class_totals(session: AsyncSession, draft: StudioDraft) -> dict[str, int]:
    """Request counts for the kind: total, needing a room, schedulable (has a time)."""
    if draft.kind == "EXAM":
        rows = (
            await session.execute(
                select(ExamRequest.needs_room, ExamRequest.date, ExamRequest.start_period).where(
                    ExamRequest.term_id == draft.term_id, ExamRequest.archived.is_(False)
                )
            )
        ).all()
        return {
            "total": len(rows),
            "needs_room": sum(1 for nr, _, _ in rows if nr),
            "no_time": sum(1 for nr, d, sp in rows if nr and (d is None or sp is None)),
        }
    rows2 = (
        await session.execute(
            select(MeetingRequest.needs_room, MeetingRequest.start_period, MeetingRequest.end_period)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == draft.term_id, MeetingRequest.archived.is_(False))
        )
    ).all()
    return {
        "total": len(rows2),
        "needs_room": sum(1 for nr, _, _ in rows2 if nr),
        "no_time": sum(1 for nr, s, e in rows2 if nr and (s is None or e is None)),
    }


async def summary(session: AsyncSession, draft: StudioDraft) -> dict[str, Any]:
    """The "What will happen" panel."""
    term = await get_term(session, draft.term_id)
    din = await build_draft_input(session, draft)
    totals = await class_totals(session, draft)
    rules = [c for c in din.inp.constraints if c.id is not None]
    must = sum(1 for c in rules if c.hard)
    try_ = len(rules) - must
    classes_in = sum(len(v) for v in din.members.values())
    out_n = len(draft.excluded_event_ids or [])
    exam = draft.kind == "EXAM"
    outside = 0
    if exam:  # the weeks the exams actually sit in; dates before/after the term are reported, not "week -2"
        weeks, outside = exam_event_weeks(din.inp)
    else:
        weeks = list(din.inp.weeks)
    holidays = set(
        (await session.execute(select(Week.index).where(Week.term_id == term.id, Week.kind == "HOLIDAY"))).scalars()
    )
    params = dict(draft.params or {})
    time_limit = float(params.get("time_limit_s") or await ss.get_value(session, "solver_default_time_limit") or 60)
    est = estimate_seconds(len(din.inp.events), len(din.inp.rooms), len(weeks), time_limit)
    last_good = (
        await session.execute(
            select(ScheduleRun)
            .where(
                ScheduleRun.term_id == term.id,
                ScheduleRun.kind == draft.kind,
                ScheduleRun.status.in_(("FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL")),
            )
            .order_by(ScheduleRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    warnings: list[dict[str, Any]] = []
    if totals["no_time"]:
        warnings.append(
            {
                "code": "no_time",
                "count": totals["no_time"],
                "message": {
                    "tr": f"{_n(totals['no_time'], 'tr')} dersin günü/saati yok; plana alınamaz.",
                    "en": f"{_n(totals['no_time'], 'en')} classes have no day/time and cannot be planned.",
                },
            }
        )
    hol = sorted(w for w in weeks if w in holidays)
    if hol:
        warnings.append(
            {
                "code": "holidays",
                "count": len(hol),
                "message": {
                    "tr": f"{len(hol)} hafta tatil: {week_span(hol)}.",
                    "en": f"{len(hol)} of the weeks are holidays: {week_span(hol)}.",
                },
            }
        )
    dropped_rooms = int((din.stats or {}).get("rooms_without_capacity_count") or 0)
    if dropped_rooms:
        warnings.append(
            {
                "code": "rooms_without_capacity",
                "count": dropped_rooms,
                "message": {
                    "tr": f"{dropped_rooms} dersliğin kapasitesi girilmemiş; kullanılmayacak.",
                    "en": f"{dropped_rooms} rooms have no capacity and will not be used.",
                },
            }
        )
    if outside:
        warnings.append(
            {
                "code": "exams_outside_term",
                "count": outside,
                "message": {
                    "tr": f"{_n(outside, 'tr')} sınavın tarihi dönemin sınav haftalarının dışında.",
                    "en": f"{_n(outside, 'en')} exams are dated outside the term's exam weeks.",
                },
            }
        )
    builtins = await disabled_builtins(session, draft)
    pre = draft.last_precheck or {}
    readiness = pre.get("readiness") if pre.get("version") == draft.version else "unknown"
    nr, nw, ne = len(din.inp.rooms), len(weeks), classes_in
    sentence = {
        "tr": f"{nw} hafta boyunca {_n(nr, 'tr')} derslikte {_n(ne, 'tr')} ders planlıyorsunuz.",
        "en": f"You are planning {_n(ne, 'en')} classes in {_n(nr, 'en')} rooms for {nw} weeks.",
    }
    if exam:  # merged cohorts sit one exam: say sittings, with the request count in brackets
        nx = len(din.inp.events)
        sentence = {
            "tr": f"{nw} sınav haftasında {_n(nr, 'tr')} salonda {_n(nx, 'tr')} sınav ({_n(ne, 'tr')} talep) "
            "planlıyorsunuz.",
            "en": f"You are planning {_n(nx, 'en')} exams ({_n(ne, 'en')} requests) in {_n(nr, 'en')} rooms "
            f"over {nw} exam weeks.",
        }
    human = {
        "tr": (
            f"SmartSched {week_span(weeks)}. haftalar için {_n(ne, 'tr')} dersi {_n(nr, 'tr')} dersliğe "
            f"yerleştirecek. {must} kesin kurala uyacak, {try_} tercihi mümkün olduğunca gözetecek. "
            f"{len(draft.pins or [])} ders sabitlendi. {_n(out_n, 'tr')} ders plan dışında. "
            f"Tahmini süre: {est['words']['tr']}."
        ),
        "en": (
            f"SmartSched will place {_n(ne, 'en')} classes into {_n(nr, 'en')} rooms for weeks "
            f"{week_span(weeks)}. It must follow {must} rules and will try to follow {try_} preferences. "
            f"{len(draft.pins or [])} classes are pinned. {_n(out_n, 'en')} are left out. "
            f"Estimated time: {est['words']['en']}."
        ),
    }
    if exam:
        nx = len(din.inp.events)
        human = {
            "tr": (
                f"SmartSched {week_span(weeks)}. sınav haftalarında {_n(nx, 'tr')} sınavı ({_n(ne, 'tr')} talep) "
                f"{_n(nr, 'tr')} salona yerleştirecek. {must} kesin kurala uyacak, {try_} tercihi mümkün olduğunca "
                f"gözetecek. {_n(out_n, 'tr')} talep plan dışında. Tahmini süre: {est['words']['tr']}."
            ),
            "en": (
                f"SmartSched will place {_n(nx, 'en')} exams ({_n(ne, 'en')} requests) into {_n(nr, 'en')} rooms "
                f"in exam weeks {week_span(weeks)}. It must follow {must} rules and will try to follow {try_} "
                f"preferences. {_n(out_n, 'en')} requests are left out. Estimated time: {est['words']['en']}."
            ),
        }
    return {
        "draft_id": draft.id,
        "version": draft.version,
        "kind": draft.kind,
        "counts": {
            "classes_total": totals["total"],
            "classes_need_room": totals["needs_room"],
            "classes_in": classes_in,
            "classes_out": out_n,
            "classes_without_time": totals["no_time"],
            "events": len(din.inp.events),
            "rooms": nr,
            "weeks": nw,
            "pinned": len(draft.pins or []),
            "rules_must": must,
            "rules_try": try_,
            "builtins_off": len(builtins),
        },
        "weeks": weeks,
        "holiday_weeks": hol,
        "readiness": readiness,
        "estimate_s": est,
        "sentence": sentence,
        "human_summary": human,
        "warnings": warnings,
        "last_good_run": (
            {
                "id": last_good.id,
                "status": last_good.status,
                "soft_score": last_good.soft_score,
                "hard_score": last_good.hard_score,
                "finished_at": last_good.finished_at,
            }
            if last_good
            else None
        ),
        "disabled_builtin_kinds": builtins,
    }


async def load_meetings(session: AsyncSession, term_id: int) -> list[MeetingRequest]:
    from app.models import Program, SectionInstructor

    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == term_id, MeetingRequest.archived.is_(False))
        .options(
            selectinload(MeetingRequest.section).selectinload(Section.course),
            selectinload(MeetingRequest.section).selectinload(Section.program).selectinload(Program.faculty),
            selectinload(MeetingRequest.section)
            .selectinload(Section.instructors)
            .selectinload(SectionInstructor.instructor),
        )
        .order_by(MeetingRequest.id)
    )
    return list((await session.execute(q)).scalars())


__all__ = [
    "BUILTINS",
    "DraftInput",
    "StudioError",
    "apply_draft",
    "build_draft_input",
    "build_solver_input_for_draft",
    "build_solver_input_for_run",
    "draft_out",
    "estimate_seconds",
    "generate",
    "get_draft",
    "run_draft_schedule",
    "summary",
    "update_draft",
]
