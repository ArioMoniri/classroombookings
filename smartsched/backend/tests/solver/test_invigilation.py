"""Invigilator assignment (``app/solver/invigilation.py``): posts, every hard rule feasible / infeasible with its
named diagnosis, soft weights, locks, determinism and a scale run."""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import replace

import pytest
from app.solver.invigilation import (
    Busy,
    Duty,
    ExamRoom,
    ExamSlot,
    InvigilationInput,
    Person,
    Post,
    StaffingRule,
    build_posts,
    solve_invigilation,
    split_seats,
    validate,
)

D1 = dt.date(2026, 6, 3)
D2 = dt.date(2026, 6, 4)
ROOMS = {
    1: ExamRoom(1, "A101", "A", 40),
    2: ExamRoom(2, "A204", "A", 120),
    3: ExamRoom(3, "B101", "B", 40),
}


def post(
    key: str, d: dt.date = D1, start: int = 2, end: int = 3, required: int = 1, owners: frozenset[str] = frozenset()
) -> Post:
    return Post(key, d, start, end, 1, key, "A", (hash(key) % 1000,), (key,), 30, required, owners)


def people(n: int, **kw) -> tuple[Person, ...]:
    return tuple(Person(f"STAFF:{i}", f"Kişi {i}", f"kişi {i}", "staff", **kw) for i in range(1, n + 1))


def inp(posts, ppl, **kw) -> InvigilationInput:
    return InvigilationInput(tuple(posts), tuple(ppl), time_limit_s=kw.pop("time_limit_s", 5.0), **kw)


def by_post(res) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for d in res.duties:
        out.setdefault(d.post_key, []).append(d.person_id)
    return out


def plan_of(i: InvigilationInput, res) -> dict[int, list[int]]:
    kidx = {p.key: k for k, p in enumerate(i.posts)}
    pidx = {p.id: n for n, p in enumerate(i.people)}
    out: dict[int, list[int]] = {}
    for d in res.duties:
        out.setdefault(kidx[d.post_key], []).append(pidx[d.person_id])
    return out


# ------------------------------------------------------------------------------------------- posts


def test_split_seats_is_proportional_and_exact():
    assert split_seats(100, [40, 120]) == [25, 75]
    assert sum(split_seats(101, [40, 40, 40])) == 101
    assert split_seats(10, [0, 0]) == [5, 5]
    assert split_seats(7, []) == []


def test_build_posts_merges_shared_rooms_and_counts_by_ratio():
    exams = [
        ExamSlot(1, "PSİ 101", D1, 2, 3, (1,), 20),
        ExamSlot(2, "PSİ 201", D1, 3, 4, (1,), 15),  # overlaps exam 1 in A101: one post P2-P4, 35 seated
        ExamSlot(3, "MAT 112", D1, 2, 3, (1, 2), 100, owner_keys=frozenset({"ayşe kaya"})),  # split 25 + 75
        ExamSlot(4, "FİZ 101", D1, 6, 7, (1,), 10),  # later, own post
        ExamSlot(5, "UZEM 1", D1, 2, 3, (), 50),  # online: no room
        ExamSlot(6, "BİY 101", D2, 2, 3, (3,), 10, invigilators=3),  # explicit request beats the ratio
    ]
    posts, no_room = build_posts(exams, ROOMS, StaffingRule(students_per_invigilator=40))
    assert no_room == [5]
    keyed = {p.key: p for p in posts}
    shared = keyed[f"{D1}|1|2-4"]
    assert set(shared.exam_ids) == {1, 2, 3} and shared.seated == 20 + 15 + 25
    assert shared.required == 2 and "ayşe kaya" in shared.owner_keys
    assert keyed[f"{D1}|2|2-3"].seated == 75 and keyed[f"{D1}|2|2-3"].required == 2
    assert keyed[f"{D1}|1|6-7"].required == 1
    assert keyed[f"{D2}|3|2-3"].required == 3
    capped, _ = build_posts(exams, ROOMS, StaffingRule(students_per_invigilator=10, max_per_room=2))
    assert max(p.required for p in capped if p.date == D1) == 2
    assert {p.key: p.required for p in capped}[f"{D2}|3|2-3"] == 3  # an explicit request is never cut


# ------------------------------------------------------------------------------------------- feasible


def test_feasible_plan_staffs_every_post_and_breaks_nothing():
    posts = [post("a", required=2), post("b", required=1), post("c", start=5, end=6, required=2), post("d", D2)]
    i = inp(posts, people(4))
    res = solve_invigilation(i)
    assert res.status == "OPTIMAL" and res.hard_score == 100 and not res.shortfall
    assert {k: len(v) for k, v in by_post(res).items()} == {"a": 2, "b": 1, "c": 2, "d": 1}
    assert validate(i, plan_of(i, res)) == []
    assert not [d for d in res.diagnoses if d.severity == "error"]


def test_nobody_in_two_places_at_once_and_min_rest():
    posts = [post("a", start=2, end=3), post("b", start=4, end=5)]
    res = solve_invigilation(inp(posts, people(1)))
    assert res.status == "OPTIMAL" and len(res.duties) == 2  # back to back is fine without a rest
    rested = solve_invigilation(inp(posts, people(1), min_rest=1))
    assert rested.status == "INFEASIBLE" and len(rested.duties) == 1
    assert rested.diagnoses[0].code == "slot_shortage"
    overlap = solve_invigilation(inp([post("a"), post("b", start=3, end=4)], people(1)))
    assert overlap.status == "INFEASIBLE" and overlap.stats["missing"] == 1


# ------------------------------------------------------------------------------------------- hard rules


def test_teaching_and_unavailability_are_respected():
    teach = Person("INS:1", "Dr. Ayşe Kaya", "ayşe kaya", busy=(Busy(D1, 1, 3, "teaching", "MAT 112"),))
    away = Person("STAFF:2", "Ali Veli", "ali veli", "staff", busy=(Busy(D1, 3, 3, "unavailable"),))
    free = Person("STAFF:3", "Can Er", "can er", "staff")
    res = solve_invigilation(inp([post("a", start=2, end=3)], (teach, away, free)))
    assert res.status == "OPTIMAL" and [d.person_id for d in res.duties] == ["STAFF:3"]
    nobody = solve_invigilation(inp([post("a", start=2, end=3)], (teach, away)))
    assert nobody.status == "INFEASIBLE"
    d = nobody.diagnoses[0]
    assert d.code == "no_candidates" and d.params["excluded"] == {"teaching": 1, "unavailable": 1}
    assert d.params["add_people"] == 1 and "teaching" in d.message


def test_own_exam_forbid_prefer_allow():
    owner = Person("INS:1", "Dr. Ayşe Kaya", "ayşe kaya")
    other = Person("STAFF:2", "Ali Veli", "ali veli", "staff")
    own = post("own", owners=frozenset({"ayşe kaya"}))
    elsewhere = post("else", start=3, end=4)
    # forbid: the owner never invigilates her own course's exam
    res = solve_invigilation(inp([own], (owner, other), own_exam="forbid"))
    assert [d.person_id for d in res.duties] == ["STAFF:2"]
    res = solve_invigilation(inp([own], (owner,), own_exam="forbid"))
    assert res.status == "INFEASIBLE" and res.diagnoses[0].params["excluded"] == {"own_exam": 1}
    # prefer: she takes her own exam (bonus) and is never sent elsewhere while it runs
    res = solve_invigilation(inp([own, elsewhere], (owner, other), own_exam="prefer"))
    assert by_post(res) == {"own": ["INS:1"], "else": ["STAFF:2"]}
    res = solve_invigilation(inp([elsewhere, own], (owner,), own_exam="prefer"))
    assert res.status == "INFEASIBLE" and by_post(res) == {"own": ["INS:1"]}
    # allow: no rule either way (she may take the other room; the plan is complete with two people)
    res = solve_invigilation(inp([own, elsewhere], (owner, other), own_exam="allow"))
    assert res.status == "OPTIMAL" and len(res.duties) == 2


def test_daily_and_total_caps():
    posts = [post("a", start=1, end=2), post("b", start=4, end=5), post("c", start=7, end=8)]
    res = solve_invigilation(inp(posts, people(1), max_per_day=2))
    assert res.status == "INFEASIBLE" and len(res.duties) == 2
    assert [d.code for d in res.diagnoses] == ["cap_shortage"]
    assert res.diagnoses[0].person_ids == ["STAFF:1"]
    own_cap = (Person("STAFF:1", "A", "a", "staff", max_per_day=3, max_duties=1),)
    res = solve_invigilation(inp(posts, own_cap, max_per_day=2))
    assert len(res.duties) == 1 and res.diagnoses[0].code == "cap_shortage"
    zero = (Person("STAFF:1", "A", "a", "staff", max_duties=0),)
    res = solve_invigilation(inp(posts[:1], zero))
    assert res.diagnoses[0].code == "no_candidates" and res.diagnoses[0].params["excluded"] == {"no_capacity": 1}


def test_slot_shortage_names_a_minimal_set_of_rooms():
    """Three rooms at 10:00 need 4 people; only 3 are free for them (a fourth room's two own people are not
    available to the others): the conflict set is the three rooms, not the fourth."""
    ppl = people(3) + (
        Person("STAFF:8", "X", "x", "staff", busy=()),
        Person("STAFF:9", "Y", "y", "staff"),
    )
    p1, p2, p3 = post("r1", required=2), post("r2"), post("r3")
    p4 = post("r4", required=2)
    i = inp([p1, p2, p3, p4], ppl)
    # make STAFF:8 / STAFF:9 eligible only for r4: busy at r1-r3's time is impossible (same time), so use owners
    i = replace(
        i,
        posts=(
            replace(p1, start=2, end=3),
            replace(p2, start=2, end=3),
            replace(p3, start=2, end=3),
            replace(p4, start=2, end=3, owner_keys=frozenset({"x", "y"})),
        ),
        own_exam="prefer",
    )
    res = solve_invigilation(i)
    assert res.status == "INFEASIBLE" and res.stats["missing"] == 1
    d = next(d for d in res.diagnoses if d.code == "slot_shortage")
    assert sorted(d.post_keys) == ["r1", "r2", "r3"]
    assert d.params["required_total"] == 4 and d.params["people_free"] == 3 and d.params["add_people"] == 1


# ------------------------------------------------------------------------------------------- locks


def test_locks_hold_conflicting_locks_are_named_and_stale_locks_warned():
    posts = [post("a"), post("b", start=5, end=6)]
    ppl = people(3)
    res = solve_invigilation(inp(posts, ppl, locks=(Duty("a", "STAFF:3", True),)))
    assert "STAFF:3" in by_post(res)["a"] and any(d.locked for d in res.duties if d.post_key == "a")
    teach = (Person("INS:1", "T", "t", busy=(Busy(D1, 1, 4, "teaching"),)), *ppl)
    res = solve_invigilation(inp(posts, teach, locks=(Duty("a", "INS:1", True),)))
    assert res.status == "INFEASIBLE" and res.hard_score < 100
    lc = next(d for d in res.diagnoses if d.code == "locked_conflict")
    assert lc.person_ids == ["INS:1"] and lc.params["reason"] == "teaching"
    assert "INS:1" not in by_post(res).get("a", [])  # a lock is never forced through a hard rule
    res = solve_invigilation(inp(posts, ppl, locks=(Duty("gone", "STAFF:1", True),)))
    assert res.status == "OPTIMAL" and [d.code for d in res.diagnoses] == ["lock_stale"]


# ------------------------------------------------------------------------------------------- soft weights


def test_load_is_balanced():
    posts = [post(f"p{n}", start=1 + 2 * n, end=2 + 2 * n) for n in range(4)]
    res = solve_invigilation(inp(posts, people(2), max_per_day=None))
    assert res.status == "OPTIMAL"
    assert sorted(v["duties"] for v in res.loads.values()) == [2, 2]
    assert res.soft_score == 100


def test_load_factor_shifts_the_fair_share():
    posts = [post(f"p{n}", start=1 + 2 * n, end=2 + 2 * n) for n in range(6)]
    ppl = (Person("STAFF:1", "A", "a", "staff", load_factor=200), Person("STAFF:2", "B", "b", "staff"))
    res = solve_invigilation(inp(posts, ppl, max_per_day=None))
    assert res.loads["STAFF:1"]["duties"] == 4 and res.loads["STAFF:2"]["duties"] == 2


def test_same_day_weight_spreads_duties_over_days():
    posts = [post("a", D1, 1, 2), post("b", D1, 4, 5), post("c", D2, 1, 2), post("d", D2, 4, 5)]
    ppl = people(2)
    spread = solve_invigilation(inp(posts, ppl, max_per_day=None, weights={"same_day": 50}))
    days = {pid: v["days"] for pid, v in spread.loads.items()}
    assert days == {"STAFF:1": 2, "STAFF:2": 2}
    assert spread.objective_breakdown["same_day"] == 0


def test_stability_keeps_the_previous_plan_when_it_costs_nothing():
    posts = [post("a"), post("b", D2)]
    ppl = people(2)
    prev = (Duty("a", "STAFF:2"), Duty("b", "STAFF:1"))
    res = solve_invigilation(inp(posts, ppl, previous=prev))
    assert by_post(res) == {"a": ["STAFF:2"], "b": ["STAFF:1"]}
    assert res.objective_breakdown["stability"] == 0
    flipped = solve_invigilation(inp(posts, ppl, previous=(Duty("a", "STAFF:1"), Duty("b", "STAFF:2"))))
    assert by_post(flipped) == {"a": ["STAFF:1"], "b": ["STAFF:2"]}


def test_own_exam_weight_zero_removes_the_preference():
    owner = Person("INS:1", "O", "o")
    ppl = (Person("STAFF:0", "A", "a", "staff"), owner)
    posts = [post("own", owners=frozenset({"o"}))]
    assert by_post(solve_invigilation(inp(posts, ppl)))["own"] == ["INS:1"]
    res = solve_invigilation(inp(posts, ppl, weights={"own_exam": 0}))
    assert res.status == "OPTIMAL" and res.objective_breakdown["own_exam"] == 0


# ------------------------------------------------------------------------------------------- determinism / scale


def _synthetic(n_posts: int, n_people: int, seed: int = 7) -> InvigilationInput:
    rnd = random.Random(seed)
    posts = []
    for k in range(n_posts):
        d = dt.date(2026, 6, 1) + dt.timedelta(days=rnd.randrange(12))
        s = rnd.choice([1, 4, 7, 10, 13])
        posts.append(
            Post(f"{d}|{k}|{s}-{s + 1}", d, s, s + 1, k, f"R{k}", "A", (k,), (f"E{k}",), 30, rnd.choice([1, 1, 2, 3]))
        )
    ppl = []
    for i in range(n_people):
        busy = tuple(
            Busy(dt.date(2026, 6, 1) + dt.timedelta(days=rnd.randrange(12)), s, s + 2, "teaching")
            for s in rnd.sample([1, 4, 7, 10, 13], 2)
        )
        ppl.append(Person(f"INS:{i}", f"P{i}", f"p{i}", busy=busy))
    return InvigilationInput(tuple(posts), tuple(ppl), time_limit_s=10.0)


def test_deterministic():
    i = _synthetic(80, 40)
    a, b = solve_invigilation(i), solve_invigilation(i)
    assert a.duties == b.duties and a.objective_breakdown == b.objective_breakdown and a.status == b.status


@pytest.mark.slow
def test_scale_final_sized():
    """Final-sized: 650 posts, 250 people over 12 days."""
    i = _synthetic(650, 250)
    res = solve_invigilation(i)
    assert res.status in ("OPTIMAL", "FEASIBLE", "INFEASIBLE")
    assert validate(i, plan_of(i, res)) == []
    assert res.stats["missing"] == 0 or all(d.code for d in res.diagnoses)
