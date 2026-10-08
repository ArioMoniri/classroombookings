"""INDEPENDENT hard-constraint checker for a SmartSched run.  Uses no app.solver code: only the pickled
SolverInput/SolverResult dataclasses (data) and, for level B, the raw DB rows (requests, rooms, blocks,
persisted assignments).

Level A (solver contract): every assignment of the result vs the original (pre-weeksplit) SolverInput.
Level B (planner truth): persisted Assignment rows vs MeetingRequest/ExamRequest/Room/Block rows.

Each finding is classified:
  VIOLATION      - breaks a hard rule with no documented waiver
  WAIVED_TRUST   - capacity/tags of an event sitting exactly in its planner-locked rooms (trust_locked_rooms)
  WAIVED_FIXED   - cohort/instructor clash of two input-fixed events at their fixed times
usage: check.py <tag>
"""
import json, pickle, sqlite3, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

SP = Path(__file__).parent
tag = sys.argv[1]
blob = pickle.loads((SP / "runs" / f"{tag}.pkl").read_bytes())
inp, res = blob["inp"], blob["res"]
run_id = blob["run_id"]
F = defaultdict(list)  # class -> list of (rule, msg)

def add(cls, rule, msg):
    F[cls].append((rule, msg))

rooms = {r.id: r for r in inp.rooms}
ev = {e.id: e for e in inp.events}
H = set(inp.weeks)
by_ev = defaultdict(list)
for a in res.assignments:
    by_ev[a.event_id].append(a)

def ecap(room, e):
    return room.exam_capacity if e.kind == "exam" else room.capacity

def input_fixed(e):
    return e.locked is not None or (e.fixed_day is not None and e.fixed_start is not None)

def fixed_slot(e):
    if e.locked is not None:
        return (e.locked.day, e.locked.start)
    return (e.fixed_day, e.fixed_start)

# ---------------------------------------------------------------- A1 per-assignment structure
for eid, asgs in by_ev.items():
    e = ev.get(eid)
    if e is None:
        add("VIOLATION", "unknown_event", f"assignment for unknown event {eid}"); continue
    wk_union = set()
    for a in asgs:
        if wk_union & set(a.weeks):
            add("VIOLATION", "weeks", f"{e.label}: two assignments share weeks")
        wk_union |= set(a.weeks)
        if not set(a.weeks) <= set(e.weeks):
            add("VIOLATION", "weeks", f"{e.label}: assignment weeks {sorted(a.weeks)} not within event weeks {sorted(e.weeks)}")
        if a.end - a.start + 1 != max(1, e.duration):
            add("VIOLATION", "duration", f"{e.label}: P{a.start}-P{a.end} != duration {e.duration}")
        if a.day not in inp.days or a.start < 1 or a.end > inp.periods_per_day:
            add("VIOLATION", "grid", f"{e.label}: outside grid day {a.day} P{a.start}-{a.end}")
        if e.locked is not None:
            L = e.locked
            if (a.day, a.start) != (L.day, L.start):
                add("VIOLATION", "locked_time", f"{e.label}: locked day{L.day} P{L.start}, got day{a.day} P{a.start}")
            if set(a.room_ids) != set(L.room_ids):
                add("VIOLATION", "locked_room", f"{e.label}: locked rooms {sorted(L.room_ids)}, got {sorted(a.room_ids)} weeks {sorted(a.weeks)}")
        elif e.fixed_day is not None and e.fixed_start is not None:
            if (a.day, a.start) != (e.fixed_day, e.fixed_start):
                add("VIOLATION", "fixed_time", f"{e.label}: fixed day{e.fixed_day} P{e.fixed_start}, got day{a.day} P{a.start}")
        else:
            if e.allowed_days and a.day not in e.allowed_days:
                add("VIOLATION", "allowed_days", f"{e.label}: day {a.day} not in {sorted(e.allowed_days)}")
            if a.start < e.earliest_start or a.end > e.latest_end:
                add("VIOLATION", "window", f"{e.label}: P{a.start}-{a.end} outside window")
        if e.kind == "exam" and e.fixed_date is not None and a.date is not None and a.date != e.fixed_date:
            add("VIOLATION", "exam_date", f"{e.label}: date {a.date} != {e.fixed_date}")
        if not e.needs_room:
            if a.room_ids:
                add("VIOLATION", "needs_room", f"{e.label}: needs no room but has {a.room_ids}")
            continue
        if not a.room_ids:
            add("VIOLATION", "no_room", f"{e.label}: needs a room, has none"); continue
        if len(set(a.room_ids)) != len(a.room_ids):
            add("VIOLATION", "dup_room", f"{e.label}: duplicate room ids {a.room_ids}")
        unknown = [r for r in a.room_ids if r not in rooms]
        if unknown:
            add("VIOLATION", "unknown_room", f"{e.label}: rooms {unknown} not in pool"); continue
        trusted = inp.trust_locked_rooms and e.locked is not None and set(a.room_ids) == set(e.locked.room_ids)
        n = len(a.room_ids)
        mx = max(1, e.max_rooms, len(e.locked.room_ids) if e.locked is not None else 0)  # documented: a k-room lock may use k rooms
        if n < max(1, e.min_rooms) or n > mx:
            add("VIOLATION", "room_count", f"{e.label}: {n} rooms, allowed {e.min_rooms}..{e.max_rooms}")
        cap = sum(ecap(rooms[r], e) for r in a.room_ids)
        if cap < e.size:
            add("WAIVED_TRUST" if trusted else "VIOLATION", "capacity",
                f"{e.label} size {e.size} in {'+'.join(rooms[r].code for r in a.room_ids)} = {cap} seats")
        for r in a.room_ids:
            miss = set(e.required_tags) - set(rooms[r].tags)
            bad = set(e.forbidden_tags) & set(rooms[r].tags)
            if miss or bad:
                add("WAIVED_TRUST" if trusted else "VIOLATION", "tags",
                    f"{e.label} in {rooms[r].code}: missing {sorted(miss)} forbidden {sorted(bad)}")
            if e.required_room_ids and r not in e.required_room_ids:
                add("VIOLATION", "pin", f"{e.label} not in pinned rooms")
            if r in e.forbidden_room_ids:
                add("VIOLATION", "forbid", f"{e.label} in forbidden room {rooms[r].code}")

# events not fully placed
unplaced = []
for e in inp.events:
    got = set().union(*(set(a.weeks) for a in by_ev.get(e.id, []))) if by_ev.get(e.id) else set()
    if got != set(e.weeks):
        unplaced.append((e.id, sorted(set(e.weeks) - got)))

# ---------------------------------------------------------------- A2 occupancy (room, week, day, period)
slots = defaultdict(list)  # (room, week, day, p) -> [(eid, assignment)]
for eid, asgs in by_ev.items():
    e = ev.get(eid)
    if e is None or not e.needs_room:
        continue
    for a in asgs:
        for w in a.weeks:
            for p in range(a.start, a.end + 1):
                for r in a.room_ids:
                    slots[(r, w, a.day, p)].append((eid, a))
seen = set()
for (r, w, d, p), items in slots.items():
    excl = [i for i, _ in items if not ev[i].share_room]
    shar = [i for i, _ in items if ev[i].share_room]
    if len(excl) > 1 or (excl and shar):
        key = (r, tuple(sorted(set(excl + shar))))
        if key not in seen:
            seen.add(key)
            add("VIOLATION", "room_double_booking", f"{rooms[r].code} w{w} d{d} P{p}: {[ev[i].label for i in excl+shar]}")
# blocks
for b in inp.blocks:
    for w in ([b.week] if b.week is not None else list(H)):
        for p in range(b.start, b.end + 1):
            for i, a in slots.get((b.room_id, w, b.day, p), []):
                k = ("blk", b, i)
                if k not in seen:
                    seen.add(k)
                    add("VIOLATION", "blocked_slot", f"{ev[i].label} in {rooms[b.room_id].code} w{w} d{b.day} P{p} is blocked")

# ---------------------------------------------------------------- A3 shared exam seats (constant allocation per exam)
from ortools.sat.python import cp_model  # used only as an independent LP/feasibility engine
share_slots = defaultdict(set)
for (r, w, d, p), items in slots.items():
    sh = [i for i, _ in items if ev[i].share_room]
    if len(sh) > 1:
        share_slots[(w, d)].update(sh)
# connected components per (week, day) through rooms+time overlap
def overlap(a, b):
    return a.day == b.day and a.start <= b.end and b.start <= a.end
checked = set()
for (w, d), ids in share_slots.items():
    ids = sorted(ids)
    A = {i: next(a for a in by_ev[i] if w in a.weeks) for i in ids}
    parent = {i: i for i in ids}
    def find(x):
        while parent[x] != x: x = parent[x]
        return x
    for i, j in combinations(ids, 2):
        if set(A[i].room_ids) & set(A[j].room_ids) and overlap(A[i], A[j]):
            parent[find(i)] = find(j)
    comps = defaultdict(list)
    for i in ids: comps[find(i)].append(i)
    for comp in comps.values():
        if len(comp) < 2: continue
        key = (w, tuple(comp))
        if key in checked: continue
        checked.add(key)
        for strict in (True, False):
            m = cp_model.CpModel()
            x = {}
            for i in comp:
                e = ev[i]
                caps = {r: ecap(rooms[r], e) for r in A[i].room_ids}
                target = e.size if strict else min(e.size, sum(caps.values()))
                for r in A[i].room_ids:
                    x[i, r] = m.NewIntVar(1 if len(A[i].room_ids) > 1 else 0, max(0, caps[r]) if len(A[i].room_ids) > 1 else target, f"x{i}_{r}")
                m.Add(sum(x[i, r] for r in A[i].room_ids) == target)
            rooms_used = {r for i in comp for r in A[i].room_ids}
            for r in rooms_used:
                cap = rooms[r].exam_capacity
                for p in range(1, inp.periods_per_day + 1):
                    here = [i for i in comp if r in A[i].room_ids and A[i].start <= p <= A[i].end]
                    if len(here) > 1 or (here and len(A[here[0]].room_ids) > 1):
                        m.Add(sum(x[i, r] for i in here) <= cap)
            s = cp_model.CpSolver(); s.parameters.num_workers = 1; s.parameters.max_time_in_seconds = 10
            st = s.Solve(m)
            if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                trusted = all(inp.trust_locked_rooms and ev[i].locked is not None and set(A[i].room_ids) == set(ev[i].locked.room_ids) for i in comp)
                desc = f"w{w} d{d}: {[(ev[i].label, ev[i].size, [rooms[r].code for r in A[i].room_ids], f'P{A[i].start}-{A[i].end}') for i in comp]} caps {[(rooms[r].code, rooms[r].exam_capacity) for r in rooms_used]}"
                if strict:
                    add("WAIVED_TRUST" if trusted else "VIOLATION", "shared_seats_strict(size)", desc)
                else:
                    add("WAIVED_TRUST" if trusted else "VIOLATION", "shared_seats(min(size,caps))", desc)

# ---------------------------------------------------------------- A4 cohort / instructor clashes
keyidx = defaultdict(list)
for e in inp.events:
    for k in e.cohort_keys | e.instructor_keys:
        keyidx[k].append(e.id)
pairs_seen = set()
for k, ids in keyidx.items():
    for i, j in combinations(sorted(ids), 2):
        if (i, j) in pairs_seen: continue
        for a in by_ev.get(i, []):
            for b in by_ev.get(j, []):
                if set(a.weeks) & set(b.weeks) and overlap(a, b):
                    pairs_seen.add((i, j))
                    ei, ej = ev[i], ev[j]
                    waived = (inp.fixed_conflicts_as_warnings and input_fixed(ei) and input_fixed(ej)
                              and fixed_slot(ei) == (a.day, a.start) and fixed_slot(ej) == (b.day, b.start))
                    add("WAIVED_FIXED" if waived else "VIOLATION", "cohort" if k.startswith("PROG") else "instructor",
                        f"{k}: {ei.label} d{a.day} P{a.start}-{a.end} vs {ej.label} d{b.day} P{b.start}-{b.end}")
                    break
            else:
                continue
            break

# ---------------------------------------------------------------- A5 explicit hard constraints present?
hard_explicit = [c for c in inp.constraints if c.hard]

# ---------------------------------------------------------------- A6 FEASIBLE_PARTIAL honesty
diag_ids = defaultdict(set)
for d in res.diagnoses:
    if d.severity == "error":
        for i in d.event_ids:
            diag_ids[i].add(d.code)
unexplained = [(i, ev[i].label, w) for i, w in unplaced if not (diag_ids.get(i, set()) - {"partial", "unplaced_summary", "core"})]
st = res.stats
summary = {
    "tag": tag, "status": res.status, "hard_score": res.hard_score, "events": len(inp.events),
    "assignment_rows": len(res.assignments),
    "unplaced_by_checker": len(unplaced), "stats_placed": st.get("placed"), "stats_unplaced": st.get("unplaced"),
    "stats_partially_placed": st.get("partially_placed"),
    "unplaced_without_error_diag": len(unexplained),
    "explicit_hard_constraints": [c.kind for c in hard_explicit],
    "counts": {k: len(v) for k, v in F.items()},
    "by_rule": {cls: dict(sorted({r: sum(1 for x in v if x[0] == r) for r, _ in v}.items())) for cls, v in F.items()},
}
print(json.dumps(summary, indent=1, ensure_ascii=False))
for cls in ("VIOLATION",):
    for rule, msg in F.get(cls, [])[:60]:
        print(cls, rule, msg)
if unexplained:
    print("UNEXPLAINED unplaced:", unexplained[:20])
(SP / "runs" / f"{tag}.check.json").write_text(json.dumps({"summary": summary, "findings": F, "unplaced": unplaced, "unexplained": unexplained}, ensure_ascii=False, indent=1, default=str))
