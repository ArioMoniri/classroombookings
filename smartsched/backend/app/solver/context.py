"""CP-SAT model context shared by the core builder and the constraint modules.

Variables (see README "Modelling"):

* ``y[e, t]``  Bool: event *e* takes time option *t* (omitted and treated as the constant *true*
  when the event has a single time option — i.e. almost every course meeting).
* ``x[e, t, r]`` Bool: event *e* takes time option *t* in room *r*.  Only (t, r) pairs that survive
  :mod:`app.solver.domains` exist.
* ``placed[e]`` Bool: only in ``assume`` / ``relax`` mode; the "event is scheduled at all" literal
  used as an assumption (core extraction) or as a slack (minimal-violation model).
* ``guard[name]`` Bool: only in ``assume`` mode; one assumption literal per actionable group of hard
  constraints ("room A204 double booking", "cohort PROG:X:Y1 overlap", constraint #17 ...).

Modes:

* ``solve``  — production model with objective.
* ``assume`` — satisfaction-only model with assumption literals (single worker).
* ``relax``  — slack model: minimise the number of unplaced events.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.domains import Domains, EventDomain, TimeOption, effective_capacity
from app.solver.model import Assignment, Constraint, Event, Room, SolverInput
from app.solver.weights import base_weight

Mode = Literal["solve", "assume", "relax"]
#: a CP-SAT Boolean literal, or the Python constant ``True`` for "always"
Lit = Any


class ModelContext:
    def __init__(self, inp: SolverInput, doms: Domains, mode: Mode = "solve") -> None:
        self.inp = inp
        self.doms = doms
        self.mode: Mode = mode
        self.model = cp_model.CpModel()
        self.rooms_by_id: dict[int, Room] = doms.rooms_by_id
        self.events_by_id: dict[int, Event] = doms.events_by_id
        self.x: dict[tuple[int, int, int], Any] = {}
        self.y: dict[tuple[int, int], Any] = {}
        self.placed: dict[int, Any] = {}
        self.guards: dict[str, Any] = {}
        self.guard_order: list[str] = []
        self.terms: dict[str, list[tuple[Any, int]]] = defaultdict(list)
        self._occ: dict[tuple[int, int, int], Lit] = {}
        self._room_use: dict[tuple[int, int], Lit] = {}
        self._on_day: dict[tuple[int, int], Lit] = {}
        self.warnings: list[str] = []
        self.n_bools = 0
        self._build_variables()

    # ------------------------------------------------------------------ variables
    def _new_bool(self, name: str) -> Any:
        self.n_bools += 1
        return self.model.NewBoolVar(name)

    def _build_variables(self) -> None:
        m = self.model
        for event in self.inp.events:
            dom = self.doms.domain(event.id)
            eid = event.id
            if self.mode != "solve":
                self.placed[eid] = self._new_bool(f"placed_{eid}")
            time_lits: list[Any] = []
            if dom.fixed_time:
                # constant time: the "time literal" is `placed` (or True in solve mode)
                lit = self.placed.get(eid, True)
                self.y[(eid, 0)] = lit
                time_lits = [] if lit is True else [lit]
            else:
                for ti in range(len(dom.times)):
                    v = self._new_bool(f"y_{eid}_{ti}")
                    self.y[(eid, ti)] = v
                    time_lits.append(v)
                if self.mode == "solve":
                    m.AddExactlyOne(time_lits)
                else:
                    m.Add(sum(time_lits) == self.placed[eid])
            if not event.needs_room:
                continue
            for ti, t in enumerate(dom.times):
                xs: list[Any] = []
                caps: list[int] = []
                for rid in dom.rooms:
                    if not dom.is_pair_allowed(t, rid):
                        continue
                    v = self._new_bool(f"x_{eid}_{ti}_{rid}")
                    self.x[(eid, ti, rid)] = v
                    xs.append(v)
                    caps.append(effective_capacity(self.rooms_by_id[rid], event))
                ylit = self.y[(eid, ti)]
                if not xs:
                    # time option without any room: cannot be chosen
                    if ylit is True:
                        # fixed-time event with no room at all -> model infeasible (static checker reports it)
                        m.AddBoolOr([])
                    else:
                        m.Add(ylit == 0)
                    continue
                if event.max_rooms <= 1:
                    if ylit is True:
                        m.AddExactlyOne(xs)
                    else:
                        m.Add(sum(xs) == ylit)
                else:
                    self._link_split(event, xs, caps, ylit)

    def _link_split(self, event: Event, xs: list[Any], caps: list[int], ylit: Lit) -> None:
        m = self.model
        lo = max(1, event.min_rooms)
        hi = max(lo, event.max_rooms)
        if ylit is True:
            m.Add(sum(xs) >= lo)
            m.Add(sum(xs) <= hi)
            m.Add(sum(c * v for c, v in zip(caps, xs, strict=True)) >= event.size)
        else:
            m.Add(sum(xs) >= lo).OnlyEnforceIf(ylit)
            m.Add(sum(xs) <= hi * ylit)
            m.Add(sum(c * v for c, v in zip(caps, xs, strict=True)) >= event.size).OnlyEnforceIf(ylit)

    # ------------------------------------------------------------------ literal accessors
    def domain(self, event_id: int) -> EventDomain:
        return self.doms.domain(event_id)

    def time_lit(self, event_id: int, ti: int) -> Lit:
        return self.y[(event_id, ti)]

    def room_lit(self, event_id: int, ti: int, room_id: int) -> Lit | None:
        return self.x.get((event_id, ti, room_id))

    def occupies(self, event_id: int, day: int, period: int) -> Lit | None:
        """Literal "event occupies (day, period)" or None when impossible; ``True`` when certain."""
        key = (event_id, day, period)
        if key in self._occ:
            return self._occ[key]
        dom = self.domain(event_id)
        lits = [self.y[(event_id, ti)] for ti, t in enumerate(dom.times) if t.covers(day, period)]
        res: Lit | None
        if not lits:
            res = None
        elif len(lits) == 1:
            res = lits[0]
        else:
            v = self._new_bool(f"occ_{event_id}_{day}_{period}")
            self.model.Add(sum(lits) == v)
            res = v
        self._occ[key] = res
        return res

    def on_day(self, event_id: int, day: int) -> Lit | None:
        key = (event_id, day)
        if key in self._on_day:
            return self._on_day[key]
        dom = self.domain(event_id)
        lits = [self.y[(event_id, ti)] for ti, t in enumerate(dom.times) if t.day == day]
        res: Lit | None
        if not lits:
            res = None
        elif len(lits) == 1:
            res = lits[0]
        else:
            v = self._new_bool(f"day_{event_id}_{day}")
            self.model.Add(sum(lits) == v)
            res = v
        self._on_day[key] = res
        return res

    def room_use(self, event_id: int, room_id: int) -> Lit | None:
        """Literal "event uses room r (at whatever time)"; None if the room is not an option."""
        key = (event_id, room_id)
        if key in self._room_use:
            return self._room_use[key]
        dom = self.domain(event_id)
        lits = [self.x[(event_id, ti, room_id)] for ti in range(len(dom.times)) if (event_id, ti, room_id) in self.x]
        res: Lit | None
        if not lits:
            res = None
        elif len(lits) == 1:
            res = lits[0]
        else:
            v = self._new_bool(f"use_{event_id}_{room_id}")
            self.model.Add(sum(lits) == v)
            res = v
        self._room_use[key] = res
        return res

    def room_lits_at(self, event_id: int, day: int, period: int, room_id: int) -> list[Any]:
        dom = self.domain(event_id)
        return [
            self.x[(event_id, ti, room_id)]
            for ti, t in enumerate(dom.times)
            if t.covers(day, period) and (event_id, ti, room_id) in self.x
        ]

    # ------------------------------------------------------------------ guards (assumptions)
    def guard(self, name: str) -> Lit | None:
        """Assumption literal for an actionable constraint group (``assume`` mode only)."""
        if self.mode != "assume":
            return None
        g = self.guards.get(name)
        if g is None:
            g = self._new_bool(f"g_{name}")
            self.guards[name] = g
            self.guard_order.append(name)
        return g

    # ------------------------------------------------------------------ hard-constraint helpers
    def add_at_most_one(self, lits: Sequence[Lit], guard: Lit | None) -> None:
        consts = sum(1 for lit in lits if lit is True)
        vars_ = [lit for lit in lits if lit is not True]
        m = self.model
        if consts >= 2:
            self.add_false(guard)
            return
        if consts == 1:
            for v in vars_:
                self.add_lit_false(v, guard)
            return
        if len(vars_) < 2:
            return
        if guard is None:
            m.AddAtMostOne(vars_)
        else:
            m.Add(sum(vars_) <= 1).OnlyEnforceIf(guard)

    def add_lit_false(self, lit: Lit, guard: Lit | None) -> None:
        if lit is True:
            self.add_false(guard)
            return
        if guard is None:
            self.model.Add(lit == 0)
        else:
            self.model.AddImplication(guard, lit.Not())

    def add_not_both(self, a: Lit, b: Lit, guard: Lit | None) -> None:
        if a is True and b is True:
            self.add_false(guard)
        elif a is True:
            self.add_lit_false(b, guard)
        elif b is True:
            self.add_lit_false(a, guard)
        elif guard is None:
            self.model.AddBoolOr([a.Not(), b.Not()])
        else:
            self.model.AddBoolOr([a.Not(), b.Not(), guard.Not()])

    def add_false(self, guard: Lit | None) -> None:
        """The model is infeasible (under the guard)."""
        if guard is None:
            self.model.AddBoolOr([])
        else:
            self.model.Add(guard == 0)

    def add_linear_le(self, expr: Any, rhs: int, guard: Lit | None) -> None:
        if guard is None:
            self.model.Add(expr <= rhs)
        else:
            self.model.Add(expr <= rhs).OnlyEnforceIf(guard)

    # ------------------------------------------------------------------ soft terms
    def weight_for(self, c: Constraint, name: str | None = None) -> int:
        return base_weight(self.inp.weights, name or c.kind) * max(0, c.weight)

    def add_penalty(self, name: str, expr: Lit, units: int, weight: int) -> None:
        """Add ``units * weight`` to the objective whenever ``expr`` (a literal / linear expr) is 1."""
        if units <= 0 or weight <= 0 or expr is None:
            return
        if expr is True:
            self.terms[name].append((1, units * weight))
            return
        self.terms[name].append((expr, units * weight))

    def new_bool(self, name: str) -> Any:
        return self._new_bool(name)

    def new_int(self, name: str, lo: int, hi: int) -> Any:
        return self.model.NewIntVar(lo, hi, name)

    def objective_expr(self) -> Any:
        parts: list[Any] = []
        for items in self.terms.values():
            for expr, coeff in items:
                parts.append(coeff * expr)
        return sum(parts) if parts else 0

    def term_values(self, solver: Any) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, items in self.terms.items():
            total = 0
            for expr, coeff in items:
                val = expr if isinstance(expr, int) else int(solver.Value(expr))
                total += coeff * val
            out[name] = total
        return out

    # ------------------------------------------------------------------ hints / fixing
    def _option_index(self, assignment: Assignment) -> int | None:
        dom = self.domain(assignment.event_id)
        return dom.time_index(assignment.day, assignment.start)

    def add_hints(self, assignments: Iterable[Assignment]) -> int:
        """Complete per-event hints from previous/locked assignments. Returns hinted event count."""
        hinted = 0
        for a in assignments:
            if a.event_id not in self.events_by_id:
                continue
            dom = self.domain(a.event_id)
            ti = self._option_index(a)
            if ti is None:
                continue
            rooms = set(a.room_ids)
            if dom.event.needs_room and any(self.x.get((a.event_id, ti, r)) is None for r in rooms):
                continue
            for i in range(len(dom.times)):
                lit = self.y[(a.event_id, i)]
                if lit is not True and lit is not self.placed.get(a.event_id):
                    self.model.AddHint(lit, 1 if i == ti else 0)
            for (eid, i, rid), v in self.x.items():
                if eid == a.event_id:
                    self.model.AddHint(v, 1 if (i == ti and rid in rooms) else 0)
            hinted += 1
        return hinted

    def fix_assignment(self, a: Assignment, guard: Lit | None) -> bool:
        """Force an event onto an assignment (used for locked events).  Returns False if impossible."""
        dom = self.domain(a.event_id)
        ti = self._option_index(a)
        if ti is None:
            self.add_false(guard)
            return False
        ylit = self.y[(a.event_id, ti)]
        if ylit is not True and guard is None:
            self.model.Add(ylit == 1)
        elif ylit is not True:
            self.model.AddImplication(guard, ylit)
        if not dom.event.needs_room:
            return True
        ok = True
        for rid in dom.rooms:
            v = self.x.get((a.event_id, ti, rid))
            if v is None:
                continue
            want = 1 if rid in a.room_ids else 0
            if guard is None:
                self.model.Add(v == want)
            else:
                self.model.AddImplication(guard, v if want else v.Not())
        for rid in a.room_ids:
            if self.x.get((a.event_id, ti, rid)) is None:
                ok = False
                self.add_false(guard)
        return ok

    # ------------------------------------------------------------------ extraction
    def extract(self, solver: Any) -> list[Assignment]:
        out: list[Assignment] = []
        for event in self.inp.events:
            dom = self.domain(event.id)
            if self.mode != "solve" and not solver.Value(self.placed[event.id]):
                continue
            chosen: TimeOption | None = None
            chosen_ti = 0
            for ti, t in enumerate(dom.times):
                lit = self.y[(event.id, ti)]
                if lit is True or solver.Value(lit):
                    chosen, chosen_ti = t, ti
                    break
            if chosen is None:
                continue
            rooms: list[int] = []
            if event.needs_room:
                for r in self.inp.rooms:
                    v = self.x.get((event.id, chosen_ti, r.id))
                    if v is not None and solver.Value(v):
                        rooms.append(r.id)
            out.append(
                Assignment(
                    event_id=event.id,
                    day=chosen.day,
                    start=chosen.start,
                    end=chosen.end,
                    room_ids=tuple(rooms),
                    weeks=event.weeks,
                    date=event.fixed_date,
                )
            )
        return out
