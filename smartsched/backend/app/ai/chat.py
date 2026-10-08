"""Post-generation chat on a run: tool-use loop -> ProposedDiff -> (planner) apply -> child run.

Safety model (docs/ARCHITECTURE.md "AI layer", docs/RESEARCH.md §4.3):

* :func:`handle_chat` only ever *reads* (read tools query the database) and *records* edit tool calls
  into a :class:`~app.schemas.ai.ProposedDiff`; it never changes a run, a constraint or a section.
  The diff is stored on the assistant ``ChatMessage`` (``tool_calls``) together with token usage.
* :func:`apply_diff` (``POST /runs/{id}/chat/apply``) re-validates every operation server-side:
  ids must belong to the run / term, moves and swaps are checked with the solver's independent
  validator (:func:`app.solver.repair.validate`) and rejected if they add a hard violation,
  constraints go through the catalogue + id verification and are created with ``source=AI``.
  The result is always a *child run* (``parent_run_id``, ``prompt_text``): either a patched copy of
  the parent (moves / swaps / locks only) or a queued repair / re-solve with the stability objective.
* :func:`explain_run` renders diagnoses and the objective breakdown from structured data only; a
  model rendering is accepted only if every number it mentions appears in that data.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import catalog
from app.ai.client import AIClient, text_of, tool_uses
from app.ai.edits import apply_section_edits
from app.ai.elicit import accept_proposals, build_system
from app.ai.resolve import (
    TermContext,
    load_term_context,
    resolve_program,
    resolve_proposal,
    resolve_rooms,
    resolve_section_edit,
    section_label,
    split_program_and_years,
)
from app.importers.normalize import PERIODS, tr_casefold
from app.models import Assignment, ChatMessage, ConstraintRow, ExamRequest, MeetingRequest, Room, ScheduleRun, Section
from app.schemas.ai import (
    AddConstraintOp,
    ApplyOut,
    ChatOut,
    ExplainOut,
    LockOp,
    MoveOp,
    ProposedDiff,
    RemoveConstraintOp,
    SectionEditOp,
    SetWeightOp,
    SwapOp,
    UsageOut,
)
from app.services.grid import assignment_labels
from app.services.solver_bridge import persist_result
from app.solver import model as sm

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).parent / "prompts"
_CHAT_RULES = (PROMPTS / "chat.md").read_text(encoding="utf-8")
_EXPLAIN_RULES = (PROMPTS / "explain.md").read_text(encoding="utf-8")

MAX_TOOL_ROUNDS = 8
MAX_TOKENS = 16000
HISTORY_MESSAGES = 10
DAY_NAMES = {
    "tr": ["", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
    "en": ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


class ChatError(ValueError):
    """Bad request against the chat layer (unknown run, unknown diff, already applied ...)."""


# ---------------------------------------------------------------------------
# Run state (read-only view used by the tools)
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    run: ScheduleRun
    term: TermContext
    rows: list[Assignment]
    labels: dict[int, str]
    rooms_by_id: dict[int, Room]
    constraints: list[ConstraintRow]
    sizes: dict[int, int] = field(default_factory=dict)  # assignment id -> enrolment
    _evaluation: Any = None

    @property
    def rows_by_id(self) -> dict[int, Assignment]:
        return {a.id: a for a in self.rows}

    def room_code(self, rid: int) -> str:
        r = self.rooms_by_id.get(int(rid))
        return r.display_name if r is not None else f"#{rid}"

    def brief(self, a: Assignment, lang: str = "en") -> dict[str, Any]:
        return {
            "assignment_id": a.id,
            "label": self.labels.get(a.id, "?"),
            "day": a.day,
            "day_name": DAY_NAMES[lang][a.day] if 1 <= a.day <= 7 else str(a.day),
            "periods": f"P{a.start_period}-P{a.end_period}",
            "time": _times(a.start_period, a.end_period),
            "rooms": [self.room_code(r) for r in a.room_ids or []],
            "weeks": _weeks_text([int(w) for w in (a.weeks or ([a.week] if a.week else []))]),
            "size": self.sizes.get(a.id),
            "locked": bool(a.is_locked),
            "origin": a.origin,
        }


def _times(start: int, end: int) -> str:
    if 1 <= start <= len(PERIODS) and 1 <= end <= len(PERIODS):
        return f"{PERIODS[start - 1].start:%H:%M}-{PERIODS[end - 1].end:%H:%M}"
    return "?"


def _weeks_text(weeks: list[int]) -> str:
    if not weeks:
        return "all"
    ws = sorted(set(weeks))
    runs: list[str] = []
    start = prev = ws[0]
    for w in ws[1:] + [None]:  # type: ignore[list-item]
        if w is not None and w == prev + 1:
            prev = w
            continue
        runs.append(f"W{start}" if start == prev else f"W{start}-W{prev}")
        if w is not None:
            start = prev = w
    return ",".join(runs)


async def load_run_state(session: AsyncSession, run_id: int) -> RunState:
    run = await session.get(ScheduleRun, run_id)
    if run is None:
        raise ChatError(f"run {run_id} not found")
    term = await load_term_context(session, run.term_id)
    rows = list(
        (
            await session.execute(
                select(Assignment)
                .where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                .order_by(Assignment.day, Assignment.start_period, Assignment.id)
            )
        ).scalars()
    )
    labels = await assignment_labels(session, rows)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    constraints = list(
        (
            await session.execute(
                select(ConstraintRow)
                .where((ConstraintRow.term_id == run.term_id) | (ConstraintRow.run_id == run.id))
                .order_by(ConstraintRow.id)
            )
        ).scalars()
    )
    sizes: dict[int, int] = {}
    mr_ids = [a.meeting_request_id for a in rows if a.meeting_request_id]
    if mr_ids:
        res = await session.execute(
            select(MeetingRequest.id, Section.enrolment)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(MeetingRequest.id.in_(mr_ids))
        )
        enrol = {int(i): e for i, e in res.all()}
        sizes.update({a.id: int(enrol.get(a.meeting_request_id) or 0) for a in rows if a.meeting_request_id})
    ex_ids = [a.exam_request_id for a in rows if a.exam_request_id]
    if ex_ids:
        res = await session.execute(select(ExamRequest.id, ExamRequest.enrolment).where(ExamRequest.id.in_(ex_ids)))
        enrol = {int(i): e for i, e in res.all()}
        sizes.update({a.id: int(enrol.get(a.exam_request_id) or 0) for a in rows if a.exam_request_id})
    return RunState(run, term, rows, labels, rooms, constraints, sizes)


def run_prompt_block(state: RunState) -> str:
    """Deterministic run summary for the system prompt (cacheable per run)."""
    run = state.run
    stats = run.stats or {}
    lines = [
        f"Run #{run.id} ({run.kind}, horizon {run.horizon} {json.dumps(run.horizon_params or {}, sort_keys=True)}), "
        f"status {run.status}, hard score {run.hard_score}, soft score {run.soft_score}, "
        f"{len(state.rows)} placed meetings.",
        "Objective breakdown (penalty by term): "
        + json.dumps(stats.get("objective_breakdown") or {}, sort_keys=True, ensure_ascii=False),
    ]
    diags = list(run.diagnosis or [])[:8]
    if diags:
        lines.append("Diagnoses:")
        for d in diags:
            lines.append(f"- [{d.get('severity', '?')}] {str(d.get('message', ''))[:300]}")
    lines.append("Constraints (id kind hardness weight source enabled: text):")
    for c in state.constraints[:80]:
        text = (c.nl_text or json.dumps(c.params or {}, sort_keys=True, ensure_ascii=False))[:100]
        lines.append(f"- #{c.id} {c.kind} {c.hardness} w{c.weight} {c.source} {'on' if c.enabled else 'off'}: {text}")
    if len(state.constraints) > 80:
        lines.append(f"... {len(state.constraints) - 80} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return re.sub(r"[\s§\-_.]+", "", tr_casefold(s or ""))


def tool_find_assignments(state: RunState, inp: dict[str, Any], lang: str) -> dict[str, Any]:
    q = _norm(str(inp.get("query") or ""))
    day = int(inp.get("day") or 0)
    week = int(inp.get("week") or 0)
    limit = max(1, min(40, int(inp.get("limit") or 20)))
    room_ids: set[int] | None = None
    if inp.get("room_code"):
        ents = resolve_rooms(state.term, [str(inp["room_code"])])
        room_ids = {e.resolved_id for e in ents if e.resolved_id is not None}
        if not room_ids:
            return {"error": f"room '{inp['room_code']}' not found", "candidates": ents[0].candidates if ents else []}
    out = []
    for a in state.rows:
        if q and q not in _norm(state.labels.get(a.id, "")):
            continue
        if day and a.day != day:
            continue
        if week and a.weeks and week not in [int(w) for w in a.weeks]:
            continue
        if room_ids is not None and not room_ids & {int(r) for r in a.room_ids or []}:
            continue
        out.append(state.brief(a, lang))
    return {"count": len(out), "assignments": out[:limit], "truncated": len(out) > limit}


def tool_room_schedule(state: RunState, inp: dict[str, Any], lang: str) -> dict[str, Any]:
    ents = resolve_rooms(state.term, [str(inp.get("room_code") or "")])
    rid = ents[0].resolved_id if ents else None
    if rid is None:
        return {"error": f"room '{inp.get('room_code')}' not found", "candidates": ents[0].candidates if ents else []}
    day = int(inp.get("day") or 0)
    week = int(inp.get("week") or 0)
    busy: list[dict[str, Any]] = []
    used: set[int] = set()
    for a in state.rows:
        if a.day != day or rid not in {int(r) for r in a.room_ids or []}:
            continue
        if week and a.weeks and week not in [int(w) for w in a.weeks]:
            continue
        busy.append(state.brief(a, lang))
        used.update(range(a.start_period, a.end_period + 1))
    room = state.rooms_by_id.get(rid)
    return {
        "room": state.room_code(rid),
        "capacity": room.capacity if room else None,
        "exam_capacity": room.exam_capacity if room else None,
        "tags": list(room.tags or []) if room else [],
        "day": day,
        "week": week or "all",
        "busy": busy,
        "free_periods": [p for p in range(1, len(PERIODS) + 1) if p not in used],
        "note": "term blocks (pre-occupied slots) are checked again when the planner applies a diff",
    }


def tool_find_sections(state: RunState, inp: dict[str, Any], lang: str) -> dict[str, Any]:
    code = _norm(str(inp.get("course_code") or ""))
    prog_canon: str | None = None
    if inp.get("program_name"):
        name, _ = split_program_and_years(str(inp["program_name"]))
        ent = resolve_program(state.term, name)
        prog_canon = ent.resolved_label
        if prog_canon is None:
            return {"error": f"programme '{inp['program_name']}' not found", "candidates": ent.candidates}
    out = []
    for s in state.term.sections.values():
        if s.archived or (code and code not in _norm(s.course.code)):
            continue
        if prog_canon and (s.program is None or s.program.canonical_name != prog_canon):
            continue
        active = [m for m in s.meeting_requests if not m.archived]
        out.append(
            {
                "section_id": s.id,
                "label": section_label(state.term, s.id),
                "enrolment": s.enrolment,
                "mode": s.mode,
                "class_years": s.class_years or ([s.class_year] if s.class_year else []),
                "planned_for_room": any(m.needs_room for m in active),
                "meetings": [
                    {"day": m.day, "periods": f"P{m.start_period}-P{m.end_period}", "needs_room": m.needs_room}
                    for m in active
                ],
            }
        )
    return {"count": len(out), "sections": out[:30], "truncated": len(out) > 30}


async def _evaluation(session: AsyncSession, state: RunState) -> tuple[sm.SolverInput, dict[int, int], Any]:
    """(SolverInput, assignment id -> event id, Evaluation) of the run as it is - computed lazily once."""
    if state._evaluation is None:
        from app.solver.scoring import evaluate

        inp, members = await _run_input(session, state.run)
        event_of = _event_map(state.run, state.rows, members)
        current = _current_assignments(inp, state.rows, event_of)
        state._evaluation = (inp, event_of, evaluate(inp, list(current.values())))
        await session.rollback()  # build_solver_input may touch run.stats; this view is read-only
    return state._evaluation  # type: ignore[no-any-return]


async def assignment_facts(session: AsyncSession, state: RunState, aid: int, lang: str = "en") -> dict[str, Any]:
    """Structured reasons for one placement (the only source the explanation may use)."""
    a = state.rows_by_id.get(aid)
    if a is None:
        return {"error": f"assignment {aid} is not part of run #{state.run.id}; use find_assignments"}
    from app.solver.constraints._common import select_events

    inp, event_of, ev = await _evaluation(session, state)
    eid = event_of.get(a.id)
    event = next((e for e in inp.events if e.id == eid), None)
    rooms = [state.rooms_by_id[int(r)] for r in a.room_ids or [] if int(r) in state.rooms_by_id]
    size = state.sizes.get(a.id) or (event.size if event else 0)
    exam = state.run.kind == "EXAM"
    cap = sum((r.exam_capacity or r.capacity) if exam else r.capacity for r in rooms)
    facts: dict[str, Any] = {
        **state.brief(a, lang),
        "room_details": [
            {
                "room": r.display_name,
                "capacity": r.capacity,
                "exam_capacity": r.exam_capacity,
                "tags": list(r.tags or []),
            }
            for r in rooms
        ],
        "capacity_check": {"size": size, "seats": cap, "fits": cap >= size},
    }
    if event is not None:
        facts["requirements"] = {
            "required_tags": sorted(event.required_tags),
            "forbidden_tags": sorted(event.forbidden_tags),
            "preferred_rooms": [state.room_code(r) for r in event.preferred_room_ids],
            "preferred_building": event.preferred_building,
            "fixed_day": event.fixed_day,
            "fixed_start": event.fixed_start,
            "pinned": event.locked is not None,
            "cohorts": sorted(event.cohort_keys),
        }
        facts["constraints"] = [
            {"id": c.id, "kind": c.kind, "hard": c.hard, "weight": c.weight}
            for c in inp.constraints
            if c.params and any(e.id == eid for e in select_events(inp, c.params))
        ][:15]
        facts["violations"] = [
            {"kind": v.kind, "hard": v.hard, "penalty": v.penalty, "message": v.message[:300]}
            for v in ev.violations
            if eid in v.event_ids
        ][:10]
    else:
        facts["note"] = "the event is no longer part of the solver input (excluded or outside the horizon)"
    return facts


# ---------------------------------------------------------------------------
# Edit tools -> diff operations (recorded, never executed)
# ---------------------------------------------------------------------------


def _resolve_room_codes(state: RunState, codes: list[str]) -> tuple[list[int], list[str]]:
    ents = resolve_rooms(state.term, [str(c) for c in codes])
    ids = [e.resolved_id for e in ents if e.resolved_id is not None]
    errors = [
        f"room '{e.text}' not found"
        + (f" (did you mean {', '.join(c['label'] for c in e.candidates)}?)" if e.candidates else "")
        for e in ents
        if e.resolved_id is None
    ]
    return ids, errors


async def record_edit(
    session: AsyncSession, state: RunState, diff: ProposedDiff, name: str, inp: dict[str, Any], lang: str
) -> dict[str, Any]:
    """Turn one edit tool call into a diff operation; returns the tool result for the model."""
    rows = state.rows_by_id
    reason = str(inp.get("reason") or "")
    if name == "move_event":
        a = rows.get(int(inp["assignment_id"]))
        if a is None:
            return {"error": "unknown assignment_id for this run; call find_assignments first"}
        room_ids: list[int] | None = None
        if inp.get("room_codes"):
            room_ids, errors = _resolve_room_codes(state, inp["room_codes"])
            if errors:
                return {"error": "; ".join(errors)}
        day = int(inp.get("day") or 0) or a.day
        start = int(inp.get("start_period") or 0) or a.start_period
        end = int(inp.get("end_period") or 0) or (start + (a.end_period - a.start_period))
        if not (1 <= day <= 7 and 1 <= start <= end <= len(PERIODS)):
            return {"error": f"invalid time: day {day}, P{start}-P{end} (days 1..7, periods 1..{len(PERIODS)})"}
        weeks = [int(w) for w in inp.get("weeks") or []] or None
        from app.services.conflicts import check_room_conflicts

        rid_list = room_ids if room_ids is not None else [int(r) for r in a.room_ids or []]
        conflicts = await check_room_conflicts(
            session,
            term_id=state.run.term_id,
            room_ids=rid_list,
            day=day,
            start_period=start,
            end_period=end,
            weeks=weeks or [int(w) for w in (a.weeks or [])],
            exclude_assignment_id=a.id,
            run_id=state.run.id,
        )
        op = MoveOp(
            assignment_id=a.id,
            day=day if day != a.day else None,
            start_period=start if start != a.start_period else None,
            end_period=end if end != a.end_period else None,
            room_ids=room_ids,
            weeks=weeks,
            label=state.labels.get(a.id),
            reason=reason,
            before=state.brief(a, lang),
            after={
                "day": day,
                "periods": f"P{start}-P{end}",
                "time": _times(start, end),
                "rooms": [state.room_code(r) for r in rid_list],
                "weeks": _weeks_text(weeks or [int(w) for w in (a.weeks or [])]),
            },
            preview_conflicts=conflicts[:10],
        )
        diff.operations.append(op)
        return {
            "recorded": "move (proposal only; the solver validates it when the planner applies)",
            "after": op.after,
            "preview_conflicts": [
                f"{c.get('label') or c.get('kind')} in {state.room_code(c['room_id']) if c.get('room_id') else '?'} "
                f"P{c['start_period']}-P{c['end_period']}"
                for c in conflicts[:5]
            ],
        }
    if name == "swap_rooms":
        a, b = rows.get(int(inp["assignment_id_a"])), rows.get(int(inp["assignment_id_b"]))
        if a is None or b is None:
            return {"error": "unknown assignment id(s) for this run; call find_assignments first"}
        diff.operations.append(
            SwapOp(
                assignment_id_a=a.id,
                assignment_id_b=b.id,
                label=f"{state.labels.get(a.id)} <-> {state.labels.get(b.id)}",
                reason=reason,
            )
        )
        return {"recorded": "swap (proposal only)"}
    if name in ("lock_assignment", "unlock_assignment"):
        a = rows.get(int(inp["assignment_id"]))
        if a is None:
            return {"error": "unknown assignment_id for this run"}
        diff.operations.append(
            LockOp(
                op="lock" if name == "lock_assignment" else "unlock",
                assignment_id=a.id,
                label=state.labels.get(a.id),
                reason=reason,
            )
        )
        return {"recorded": name.replace("_assignment", "") + " (proposal only)"}
    if name == "add_constraint":
        p = resolve_proposal(state.term, inp)
        diff.operations.append(AddConstraintOp(constraint=p))
        return {
            "recorded": "add_constraint (proposal only)",
            "status": p.status,
            "resolved_params": p.params,
            "issues": p.issues,
            "unresolved": [
                {"type": e.type, "text": e.text, "candidates": e.candidates}
                for e in p.entities
                if e.resolved_id is None
            ],
        }
    if name in ("remove_constraint", "set_weight"):
        cid = int(inp["constraint_id"])
        row = next((c for c in state.constraints if c.id == cid), None)
        if row is None:
            return {"error": f"constraint #{cid} is not in the context list"}
        if name == "remove_constraint":
            diff.operations.append(RemoveConstraintOp(constraint_id=cid, label=row.nl_text or row.kind, reason=reason))
            return {"recorded": "remove_constraint (proposal only)"}
        weight = int(inp.get("weight") or 0) or None
        hardness = str(inp.get("hardness") or "") or None
        spec = catalog.KINDS.get(row.kind)
        if hardness and spec is not None and hardness not in spec.allowed_hardness:
            return {"error": f"{row.kind} cannot be {hardness}"}
        if weight is not None and not 1 <= weight <= 10:
            return {"error": "weight must be 1..10"}
        if weight is None and hardness is None:
            return {"error": "nothing to change"}
        diff.operations.append(
            SetWeightOp(
                constraint_id=cid, weight=weight, hardness=hardness, label=row.nl_text or row.kind, reason=reason
            )  # type: ignore[arg-type]
        )
        return {"recorded": "set_weight (proposal only)"}
    if name in ("include_sections", "exclude_sections", "set_section_field"):
        sop = {"include_sections": "include", "exclude_sections": "exclude", "set_section_field": "set_field"}[name]
        edit = resolve_section_edit(state.term, sop, {**inp, "nl_text": reason})
        diff.operations.append(SectionEditOp(edit=edit))
        return {
            "recorded": f"section {sop} (proposal only)",
            "sections": edit.labels,
            "status": edit.status,
            "issues": edit.issues,
        }
    if name == "re_solve":
        diff.re_solve = True
        diff.stability = bool(inp.get("stability", True))
        return {"recorded": "re_solve (runs only after the planner applies the diff)", "stability": diff.stability}
    return {"error": f"unknown tool {name}"}


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------


async def _history(session: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.run_id == run_id)
                .order_by(ChatMessage.id.desc())
                .limit(HISTORY_MESSAGES)
            )
        ).scalars()
    )[::-1]
    out: list[dict[str, Any]] = []
    for m in rows:
        if m.role not in ("user", "assistant") or not m.content:
            continue
        if out and out[-1]["role"] == m.role:
            out[-1]["content"] += "\n\n" + m.content
        else:
            out.append({"role": m.role, "content": m.content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    if out and out[-1]["role"] == "user":
        out.append({"role": "assistant", "content": "(no reply)"})
    return out


async def handle_chat(
    session: AsyncSession,
    run_id: int,
    message: str,
    lang: str = "tr",
    *,
    client: AIClient,
    user_id: int | None = None,
) -> ChatOut:
    """One planner message -> assistant reply + ProposedDiff. Nothing is applied."""
    state = await load_run_state(session, run_id)
    diff = ProposedDiff(id=uuid.uuid4().hex[:12], run_id=run_id)
    system = build_system(state.term, lang, intro=_CHAT_RULES)
    system.append({"type": "text", "text": "Current run:\n" + run_prompt_block(state)})
    messages: list[dict[str, Any]] = [*await _history(session, run_id), {"role": "user", "content": message}]
    trace: list[dict[str, Any]] = []
    explanations: list[dict[str, Any]] = []
    final_text = ""
    for _round in range(MAX_TOOL_ROUNDS):
        response = await client.complete(
            system=system, messages=messages, tools=catalog.CHAT_TOOLS, max_tokens=MAX_TOKENS, effort="medium"
        )
        final_text = text_of(response) or final_text
        calls = tool_uses(response)
        if not calls or response.stop_reason != "tool_use":
            if response.stop_reason == "max_tokens" and calls:
                diff.warnings.append("the assistant's last tool call was cut off and ignored")
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for call in calls:
            data = call.input if isinstance(call.input, dict) else {}
            issues = catalog.validate_tool_input(call.name, data)
            if issues:
                result: dict[str, Any] = {"error": "invalid input: " + "; ".join(issues[:5])}
            elif call.name in catalog.READ_TOOL_NAMES:
                if call.name == "find_assignments":
                    result = tool_find_assignments(state, data, lang)
                elif call.name == "room_schedule":
                    result = tool_room_schedule(state, data, lang)
                elif call.name == "find_sections":
                    result = tool_find_sections(state, data, lang)
                else:
                    result = await assignment_facts(session, state, int(data["assignment_id"]), lang)
                    if "error" not in result:
                        explanations.append(result)
            elif call.name in catalog.EDIT_TOOL_NAMES:
                result = await record_edit(session, state, diff, call.name, data, lang)
            else:
                result = {"error": f"unknown tool {call.name}"}
            trace.append({"type": "tool", "name": call.name, "input": data, "ok": "error" not in result})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:20000],
                    **({"is_error": True} if "error" in result else {}),
                }
            )
        messages.append({"role": "user", "content": results})
    else:
        diff.warnings.append("stopped after the maximum number of tool rounds")
    if not final_text:
        final_text = _diff_summary(diff, lang) or ("Tamam." if lang == "tr" else "Done.")
    diff.summary = _diff_summary(diff, lang)
    usage = client.usage.to_dict()
    session.add(ChatMessage(run_id=run_id, role="user", content=message, tool_calls=[]))
    reply = ChatMessage(
        run_id=run_id,
        role="assistant",
        content=final_text,
        tool_calls=[
            *trace,
            *([{"type": "diff", "diff": diff.model_dump(mode="json"), "applied": None}] if not diff.is_empty else []),
            usage,
        ],
    )
    session.add(reply)
    await session.commit()
    log.info("chat run=%s ops=%d re_solve=%s tools=%d", run_id, len(diff.operations), diff.re_solve, len(trace))
    return ChatOut(
        message_id=reply.id,
        assistant_message=final_text,
        proposed_diff=None if diff.is_empty else diff,
        explanations=explanations,
        usage=UsageOut(**client.usage.to_out()),
    )


def _diff_summary(diff: ProposedDiff, lang: str) -> str:
    counts: dict[str, int] = {}
    for op in diff.operations:
        counts[op.op] = counts.get(op.op, 0) + 1
    names = {
        "tr": {"move": "taşıma", "swap": "derslik değişimi", "lock": "kilit", "unlock": "kilit açma",
               "add_constraint": "yeni kural", "remove_constraint": "kural kaldırma", "set_weight": "ağırlık",
               "section_edit": "şube düzenleme"},
        "en": {"move": "move", "swap": "swap", "lock": "lock", "unlock": "unlock", "add_constraint": "new rule",
               "remove_constraint": "rule removal", "set_weight": "weight change", "section_edit": "section edit"},
    }[lang if lang in ("tr", "en") else "en"]  # fmt: skip
    parts = [f"{n} {names.get(k, k)}" for k, n in counts.items()]
    if diff.re_solve:
        parts.append(
            ("yeniden çözüm" if lang == "tr" else "re-solve")
            + (" (kararlı)" if lang == "tr" and diff.stability else " (stable)" if diff.stability else "")
        )
    return " · ".join(parts)


async def chat_history(session: AsyncSession, run_id: int) -> list[ChatMessage]:
    return list(
        (
            await session.execute(select(ChatMessage).where(ChatMessage.run_id == run_id).order_by(ChatMessage.id))
        ).scalars()
    )


async def find_diff(session: AsyncSession, run_id: int, diff_id: str) -> tuple[ProposedDiff, ChatMessage, int]:
    for m in await chat_history(session, run_id):
        for i, tc in enumerate(m.tool_calls or []):
            if isinstance(tc, dict) and tc.get("type") == "diff" and (tc.get("diff") or {}).get("id") == diff_id:
                return ProposedDiff.model_validate(tc["diff"]), m, i
    raise ChatError(f"diff {diff_id} not found for run {run_id}")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


async def _run_input(session: AsyncSession, run: ScheduleRun) -> tuple[sm.SolverInput, dict[int, list[int]]]:
    """Solver input of ``run`` (or of a child copying its params): a studio run's draft (left-out classes,
    pins, rule switches) is honoured, exactly as for the run itself (review B2)."""
    from app.services.studio import build_solver_input_for_run

    return await build_solver_input_for_run(session, run)


def _event_map(run: ScheduleRun, rows: list[Assignment], members: dict[int, list[int]]) -> dict[int, int]:
    """Assignment row id -> solver event id (meeting request id; exam head id for merged exams)."""
    head_of = {m: head for head, ms in members.items() for m in ms}
    out: dict[int, int] = {}
    for a in rows:
        rid = a.exam_request_id if run.kind == "EXAM" else a.meeting_request_id
        if rid is not None:
            out[a.id] = head_of.get(rid, rid)
    return out


def _current_assignments(
    inp: sm.SolverInput, rows: list[Assignment], event_of: dict[int, int]
) -> dict[int, sm.Assignment]:
    events = {e.id: e for e in inp.events}
    out: dict[int, sm.Assignment] = {}
    for a in rows:
        eid = event_of.get(a.id)
        if eid is None or eid not in events or eid in out:
            continue
        weeks = frozenset(int(w) for w in (a.weeks or ([a.week] if a.week else []))) or events[eid].weeks
        out[eid] = sm.Assignment(
            eid, a.day, a.start_period, a.end_period, tuple(int(r) for r in a.room_ids or []), weeks, a.date
        )
    return out


def _hard_keys(
    inp: sm.SolverInput, assignments: dict[int, sm.Assignment]
) -> tuple[set[tuple[str, frozenset[int]]], list[Any]]:
    from app.solver.repair import validate

    viol = [v for v in validate(inp, list(assignments.values())) if v.hard]
    return {(v.kind, frozenset(v.event_ids)) for v in viol}, viol


@dataclass
class _Plan:
    applied: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    moved: dict[int, sm.Assignment] = field(default_factory=dict)  # event id -> edited assignment
    lock: set[int] = field(default_factory=set)  # event ids
    unlock: set[int] = field(default_factory=set)
    constraints_created: list[int] = field(default_factory=list)
    changed_constraints: list[ConstraintRow] = field(default_factory=list)
    data_changed: bool = False


async def apply_diff(
    session: AsyncSession,
    run_id: int,
    *,
    diff: ProposedDiff | None = None,
    diff_id: str | None = None,
    user_id: int | None = None,
    label: str | None = None,
    enqueue: bool = True,
) -> ApplyOut:
    """Validate and apply a reviewed diff; always produces a child run (or nothing when all ops fail)."""
    parent = await session.get(ScheduleRun, run_id)
    if parent is None:
        raise ChatError(f"run {run_id} not found")
    stored_msg: ChatMessage | None = None
    stored_idx = -1
    if diff_id:
        stored, stored_msg, stored_idx = await find_diff(session, run_id, diff_id)
        applied_to = (stored_msg.tool_calls or [])[stored_idx].get("applied")
        if applied_to:
            raise ChatError(f"diff {diff_id} was already applied (child run #{applied_to})")
        diff = diff or stored
        if diff.id != diff_id:
            raise ChatError("diff id mismatch")
    if diff is None:
        raise ChatError("nothing to apply: pass diff_id or diff")
    if diff.run_id != run_id:
        raise ChatError("the diff belongs to another run")
    if diff.is_empty:
        raise ChatError("the diff is empty")
    claim = await _claim(session, run_id, diff_id, user_id) if diff_id else None
    try:
        return await _apply_claimed(session, parent, diff, stored_msg, stored_idx, claim, user_id, label, enqueue)
    except BaseException:
        if claim is not None:
            await _release(session, claim)
        raise


async def _claim(session: AsyncSession, run_id: int, diff_id: str, user_id: int | None) -> int:
    """Atomic idempotency claim (review M2): the unique (run, diff) INSERT is committed before any work, so
    two concurrent applies of one diff cannot both create a child run; the loser gets "already applied"."""
    from sqlalchemy.exc import IntegrityError

    from app.models import ChatApplyClaim

    row = ChatApplyClaim(run_id=run_id, diff_id=diff_id[:64], user_id=user_id)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        other = (
            await session.execute(
                select(ChatApplyClaim.child_run_id).where(
                    ChatApplyClaim.run_id == run_id, ChatApplyClaim.diff_id == diff_id[:64]
                )
            )
        ).scalar_one_or_none()
        raise ChatError(f"diff {diff_id} was already applied (child run #{other or 'pending'})") from exc
    return int(row.id)


async def _release(session: AsyncSession, claim_id: int) -> None:
    """Undo a claim whose apply failed or rejected every operation (the planner may try again)."""
    from sqlalchemy import delete

    from app.models import ChatApplyClaim

    await session.rollback()
    await session.execute(delete(ChatApplyClaim).where(ChatApplyClaim.id == claim_id))
    await session.commit()


async def _apply_claimed(
    session: AsyncSession,
    parent: ScheduleRun,
    diff: ProposedDiff,
    stored_msg: ChatMessage | None,
    stored_idx: int,
    claim: int | None,
    user_id: int | None,
    label: str | None,
    enqueue: bool,
) -> ApplyOut:
    run_id = parent.id
    state = await load_run_state(session, run_id)
    prompt = await _prompt_for(session, run_id, stored_msg)
    child = ScheduleRun(
        term_id=parent.term_id,
        kind=parent.kind,
        horizon=parent.horizon,
        horizon_params=dict(parent.horizon_params or {}),
        params=dict(parent.params or {}),
        status="QUEUED",
        stats={"progress": 0, "phase": "applying chat edit", "edited_from": parent.id, "diff_id": diff.id},
        parent_run_id=parent.id,
        prompt_text=prompt,
        label=(label or f"Chat edit of #{parent.id}")[:255],
        created_by=user_id,
    )
    session.add(child)
    await session.flush()
    plan = _Plan()

    # 1. data ops first: they change the solver input the moves are validated against
    for i, op in enumerate(diff.operations):
        if isinstance(op, AddConstraintOp):
            created, rej = await accept_proposals(
                session, parent.term_id, [op.constraint], user_id=user_id, commit=False
            )
            if created:
                plan.constraints_created += created
                plan.data_changed = True
                plan.applied.append({"index": i, "op": op.op, "constraint_id": created[0]})
                row = await session.get(ConstraintRow, created[0])
                if row is not None:
                    plan.changed_constraints.append(row)
            else:
                plan.rejected.append({"index": i, "op": op.op, "reasons": rej[0]["issues"] if rej else ["invalid"]})
        elif isinstance(op, RemoveConstraintOp | SetWeightOp):
            row = next((c for c in state.constraints if c.id == op.constraint_id), None)
            if row is None:
                plan.rejected.append(
                    {"index": i, "op": op.op, "reasons": [f"constraint #{op.constraint_id} not found for this run"]}
                )
                continue
            if isinstance(op, RemoveConstraintOp):
                if not row.enabled:
                    plan.rejected.append({"index": i, "op": op.op, "reasons": ["constraint is already disabled"]})
                    continue
                row.enabled = False
            else:
                spec = catalog.KINDS.get(row.kind)
                if op.hardness and spec is not None and op.hardness not in spec.allowed_hardness:
                    plan.rejected.append({"index": i, "op": op.op, "reasons": [f"{row.kind} cannot be {op.hardness}"]})
                    continue
                if op.weight is not None and not 1 <= op.weight <= 10:
                    plan.rejected.append({"index": i, "op": op.op, "reasons": ["weight must be 1..10"]})
                    continue
                if op.hardness:
                    row.hardness = op.hardness
                if op.weight is not None:
                    row.weight = op.weight
            plan.changed_constraints.append(row)
            plan.data_changed = True
            plan.applied.append({"index": i, "op": op.op, "constraint_id": row.id})
        elif isinstance(op, SectionEditOp):
            ok, rej = await apply_section_edits(session, parent.term_id, [op.edit], commit=False)
            if ok:
                plan.data_changed = True
                plan.applied.append({"index": i, "op": op.op, **{k: v for k, v in ok[0].items() if k != "index"}})
            else:
                plan.rejected.append({"index": i, "op": op.op, "reasons": rej[0]["issues"] if rej else ["invalid"]})
    await session.flush()

    # 2. solver input of the child (term data + constraints as they are now, parent as `previous`)
    inp, members = await _run_input(session, child)  # keeps the draft of studio runs (B2)
    event_of = _event_map(parent, state.rows, members)
    current = _current_assignments(inp, state.rows, event_of)
    events = {e.id: e for e in inp.events}
    room_ids_ok = {r.id for r in inp.rooms}
    base_keys, _ = _hard_keys(inp, current)

    # 3. moves / swaps validated one by one with the independent validator
    for i, op in enumerate(diff.operations):
        if isinstance(op, MoveOp | SwapOp):
            trial = dict(current)
            reasons: list[str] = []
            touched: list[int] = []
            pairs = [(op.assignment_id, None)] if isinstance(op, MoveOp) else [(op.assignment_id_a, op.assignment_id_b)]
            for aid, other in pairs:
                eid = event_of.get(aid)
                if aid not in state.rows_by_id or eid is None:
                    reasons.append(f"assignment {aid} is not part of run #{run_id}")
                    continue
                if eid not in current:
                    reasons.append(
                        f"{state.labels.get(aid)} is no longer in the solver input (excluded / outside horizon)"
                    )
                    continue
                old = current[eid]
                if isinstance(op, MoveOp):
                    if op.weeks and frozenset(op.weeks) != old.weeks:
                        reasons.append("changing the weeks of a meeting needs a week-pattern edit of the request")
                    rooms = tuple(op.room_ids) if op.room_ids is not None else old.room_ids
                    day = op.day or old.day
                    start = op.start_period or old.start
                    end = op.end_period or (start + old.end - old.start)
                    if not (1 <= day <= 7 and 1 <= start <= end <= inp.periods_per_day):
                        reasons.append(f"invalid time: day {day} P{start}-P{end}")
                    bad = [r for r in rooms if r not in room_ids_ok]
                    if bad:
                        reasons.append(f"rooms not available to the solver: {[state.room_code(r) for r in bad]}")
                    if events[eid].needs_room and not rooms:
                        reasons.append("an event that needs a room cannot be left without one")
                    trial[eid] = replace(old, day=day, start=start, end=end, room_ids=rooms)
                    touched.append(eid)
                else:
                    oid = event_of.get(other or -1)
                    if other not in state.rows_by_id or oid is None or oid not in current:
                        reasons.append(f"assignment {other} is not part of run #{run_id}")
                        continue
                    trial[eid] = replace(old, room_ids=current[oid].room_ids)
                    trial[oid] = replace(current[oid], room_ids=old.room_ids)
                    touched += [eid, oid]
            if not reasons:
                keys, viol = _hard_keys(inp, trial)
                new = [v for v in viol if (v.kind, frozenset(v.event_ids)) not in base_keys]
                if new:
                    reasons += [f"{v.kind}: {v.message}" for v in new[:5]]
                    if any(v.kind == "fixed_time" for v in new):
                        reasons.append(
                            "the meeting's requested day/time is fixed; change it with set_section_field "
                            "(section edit) or relax the fixed_time rule"
                        )
            if reasons:
                plan.rejected.append({"index": i, "op": op.op, "reasons": reasons})
                continue
            current = trial
            base_keys = keys
            for eid in touched:
                plan.moved[eid] = current[eid]
            plan.applied.append({"index": i, "op": op.op, "event_ids": touched})
        elif isinstance(op, LockOp):
            eid = event_of.get(op.assignment_id)
            if op.assignment_id not in state.rows_by_id or eid is None:
                plan.rejected.append(
                    {
                        "index": i,
                        "op": op.op,
                        "reasons": [f"assignment {op.assignment_id} is not part of run #{run_id}"],
                    }
                )
                continue
            (plan.lock if op.op == "lock" else plan.unlock).add(eid)
            (plan.unlock if op.op == "lock" else plan.lock).discard(eid)
            plan.applied.append({"index": i, "op": op.op, "event_ids": [eid]})

    if not plan.applied:
        await session.rollback()
        if claim is not None:
            await _release(session, claim)
        return ApplyOut(child_run_id=None, rejected=plan.rejected, mode="none", status="REJECTED")

    locked_rows = {event_of[a.id] for a in state.rows if a.is_locked and a.id in event_of}
    locks = (locked_rows | plan.lock) - plan.unlock
    unassigned = [e.id for e in inp.events if e.id not in current]
    needs_solve = diff.re_solve or plan.data_changed or bool(unassigned)
    out = ApplyOut(
        child_run_id=child.id,
        applied=plan.applied,
        rejected=plan.rejected,
        constraints_created=plan.constraints_created,
    )
    if not needs_solve:
        await _write_patch(session, child, parent, state, event_of, current, plan, locks, inp)
        out.mode, out.status = "patch", child.status
        out.hard_score, out.soft_score = child.hard_score, child.soft_score
    else:
        from app.solver.constraints._common import select_events

        if diff.re_solve and not diff.stability:
            changed = set(events)
            out.mode = "full"
        else:
            _, viol = _hard_keys(inp, current)
            changed = set(plan.moved) | set(unassigned) | {e for v in viol for e in v.event_ids}
            for c in plan.changed_constraints:
                if c.enabled and c.params:
                    changed |= {e.id for e in select_events(inp, c.params)}
            out.mode = "repair"
        child.stats = {**(child.stats or {}), "phase": "queued", "mode": out.mode}
        out.status = "QUEUED"
        out.re_solve_queued = True
    if stored_msg is not None:
        calls = list(stored_msg.tool_calls or [])
        calls[stored_idx] = {**calls[stored_idx], "applied": child.id}
        stored_msg.tool_calls = calls
    if claim is not None:
        from app.models import ChatApplyClaim

        claim_row = await session.get(ChatApplyClaim, claim)
        if claim_row is not None:
            claim_row.child_run_id = child.id
    await session.commit()
    if needs_solve:
        job = _solve_job(child.id, current, plan.moved, locks, changed, parent)
        if enqueue:
            _enqueue(child.id, job)
        else:
            await job(lambda _phase, _pct: None)
            await session.refresh(child)
            out.status, out.hard_score, out.soft_score = child.status, child.hard_score, child.soft_score
    log.info(
        "apply run=%s child=%s mode=%s applied=%d rejected=%d",
        run_id,
        child.id,
        out.mode,
        len(plan.applied),
        len(plan.rejected),
    )
    return out


async def _prompt_for(session: AsyncSession, run_id: int, msg: ChatMessage | None) -> str | None:
    if msg is None:
        return None
    prev = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.run_id == run_id, ChatMessage.id < msg.id, ChatMessage.role == "user")
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return prev.content if prev is not None else None


async def _write_patch(
    session: AsyncSession,
    child: ScheduleRun,
    parent: ScheduleRun,
    state: RunState,
    event_of: dict[int, int],
    current: dict[int, sm.Assignment],
    plan: _Plan,
    locks: set[int],
    inp: sm.SolverInput,
) -> None:
    """Child = copy of the parent's rows with the validated edits; scores from the validator."""
    from app.solver.repair import score, validate

    for a in state.rows:
        eid = event_of.get(a.id)
        edited = plan.moved.get(eid) if eid is not None else None
        session.add(
            Assignment(
                run_id=child.id,
                meeting_request_id=a.meeting_request_id,
                exam_request_id=a.exam_request_id,
                week=a.week,
                weeks=list(a.weeks or []),
                day=edited.day if edited else a.day,
                date=None if edited and edited.day != a.day else a.date,
                start_period=edited.start if edited else a.start_period,
                end_period=edited.end if edited else a.end_period,
                room_ids=list(edited.room_ids) if edited else list(a.room_ids or []),
                label=a.label,
                course_codes=list(a.course_codes or []),
                tags=list(a.tags or []),
                notes=a.notes,
                is_locked=eid in locks if eid is not None else a.is_locked,
                origin="AI_EDIT" if edited else a.origin,
            )
        )
    hard, soft, breakdown = score(inp, list(current.values()))
    hard_viol = [v for v in validate(inp, list(current.values())) if v.hard]
    child.status = "FEASIBLE" if hard == 100 else "INFEASIBLE"
    child.hard_score, child.soft_score = hard, soft
    child.objective_value = float(sum(breakdown.values())) if breakdown else 0.0
    child.stats = {
        **{k: v for k, v in (parent.stats or {}).items() if k in ("solver", "events", "rooms")},
        **(child.stats or {}),
        "objective_breakdown": breakdown,
        "assignments": len(state.rows),
        "progress": 100,
        "phase": "done",
        "mode": "patch",
        "edited_events": sorted(plan.moved),
    }
    child.diagnosis = [
        {
            "event_ids": v.event_ids,
            "constraint_kinds": [v.kind],
            "message": v.message,
            "suggestions": [],
            "severity": "error",
        }
        for v in hard_viol[:50]
    ]
    child.started_at = child.finished_at = datetime.now(UTC).replace(tzinfo=None)


def _solve_job(
    child_id: int,
    current: dict[int, sm.Assignment],
    moved: dict[int, sm.Assignment],
    locks: set[int],
    changed: set[int],
    parent: ScheduleRun,
) -> Any:
    from app.core.db import get_session_factory

    time_limit = float((parent.params or {}).get("time_limit_s", 60.0))

    async def job(progress: Any) -> dict[str, Any]:
        from app.solver.repair import repair
        from app.workers import run_jobs

        factory = get_session_factory()
        async with factory() as s:
            run = await s.get(ScheduleRun, child_id)
            assert run is not None
            if not await run_jobs.start_run(s, run):
                return await run_jobs.finish_cancelled(factory, child_id)
            await s.commit()
            progress("building", 10)
            inp, members = await _run_input(s, run)  # keeps the draft of studio runs (B2)
            await s.commit()  # no transaction stays open during the solve (review M7)
        ids = {e.id for e in inp.events}
        evs = []
        for e in inp.events:
            if e.id in moved:
                evs.append(replace(e, locked=moved[e.id]))
            elif e.id in locks and e.id in current:
                evs.append(replace(e, locked=current[e.id]))
            else:
                evs.append(e)
        inp = replace(inp, events=tuple(evs))
        cur = [a for eid, a in current.items() if eid in ids]
        full = changed >= ids
        limit = time_limit if full else min(time_limit, 30.0)
        progress("solving", 30)
        try:
            result = await run_jobs.solve_off_loop(
                child_id,
                limit,
                repair,
                inp,
                cur,
                sorted(changed & ids),
                limit,
                keep_changed=False,
                radius=0 if full else 1,
            )
        except run_jobs.RunCancelled:
            return await run_jobs.finish_cancelled(factory, child_id)
        progress("persisting", 90)
        async with factory() as s:
            run = await s.get(ScheduleRun, child_id)
            assert run is not None
            result.stats = {**result.stats, "solver": "app.solver.repair", "mode": "full" if full else "repair"}
            await persist_result(s, run, result, members)
            rows = list((await s.execute(select(Assignment).where(Assignment.run_id == child_id))).scalars())
            for a in rows:
                rid = a.exam_request_id if run.kind == "EXAM" else a.meeting_request_id
                head = next((h for h, ms in members.items() if rid in ms), rid)
                if head in moved:
                    a.origin = "AI_EDIT"
                if head in locks:
                    a.is_locked = True
            await s.commit()
            return {"status": result.status, "assignments": len(rows)}

    return job


def _enqueue(child_id: int, job: Any) -> None:
    from app.core.db import get_session_factory
    from app.workers.queue import JobState, get_queue

    async def on_status(st: JobState) -> None:
        async with get_session_factory()() as s:
            row = await s.get(ScheduleRun, child_id)
            if row is None:
                return
            if st.status == "FAILED":
                row.status = "FAILED"
                row.error = (st.error or "")[:4000]
                row.finished_at = datetime.now(UTC).replace(tzinfo=None)
            row.stats = {**(row.stats or {}), "progress": st.progress, "phase": st.phase}
            await s.commit()

    get_queue().enqueue(f"run:{child_id}", job, on_status=on_status)


# ---------------------------------------------------------------------------
# Explain a run (diagnoses + objective breakdown -> TR/EN prose)
# ---------------------------------------------------------------------------


class _ModelExplanation(BaseModel):
    headline: str
    paragraphs: list[str]
    suggestions: list[str]


EXPLAIN_FORMAT = {
    "type": "json_schema",
    "schema": catalog.strict_object(
        {
            "headline": {"type": "string"},
            "paragraphs": {"type": "array", "items": {"type": "string"}},
            "suggestions": {"type": "array", "items": {"type": "string"}},
        }
    ),
}

_TERM_NAMES = {
    "tr": {"capacity": "kapasite", "room_preference": "derslik tercihi", "building_preference": "bina tercihi",
           "min_capacity_waste": "boş koltuk", "stability": "değişiklik", "exam_gap": "sınav aralığı",
           "day_window": "gün penceresi", "room_tags": "derslik etiketi"},
    "en": {},
}  # fmt: skip


def run_facts(run: ScheduleRun) -> dict[str, Any]:
    stats = run.stats or {}
    return {
        "run_id": run.id,
        "parent_run_id": run.parent_run_id,
        "kind": run.kind,
        "status": run.status,
        "hard_score": run.hard_score,
        "soft_score": run.soft_score,
        "objective_breakdown": dict(sorted((stats.get("objective_breakdown") or {}).items(), key=lambda kv: -kv[1])),
        "events": stats.get("events"),
        "rooms": stats.get("rooms"),
        "assignments": stats.get("assignments"),
        "warnings": list(stats.get("warnings") or [])[:10],
        "diagnoses": [
            {
                "severity": d.get("severity"),
                "kinds": d.get("constraint_kinds"),
                "message": str(d.get("message", ""))[:400],
                "suggestions": list(d.get("suggestions") or [])[:4],
            }
            for d in list(run.diagnosis or [])[:10]
        ],
        "diagnoses_total": len(run.diagnosis or []),
        "prompt_text": run.prompt_text,
    }


def render_template(facts: dict[str, Any], lang: str) -> tuple[str, list[dict[str, Any]]]:
    tr = lang == "tr"
    status = facts["status"]
    ok = status in ("OPTIMAL", "FEASIBLE")
    if ok:
        hs, ss_ = facts["hard_score"], facts["soft_score"]
        head = (
            f"Çalıştırma #{facts['run_id']}: {status}, zorunlu kurallar {hs}/100, esnek puan {ss_}/100."
            if tr
            else f"Run #{facts['run_id']}: {status}, hard rules {hs}/100, soft score {ss_}/100."
        )
    else:
        head = (
            f"Çalıştırma #{facts['run_id']}: {status} - {facts['diagnoses_total']} sorun bulundu."
            if tr
            else f"Run #{facts['run_id']}: {status} - {facts['diagnoses_total']} problem(s) found."
        )
    sections: list[dict[str, Any]] = [{"title": "Özet" if tr else "Summary", "body": head}]
    breakdown = facts["objective_breakdown"]
    if breakdown:
        names = _TERM_NAMES.get(lang, {})
        items = [f"{names.get(k, k)}: {v}" for k, v in list(breakdown.items())[:6]]
        sections.append(
            {"title": "Ceza dağılımı" if tr else "Penalty breakdown", "body": "; ".join(items), "data": breakdown}
        )
    if facts["diagnoses"]:
        body = []
        for d in facts["diagnoses"]:
            line = d["message"]
            if d["suggestions"]:
                line += (" Öneri: " if tr else " Suggestion: ") + "; ".join(d["suggestions"][:2])
            body.append(line)
        sections.append(
            {"title": "Teşhis" if tr else "Diagnosis", "body": "\n".join(body), "items": facts["diagnoses"]}
        )
    if facts["warnings"]:
        sections.append({"title": "Uyarılar" if tr else "Warnings", "body": "; ".join(map(str, facts["warnings"]))})
    return "\n\n".join(s["body"] for s in sections), sections


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


async def explain_run(
    session: AsyncSession, run_id: int, lang: str = "tr", *, client: AIClient | None = None
) -> ExplainOut:
    """Structured run data -> TR/EN prose. Model prose is used only if every number in it is grounded."""
    run = await session.get(ScheduleRun, run_id)
    if run is None:
        raise ChatError(f"run {run_id} not found")
    facts = run_facts(run)
    text, sections = render_template(facts, lang)
    if client is None:
        return ExplainOut(text=text, sections=sections, source="template")
    data = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)
    message = await client.complete(
        system=_EXPLAIN_RULES.format(lang="Turkish" if lang == "tr" else "English"),
        messages=[{"role": "user", "content": f"<run_data>\n{data}\n</run_data>"}],
        max_tokens=4000,
        output_format=EXPLAIN_FORMAT,
        effort="low",
    )
    usage = UsageOut(**client.usage.to_out())
    try:
        parsed = _ModelExplanation.model_validate_json(text_of(message))
    except ValidationError:
        log.warning("explain: model output failed validation; using the template")
        return ExplainOut(text=text, sections=sections, source="template", usage=usage)
    prose = "\n\n".join([parsed.headline, *parsed.paragraphs])
    allowed = _numbers(data) | {"0", "100"}  # scores are reported out of 100
    ungrounded = _numbers(prose + " ".join(parsed.suggestions)) - allowed
    if ungrounded:
        log.warning("explain: %d ungrounded numbers in model prose; using the template", len(ungrounded))
        return ExplainOut(text=text, sections=sections, source="template", usage=usage)
    model_sections = [
        {"title": parsed.headline, "body": "\n\n".join(parsed.paragraphs)},
        *(
            [{"title": "Öneriler" if lang == "tr" else "Suggestions", "body": "\n".join(parsed.suggestions)}]
            if parsed.suggestions
            else []
        ),
        *[s for s in sections if "data" in s or "items" in s],
    ]
    return ExplainOut(text=prose, sections=model_sections, source="model", usage=usage)


__all__ = [
    "ChatError",
    "RunState",
    "apply_diff",
    "assignment_facts",
    "chat_history",
    "explain_run",
    "find_diff",
    "handle_chat",
    "load_run_state",
    "render_template",
    "run_facts",
]
