"""``evaluate(inp, assignments)``: run every constraint kind's ``score`` on a finished timetable."""

from __future__ import annotations

from app.solver.constraints import HANDLERS, effective_constraints
from app.solver.evaluate import Evaluation, index_assignments
from app.solver.model import Assignment, SolverInput


def evaluate(inp: SolverInput, assignments: list[Assignment] | tuple[Assignment, ...]) -> Evaluation:
    constraints, _warnings, _soft = effective_constraints(inp)
    rooms_by_id = {r.id: r for r in inp.rooms}
    events_by_id = {e.id: e for e in inp.events}
    ev = Evaluation(inp, index_assignments(assignments), rooms_by_id, events_by_id)
    seen: set[int] = set()
    for a in assignments:
        if a.event_id in seen:
            ev.hard("unassigned", [a.event_id], f"event #{a.event_id} has more than one assignment")
        seen.add(a.event_id)
        if a.event_id not in events_by_id:
            ev.hard("unassigned", [a.event_id], f"assignment refers to unknown event #{a.event_id}")
            continue
        event = events_by_id[a.event_id]
        for r in a.room_ids:
            if r not in rooms_by_id:
                ev.hard("unassigned", [a.event_id], f"{event.label} refers to unknown room #{r}", [r])
        if event.needs_room and not a.room_ids:
            ev.hard("unassigned", [a.event_id], f"{event.label} has no room")
        if not event.needs_room and a.room_ids:
            ev.hard("unassigned", [a.event_id], f"{event.label} does not need a room but occupies {list(a.room_ids)}", list(a.room_ids))
    for e in inp.events:
        if e.id not in ev.by_event:
            ev.hard("unassigned", [e.id], f"{e.label} is not scheduled")
    for c in constraints:
        HANDLERS[c.kind].score(ev, c)
    return ev


__all__ = ["evaluate"]
