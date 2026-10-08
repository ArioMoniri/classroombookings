"""CP-SAT model context shared by the core builder and the constraint modules.

Variables (see README "Modelling"):

* ``y[e, t]``  Bool: event *e* takes time option *t*.  Omitted (constant ``True``) when the event
  has a single time option — i.e. almost every course meeting.  Flexible events also get an
  integer ``start[e]`` on the global period axis (``day_pos * periods_per_day + period - 1``)
  linked by ``start == Σ g_t · y[e,t]``.
* ``z[e, r]``  Bool: event *e* uses room *r* (only rooms that survive the domain pruning).
  Single-room events: ``ExactlyOne``; split exams: ``min ≤ Σ z ≤ max`` and ``Σ cap_r·z ≥ size``.
* Room occupancy is an optional interval per (event, room) — ``presence = z[e,r]`` — inside one
  ``NoOverlap`` per (room, week class); cohort/instructor occupancy is a fixed-size interval per
  event inside one ``NoOverlap`` per (key, week class).  No per-week copies, no ``x[e,t,r]``.
* ``placed[e]`` Bool: only in ``assume`` / ``relax`` mode; "event is scheduled at all", used as an
  assumption (core extraction) or as a slack (minimal-violation model).
* ``guard[name]`` Bool: only in ``assume`` mode; one assumption literal per actionable group of hard
  constraints.  Interval presences become ``base ∧ guard`` so a false guard switches the group off.

Modes: ``solve`` (objective), ``assume`` (satisfaction + assumptions, single worker), ``relax``
(minimise the number of unplaced events).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.constraints._common import week_runs
from app.solver.domains import Domains, EventDomain, TimeOption, effective_capacity, shares_room, trusted_lock
from app.solver.model import Assignment, Constraint, Event, Room, SolverInput
from app.solver.seats import proportional_allocation, seat_target
from app.solver.weights import base_weight

Mode = Literal["solve", "assume", "relax"]
#: a CP-SAT Boolean literal, or the Python constant ``True`` for "always"
Lit = Any


class HintView:
    """Assignments used to value every model variable when building a complete hint."""

    def __init__(self, assignments: Iterable[Assignment], doms: Domains) -> None:
        self.by_event = {a.event_id: a for a in assignments}
        self.doms = doms

    def time(self, event_id: int) -> TimeOption | None:
        a = self.by_event.get(event_id)
        return None if a is None else TimeOption(a.day, a.start, a.end - a.start + 1)

    def rooms(self, event_id: int) -> frozenset[int]:
        a = self.by_event.get(event_id)
        return frozenset() if a is None else frozenset(a.room_ids)


def _eval_placed(eid: int) -> Callable[[HintView], int]:
    return lambda h: int(eid in h.by_event)


def _eval_time(eid: int, topt: TimeOption) -> Callable[[HintView], int]:
    return lambda h: int(h.time(eid) == topt)


def _eval_room(eid: int, rid: int) -> Callable[[HintView], int]:
    return lambda h: int(rid in h.rooms(eid))


def _eval_seats(event: Event, rid: int, rooms_by_id: dict[int, Room]) -> Callable[[HintView], int]:
    def fn(h: HintView) -> int:
        rooms = h.rooms(event.id)
        return proportional_allocation(event, rooms, rooms_by_id).get(rid, 0) if rid in rooms else 0

    return fn


class ModelContext:
    def __init__(self, inp: SolverInput, doms: Domains, mode: Mode = "solve") -> None:
        self.inp = inp
        self.doms = doms
        self.mode: Mode = mode
        self.model = cp_model.CpModel()
        self.rooms_by_id: dict[int, Room] = doms.rooms_by_id
        self.events_by_id: dict[int, Event] = doms.events_by_id
        self.day_pos: dict[int, int] = {d: i for i, d in enumerate(inp.days)}
        self.y: dict[tuple[int, int], Lit] = {}
        self.z: dict[tuple[int, int], Any] = {}
        self.start: dict[int, Any] = {}  # flexible events: IntVar on the global period axis
        #: split room-sharing events: seats used in each room option (see app/solver/seats.py)
        self.seats: dict[tuple[int, int], Any] = {}
        self.placed: dict[int, Any] = {}
        self.guards: dict[str, Any] = {}
        self.guard_order: list[str] = []
        self.terms: dict[str, list[tuple[Any, int]]] = defaultdict(list)
        self._occ: dict[tuple[int, int, int], Lit | None] = {}
        self._on_day: dict[tuple[int, int], Lit | None] = {}
        self._room_interval: dict[tuple[int, int], Any] = {}
        self._event_interval: dict[int, Any] = {}
        self._and_cache: dict[tuple[int, int], Any] = {}
        self._week_interval: dict[tuple[int, int], Any] = {}
        #: derived variables with an evaluator over a hinted assignment set (complete hints)
        self._derived: list[tuple[Any, Callable[[HintView], int]]] = []
        self._lit_eval: dict[int, Callable[[HintView], int]] = {}
        self.warnings: list[str] = []
        #: ``relax`` mode: the minimised expression (re-used by the canonical tie-break stage)
        self.relax_objective: Any = None
        self.n_bools = 0
        self.n_intervals = 0
        self._build_variables()

    # ------------------------------------------------------------------ variables
    def _new_bool(self, name: str) -> Any:
        self.n_bools += 1
        return self.model.NewBoolVar(name)

    def global_start(self, t: TimeOption) -> int:
        return self.day_pos[t.day] * self.inp.periods_per_day + t.start - 1

    def _build_variables(self) -> None:
        m = self.model
        for event in self.inp.events:
            dom = self.doms.domain(event.id)
            eid = event.id
            if self.mode != "solve":
                self.placed[eid] = self._new_bool(f"placed_{eid}")
                self._lit_eval[self.placed[eid].Index()] = _eval_placed(eid)
            if dom.fixed_time:
                self.y[(eid, 0)] = self.placed.get(eid, True)
            elif dom.times:
                ys = []
                for ti, topt in enumerate(dom.times):
                    v = self._new_bool(f"y_{eid}_{ti}")
                    self.y[(eid, ti)] = v
                    ys.append(v)
                    self._lit_eval[v.Index()] = _eval_time(eid, topt)
                if self.mode == "solve":
                    m.AddExactlyOne(ys)
                else:
                    m.Add(sum(ys) == self.placed[eid])
                starts = sorted({self.global_start(t) for t in dom.times})
                sv = m.NewIntVarFromDomain(cp_model.Domain.FromValues(starts), f"start_{eid}")
                m.Add(
                    sv
                    == sum(self.global_start(t) * v for t, v in zip(dom.times, ys, strict=True))
                    + (0 if self.mode == "solve" else starts[0] * (1 - self.placed[eid]))
                )
                self.start[eid] = sv
            else:
                # no time option at all: the static checker reports it; keep the model consistent
                if self.mode == "solve":
                    m.AddBoolOr([])
                else:
                    m.Add(self.placed[eid] == 0)
                continue
            if not event.needs_room:
                continue
            zs: list[Any] = []
            caps: list[int] = []
            for rid in dom.rooms:
                if dom.fixed_time and not dom.is_pair_allowed(dom.times[0], rid):
                    continue
                v = self._new_bool(f"z_{eid}_{rid}")
                self.z[(eid, rid)] = v
                zs.append(v)
                self._lit_eval[v.Index()] = _eval_room(eid, rid)
                caps.append(effective_capacity(self.rooms_by_id[rid], event))
            placed = self.placed.get(eid, True)
            if not zs:
                if placed is True:
                    m.AddBoolOr([])
                else:
                    m.Add(placed == 0)
                continue
            if event.max_rooms <= 1:
                if placed is True:
                    m.AddExactlyOne(zs)
                else:
                    m.Add(sum(zs) == placed)
            else:
                self._link_split(event, zs, caps, placed)
                if shares_room(event):
                    self._link_seats(event, [r for r in dom.rooms if (eid, r) in self.z], placed)
            if not dom.fixed_time:
                # blocked (time, room) pairs of flexible events
                for ti, t in enumerate(dom.times):
                    for rid in dom.rooms:
                        if (eid, rid) in self.z and not dom.is_pair_allowed(t, rid):
                            m.AddBoolOr([self.y[(eid, ti)].Not(), self.z[(eid, rid)].Not()])

    def _link_split(self, event: Event, zs: list[Any], caps: list[int], placed: Lit) -> None:
        m = self.model
        lo = max(1, event.min_rooms)
        hi = max(lo, event.max_rooms)
        total = sum(c * v for c, v in zip(caps, zs, strict=True))
        # trust_locked_rooms: a planner-locked room set may seat fewer than ``size`` (warning, not a rule)
        need = 0 if trusted_lock(self.inp, event) else event.size
        if placed is True:
            m.Add(sum(zs) >= lo)
            m.Add(sum(zs) <= hi)
            if need:
                m.Add(total >= need)
        else:
            m.Add(sum(zs) >= lo).OnlyEnforceIf(placed)
            m.Add(sum(zs) <= hi * placed)
            if need:
                m.Add(total >= need).OnlyEnforceIf(placed)

    def _link_seats(self, event: Event, rooms: list[int], placed: Lit) -> None:
        """Split room-sharing event: ``seats[e,r]`` in ``[z, cap_r·z]`` with ``Σ_r seats = target``
        (``size``; for a locked room set ``min(size, Σ cap)``)."""
        m = self.model
        eid = event.id
        caps = {r: effective_capacity(self.rooms_by_id[r], event) for r in rooms}
        if trusted_lock(self.inp, event):
            assert event.locked is not None
            target = seat_target(event, event.locked.room_ids, self.rooms_by_id)
        else:
            target = event.size
        for r in rooms:
            z = self.z[(eid, r)]
            sv = m.NewIntVar(0, max(0, caps[r]), f"seats_{eid}_{r}")
            m.Add(sv <= caps[r] * z)
            if target >= max(1, event.max_rooms):
                # at least one seat per used room; a size-0 (or tiny) exam would otherwise have no room set at
                # all (orchestrator R2: size-0 Final exams stayed unplaced next to free rooms)
                m.Add(sv >= z)
            self.seats[(eid, r)] = sv
            self.derive(sv, _eval_seats(event, r, self.rooms_by_id))
        total = sum(self.seats[(eid, r)] for r in rooms)
        if placed is True:
            m.Add(total == target)
        else:
            m.Add(total == target * placed)

    def seat_demand(self, event_id: int, room_id: int) -> Any:
        """Seats ``event`` takes in ``room`` when it uses it (a constant for single-room events)."""
        sv = self.seats.get((event_id, room_id))
        if sv is not None:
            return sv
        event = self.events_by_id[event_id]
        return seat_target(event, (room_id,), self.rooms_by_id)

    # ------------------------------------------------------------------ literal accessors
    def domain(self, event_id: int) -> EventDomain:
        return self.doms.domain(event_id)

    def time_lit(self, event_id: int, ti: int) -> Lit:
        return self.y[(event_id, ti)]

    def room_use(self, event_id: int, room_id: int) -> Lit | None:
        """Literal "event uses room r"; None if the room is not an option."""
        return self.z.get((event_id, room_id))

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
            self.derive(v, lambda h: int((t := h.time(event_id)) is not None and t.covers(day, period)))
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
            self.derive(v, lambda h: int((t := h.time(event_id)) is not None and t.day == day))
            res = v
        self._on_day[key] = res
        return res

    def and_lit(self, a: Lit, b: Lit) -> Lit:
        """Literal for ``a ∧ b`` (constants folded)."""
        if a is True:
            return b
        if b is True:
            return a
        key = (a.Index(), b.Index()) if a.Index() <= b.Index() else (b.Index(), a.Index())
        v = self._and_cache.get(key)
        if v is None:
            v = self._new_bool(f"and_{key[0]}_{key[1]}")
            self.model.AddBoolAnd([a, b]).OnlyEnforceIf(v)
            self.model.AddBoolOr([a.Not(), b.Not(), v])
            self._and_cache[key] = v
            self.derive(v, lambda h: self.lit_value(a, h) & self.lit_value(b, h))
        return v

    # ------------------------------------------------------------------ complete hints
    def derive(self, var: Any, fn: Callable[[HintView], int]) -> None:
        """Register how to value ``var`` from a hinted assignment set."""
        self._derived.append((var, fn))
        self._lit_eval[var.Index()] = fn

    def lit_value(self, lit: Lit, h: HintView) -> int:
        """Value of a literal / registered variable under the hint (unknown -> 0)."""
        if lit is True:
            return 1
        idx = lit.Index()
        if idx < 0:  # negated literal
            fn = self._lit_eval.get(-idx - 1)
            return 0 if fn is None else 1 - fn(h)
        fn = self._lit_eval.get(idx)
        return 0 if fn is None else fn(h)

    # ------------------------------------------------------------------ intervals
    def _start_expr(self, event_id: int) -> Any:
        dom = self.domain(event_id)
        if dom.fixed_time:
            return self.global_start(dom.times[0])
        return self.start[event_id]

    def room_interval(self, event_id: int, room_id: int, guard: Lit | None) -> Any | None:
        """Optional interval "event occupies room r" (presence z ∧ guard)."""
        z = self.z.get((event_id, room_id))
        if z is None:
            return None
        presence = z if guard is None else self.and_lit(z, guard)
        key = (event_id, room_id)
        if guard is None and key in self._room_interval:
            return self._room_interval[key]
        dur = max(1, self.events_by_id[event_id].duration)
        iv = self.model.NewOptionalFixedSizeIntervalVar(
            self._start_expr(event_id), dur, presence, f"iv_{event_id}_{room_id}"
        )
        self.n_intervals += 1
        if guard is None:
            self._room_interval[key] = iv
        return iv

    def event_interval(self, event_id: int, guard: Lit | None) -> Any:
        """Interval "event takes place" (presence placed ∧ guard; always present in solve mode)."""
        base = self.placed.get(event_id, True)
        presence = base if guard is None else self.and_lit(base, guard)
        if presence is True and event_id in self._event_interval:
            return self._event_interval[event_id]
        dur = max(1, self.events_by_id[event_id].duration)
        if presence is True:
            iv = self.model.NewFixedSizeIntervalVar(self._start_expr(event_id), dur, f"ev_{event_id}")
            self._event_interval[event_id] = iv
        else:
            iv = self.model.NewOptionalFixedSizeIntervalVar(
                self._start_expr(event_id), dur, presence, f"ev_{event_id}_{self.n_intervals}"
            )
        self.n_intervals += 1
        return iv

    def fixed_interval(self, day: int, start: int, end: int, name: str) -> Any:
        g = self.day_pos[day] * self.inp.periods_per_day + start - 1
        self.n_intervals += 1
        return self.model.NewFixedSizeIntervalVar(g, end - start + 1, name)

    def add_no_overlap(self, intervals: Sequence[Any]) -> None:
        if len(intervals) >= 2:
            self.model.AddNoOverlap(intervals)

    def add_no_overlap_2d(self, items: Sequence[tuple[Any, frozenset[int]]]) -> None:
        """Boxes (time interval × contiguous week run); the same time interval is reused for
        every run of its week set."""
        if len(items) < 2:
            return
        xs: list[Any] = []
        ys: list[Any] = []
        for iv, weeks in items:
            for first, last in week_runs(weeks):
                key = (first, last)
                yiv = self._week_interval.get(key)
                if yiv is None:
                    yiv = self.model.NewFixedSizeIntervalVar(first, last - first + 1, f"weeks_{first}_{last}")
                    self._week_interval[key] = yiv
                xs.append(iv)
                ys.append(yiv)
        self.model.AddNoOverlap2D(xs, ys)

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
        """Add ``units * weight`` to the objective whenever ``expr`` (a literal / int expr) is 1."""
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
        return self.domain(assignment.event_id).time_index(assignment.day, assignment.start)

    def add_hints(self, assignments: Iterable[Assignment], *, unplaced_rest: bool = False) -> int:
        """Complete per-event hints from previous/locked assignments. Returns hinted event count.
        ``unplaced_rest`` (relax mode): every event without a hint is hinted as not placed, so the
        hint is a complete partial schedule."""
        hinted = 0
        assignments = list(assignments)
        if unplaced_rest and self.placed:
            have = {a.event_id for a in assignments}
            for e in self.inp.events:
                if e.id in have:
                    continue
                self.model.AddHint(self.placed[e.id], 0)
                for i in range(len(self.domain(e.id).times)):
                    lit = self.y.get((e.id, i))
                    if lit is not None and lit is not True and lit is not self.placed[e.id]:
                        self.model.AddHint(lit, 0)
                for rid in self.domain(e.id).rooms:
                    v = self.z.get((e.id, rid))
                    if v is not None:
                        self.model.AddHint(v, 0)
        for a in assignments:
            if a.event_id not in self.events_by_id:
                continue
            dom = self.domain(a.event_id)
            ti = self._option_index(a)
            if ti is None:
                continue
            rooms = set(a.room_ids)
            if dom.event.needs_room and any((a.event_id, r) not in self.z for r in rooms):
                continue
            for i in range(len(dom.times)):
                lit = self.y[(a.event_id, i)]
                if lit is not True and lit is not self.placed.get(a.event_id):
                    self.model.AddHint(lit, 1 if i == ti else 0)
            if a.event_id in self.start:
                self.model.AddHint(self.start[a.event_id], self.global_start(dom.times[ti]))
            for rid in dom.rooms:
                v = self.z.get((a.event_id, rid))
                if v is not None:
                    self.model.AddHint(v, 1 if rid in rooms else 0)
            if a.event_id in self.placed:
                self.model.AddHint(self.placed[a.event_id], 1)
            hinted += 1
        if hinted:
            view = HintView(assignments, self.doms)
            for var, fn in self._derived:
                self.model.AddHint(var, fn(view))
        return hinted

    def fix_assignment(self, a: Assignment, guard: Lit | None) -> bool:
        """Force an event onto an assignment (used for locked events).  Returns False if impossible.
        In ``relax`` mode the lock binds only if the event is placed (an impossible lock unplaces it)."""
        dom = self.domain(a.event_id)
        placed = self.placed.get(a.event_id) if self.mode == "relax" else None
        if placed is not None and guard is None:
            return self._fix_if_placed(a, placed)
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
            v = self.z.get((a.event_id, rid))
            if v is None:
                continue
            want = 1 if rid in a.room_ids else 0
            if guard is None:
                self.model.Add(v == want)
            else:
                self.model.AddImplication(guard, v if want else v.Not())
        for rid in a.room_ids:
            if (a.event_id, rid) not in self.z:
                ok = False
                self.add_false(guard)
        return ok

    def _fix_if_placed(self, a: Assignment, placed: Any) -> bool:
        m = self.model
        dom = self.domain(a.event_id)
        ti = self._option_index(a)
        if ti is None or (dom.event.needs_room and any((a.event_id, r) not in self.z for r in a.room_ids)):
            m.Add(placed == 0)
            return False
        ylit = self.y[(a.event_id, ti)]
        if ylit is not True and ylit is not placed:
            m.AddImplication(placed, ylit)
        if dom.event.needs_room:
            for rid in dom.rooms:
                v = self.z.get((a.event_id, rid))
                if v is None:
                    continue
                if rid in a.room_ids:
                    m.Add(v == placed)
                else:
                    m.Add(v == 0)
        return True

    # ------------------------------------------------------------------ extraction
    def extract(self, solver: Any) -> list[Assignment]:
        out: list[Assignment] = []
        for event in self.inp.events:
            dom = self.domain(event.id)
            if self.mode != "solve" and not solver.Value(self.placed[event.id]):
                continue
            chosen: TimeOption | None = None
            for ti, t in enumerate(dom.times):
                lit = self.y.get((event.id, ti))
                if lit is None:
                    continue
                if lit is True or solver.Value(lit):
                    chosen = t
                    break
            if chosen is None:
                continue
            rooms: list[int] = []
            if event.needs_room:
                for r in self.inp.rooms:
                    v = self.z.get((event.id, r.id))
                    if v is not None and solver.Value(v):
                        rooms.append(r.id)
            out.append(
                Assignment(event.id, chosen.day, chosen.start, chosen.end, tuple(rooms), event.weeks, event.fixed_date)
            )
        return out
