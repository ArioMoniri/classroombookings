"""AS-14 weight learning from manual edits (inverse optimisation lite, docs/research/2026-10-17-adaptive-scheduling.md
§3.3): each manual move vs its parent run is scored by ``solver/evaluate.py`` per soft term (ΔΦ), agreements per term
pair are counted, the weights that best explain the edits are recovered and a **draft** season-profile version is
proposed with an explanation and evidence (run ids and counts, no names).  Nothing applies without an admin."""

from __future__ import annotations

import math

from app.core.db import get_session_factory
from app.models import Assignment, Course, MeetingRequest, Program, Room, ScheduleRun, Section, Term
from app.models.seasons import SeasonProfile
from app.services import seasons
from app.services import weight_learning as wl
from app.services.backtest_solver import b9_weight_learning
from app.solver.model import Assignment as SA
from sqlalchemy import select

from tests.solver.conftest import event, make_input, room

TRUE = {"room_preference": 12, "building_preference": 7, "day_window": 3, "min_capacity_waste": 1}


def test_edit_deltas_are_raw_units_per_soft_term() -> None:
    rooms = (room(1, "A101", 40), room(2, "B201", 120))
    ev = event(1, size=30, day=1, start=1, preferred_room_ids=(1,), preferred_building="A")
    inp = make_input(rooms, (ev,), (), days=(1,), weights={"room_preference": 99})
    before = [SA(1, 1, 1, 2, (2,), frozenset(inp.weeks))]  # B201: not preferred, wrong building, 9 waste units
    after = [SA(1, 1, 1, 2, (1,), frozenset(inp.weeks))]
    d = wl.edit_deltas(inp, before, after)
    # the run's weights do not matter: units, not weighted penalties
    assert d["room_preference"] == -1 and d["building_preference"] == -1
    assert d["min_capacity_waste"] == -8  # 90 -> 10 empty seats in units of 10
    assert all(isinstance(v, int) for v in d.values())


def test_kendall_tau() -> None:
    assert wl.kendall_tau([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert wl.kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert abs(wl.kendall_tau([1, 2, 3, 4], [1, 3, 2, 4]) - 2 / 3) < 1e-9


def test_b9_recovers_known_weight_ratios() -> None:
    res = b9_weight_learning()
    m = res.metrics
    assert m["edits"] >= 40
    assert m["kendall_tau_ratios"] >= 0.8, m
    assert m["kendall_tau_weights"] >= 0.8, m
    assert m["deterministic"] is True
    assert res.passed is True


def test_learning_is_deterministic_and_explains_the_top_pair() -> None:
    edits = wl.synthetic_edits(TRUE, n=60, seed=7)
    a = wl.learn(edits, current=dict(wl.DEFAULTS))
    b = wl.learn(list(reversed(edits)), current=dict(wl.DEFAULTS))
    assert a.weights == b.weights
    p = wl.proposal(a, current=dict(wl.DEFAULTS), edits=edits)
    assert p is not None
    assert p["status"] == "draft"
    assert p["changes"], p
    # the proposal explains more of the edits than today's weights, and moves toward the planner's ratios
    assert p["edits_explained"] > p["edits_explained_now"]
    proposed = {**{k: wl.DEFAULTS[k] for k in TRUE}, **p["solver_weights"]}
    assert proposed["building_preference"] > wl.DEFAULTS["building_preference"]  # planner: 7 (defaults 5)
    assert proposed["day_window"] < wl.DEFAULTS["day_window"]  # planner: 3 (defaults 5)

    def log_error(w: dict[str, int]) -> float:
        keys = sorted(TRUE)
        return sum(
            abs(math.log(a / b)) for a, b in zip(wl.ratio_vector(w, keys), wl.ratio_vector(TRUE, keys), strict=True)
        )

    assert log_error(proposed) < log_error({k: wl.DEFAULTS[k] for k in TRUE})
    tr, en = p["explanation"]["tr"], p["explanation"]["en"]
    assert "düzenlemenin" in tr and "→" in tr and "edits" in en and "→" in en
    ev = p["evidence"]
    assert ev["edits"] == 60 and ev["pairs"] and "names" not in str(ev).lower()


def test_fewer_than_five_edits_propose_nothing() -> None:
    edits = wl.synthetic_edits(TRUE, n=4, seed=1)
    learned = wl.learn(edits, current=dict(wl.DEFAULTS))
    assert wl.proposal(learned, current=dict(wl.DEFAULTS), edits=edits) is None
    out = wl.propose(edits, current=dict(wl.DEFAULTS))
    assert out["proposal"] is None and out["confidence"] == "none"
    assert out["needs"]["tr"] and out["needs"]["en"] and "5" in out["needs"]["tr"]


# ------------------------------------------------------------------------------------------------ the database path


async def _seed(s, n_edits: int) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """A term with one parent run and a child run whose MANUAL moves put each class into its preferred building
    at the price of more empty seats (the planner valued building over waste)."""
    term = Term(code="2026-BAHAR", name="Bahar", week_count=1)
    s.add(term)
    await s.flush()
    small_b = Room(code="B101", display_name="B101", capacity=40, exam_capacity=20, tags=[], is_bookable=True)
    big_a = Room(code="A301", display_name="A301", capacity=120, exam_capacity=60, tags=[], is_bookable=True)
    s.add_all([small_b, big_a])
    prog = Program(name="Fizik", canonical_name="fizik")
    s.add(prog)
    await s.flush()
    parent = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="OPTIMAL", params={})
    s.add(parent)
    await s.flush()
    child = ScheduleRun(
        term_id=term.id, kind="COURSE", horizon="TERM", status="OPTIMAL", params={}, parent_run_id=parent.id
    )
    s.add(child)
    await s.flush()
    for i in range(n_edits):
        course = Course(code=f"FIZ{100 + i}", display_code=f"FIZ {100 + i}")
        s.add(course)
        await s.flush()
        sec = Section(
            term_id=term.id,
            course_id=course.id,
            program_id=prog.id,
            class_year=1,
            class_years=[1],
            enrolment=30,
            source_key=f"FIZ{100 + i}",
        )
        s.add(sec)
        await s.flush()
        day, start = 1 + i % 5, 1 + 2 * (i // 5)
        mr = MeetingRequest(
            section_id=sec.id,
            day=day,
            days=[day],
            start_period=start,
            end_period=start + 1,
            weeks=[1],
            status="PARSED",
            requested_building="A",
        )
        s.add(mr)
        await s.flush()
        common = {"meeting_request_id": mr.id, "weeks": [1], "day": day, "start_period": start, "end_period": start + 1}
        s.add(Assignment(run_id=parent.id, room_ids=[small_b.id], origin="SOLVER", **common))
        s.add(Assignment(run_id=child.id, room_ids=[big_a.id], origin="MANUAL", **common))
    await s.commit()
    return {"term": term.id, "parent": parent.id, "child": child.id}


async def test_manual_edits_propose_a_draft_profile_never_applied(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s, 6)
        out = await wl.propose_for_term(s, ids["term"], actor=None)
        await s.commit()
    assert out["edits"] == 6 and out["confidence"] in ("low", "medium", "high")
    p = out["proposal"]
    assert p is not None and p["profile_id"]
    assert p["solver_weights"]["building_preference"] > 5
    assert p["evidence"]["run_ids"] == [ids["child"]] and p["evidence"]["parent_run_ids"] == [ids["parent"]]
    async with get_session_factory()() as s:
        listed = await seasons.list_profiles(s)
        drafts = [x for x in listed["profiles"] if x["id"] == p["profile_id"]]
        assert len(drafts) == 1 and drafts[0]["status"] == "draft" and drafts[0]["origin"] == "learned"
        assert drafts[0]["explanation"]["tr"] and drafts[0]["explanation"]["en"]
        # nothing applies without an admin: no active profile, the run weights stay the defaults
        active = list((await s.execute(select(SeasonProfile).where(SeasonProfile.status == "active"))).scalars())
        assert active == []
        probe = ScheduleRun(term_id=ids["term"], kind="COURSE", horizon="TERM", params={})
        eff = await seasons.effective_weights(s, probe)
        assert eff.overrides == {}
        # a second proposal edits the same learned draft in place (no pile of drafts)
        again = await wl.propose_for_term(s, ids["term"], actor=None)
        await s.commit()
        assert again["proposal"]["profile_id"] == p["profile_id"]
        n = (await s.execute(select(SeasonProfile))).scalars().all()
        assert len(n) == 1


async def test_fewer_than_five_manual_edits_answer_needs(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s, 3)
        out = await wl.propose_for_term(s, ids["term"], actor=None)
    assert out["edits"] == 3 and out["proposal"] is None and out["confidence"] == "none"
    assert out["needs"]["tr"] and out["needs"]["en"]


def test_b9_holds_across_seeds() -> None:
    """Not one lucky seed: six different synthetic terms and edit streams all recover the ratio order."""
    taus = [b9_weight_learning(seed=s).metrics["kendall_tau_ratios"] for s in range(6)]
    assert min(taus) >= 0.8, taus
