"""Bridge and run-param parts of P19-M2 / M3 (small seeded terms, fast):

* stored coordinator priorities (request override > section > 0) and the ``priorities`` run param on top;
* run-scoped rules inherited along ``parent_run_id`` (decision "AI backlog finished" 2026-10-15), without double
  counting chat copies, switched off by a disabled copy or ``inherit_run_rules: false``;
* ``publish_candidate`` and moderation re-solves always solve with one worker (owner decision 2026-10-15);
* the moderation unlock of a draft child run;
* the matching flags and verdicts of ``app.services.moderation`` on hand-made rows.
"""

from __future__ import annotations

import pytest
from app.core.db import get_session_factory
from app.models import ConstraintRow, MeetingRequest, Room, ScheduleRun, Section
from app.services import run_params as rp
from app.services.moderation import Place, Want, flags_for, verdict_of
from app.services.solver_bridge import build_solver_input, solver_workers

from tests.test_review_solver_fixes import Seed


async def _term() -> tuple[int, dict[str, int]]:
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("T-MOD")
        await seed.rooms(("A101", 60, [], True), ("A102", 60, [], True))
        await seed.meeting("lock", "PHAR 114", section="2", size=40, start=1, end=2, locked=["A101"])
        await seed.meeting("a", "MAT 112", section="1", size=40, year=2, start=3, end=4)
        await s.commit()
        return tid, dict(seed.ids)


def _probe(tid: int, **kw: object) -> ScheduleRun:
    return ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", **kw)  # type: ignore[arg-type]


async def test_stored_priorities_request_over_section_and_run_param_on_top(engine):
    tid, ids = await _term()
    async with get_session_factory()() as s:
        mr = await s.get(MeetingRequest, ids["a"])
        assert mr is not None
        sec = await s.get(Section, mr.section_id)
        assert sec is not None
        sec.priority = 2
        await s.commit()
        inp, _m = await build_solver_input(s, _probe(tid))
        assert {e.id: e.priority for e in inp.events} == {ids["lock"]: 0, ids["a"]: 2}
        mr.priority = -1  # the request override wins over its section
        await s.commit()
        inp, _m = await build_solver_input(s, _probe(tid))
        assert {e.id: e.priority for e in inp.events}[ids["a"]] == -1
        probe = _probe(tid, params={"priorities": {str(ids["a"]): 7}})
        inp, _m = await build_solver_input(s, probe)
        assert {e.id: e.priority for e in inp.events}[ids["a"]] == 7
        assert probe.stats["relaxation_policy"]["priorities"] == 1
        assert probe.stats["relaxation_policy"]["stored_priorities"] == 1


async def _rule(s, run_id: int | None, *, term_id: int | None = None, enabled: bool = True, ref=None) -> int:  # type: ignore[no-untyped-def]
    row = ConstraintRow(
        term_id=term_id,
        run_id=run_id,
        kind="room_preference",
        params={"event_ids": [1], "room_ids": [1]},
        hardness="soft",
        weight=3,
        source="AI",
        enabled=enabled,
        source_ref=ref,
    )
    s.add(row)
    await s.flush()
    return row.id


async def test_run_scoped_rules_are_inherited_along_the_parent_chain(engine):
    tid, _ids = await _term()
    async with get_session_factory()() as s:
        root = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", status="FEASIBLE")
        s.add(root)
        await s.flush()
        mid = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", status="FEASIBLE", parent_run_id=root.id)
        other = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", status="FEASIBLE")
        s.add_all([mid, other])
        await s.flush()
        r_root = await _rule(s, root.id)
        r_root2 = await _rule(s, root.id)
        r_other = await _rule(s, other.id)
        # a chat child holds a copy of its parent's run rule: counted once (the copy, nearest wins)
        copy = await _rule(s, mid.id, ref={"inherited_from": r_root})
        # a disabled copy clears the ancestor's rule for every descendant
        await _rule(s, mid.id, enabled=False, ref={"inherited_from": r_root2})
        term_rule = await _rule(s, None, term_id=tid)
        await s.commit()
        leaf = _probe(tid, parent_run_id=mid.id)
        inp, _m = await build_solver_input(s, leaf)
        got = [c.id for c in inp.constraints]
        assert got.count(copy) == 1 and r_root not in got and r_root2 not in got and r_other not in got
        assert term_rule in got
        assert leaf.stats["inherited_run_rules"] == {str(copy): mid.id}
        # straight from the root: both root rules
        child = _probe(tid, parent_run_id=root.id)
        inp, _m = await build_solver_input(s, child)
        assert {r_root, r_root2} <= {c.id for c in inp.constraints}
        # explicitly cleared
        cleared = _probe(tid, parent_run_id=root.id, params={"inherit_run_rules": False})
        inp, _m = await build_solver_input(s, cleared)
        assert not {r_root, r_root2} & {c.id for c in inp.constraints}
        assert "inherited_run_rules" not in (cleared.stats or {})


def test_publish_candidate_and_moderation_runs_use_one_worker():
    assert rp.clean_client_params({"publish_candidate": True, "workers": 6}) == {
        "publish_candidate": True,
        "workers": 1,
    }
    # the server default merged in later (POST /runs) cannot bring the threads back
    assert rp.clamp_server_params({"workers": 8, "publish_candidate": True})["workers"] == 1
    assert rp.clamp_server_params({"workers": 8, "moderation": {"mode": "repair"}})["workers"] == 1
    assert rp.clamp_server_params({"workers": 4})["workers"] == 4
    assert solver_workers({"workers": 8, "publish_candidate": True}) == 1
    assert solver_workers({"workers": 8, "moderation": {}}) == 1
    assert solver_workers({"workers": 3}) == 3 and solver_workers({}) == 8
    assert rp.clean_client_params({"inherit_run_rules": False}) == {"inherit_run_rules": False}
    for key in ("moderation", "unlock_request_ids"):
        with pytest.raises(rp.ParamError, match="moderation"):
            rp.clean_client_params({key: {}})
    with pytest.raises(rp.ParamError):
        rp.clean_client_params({"publish_candidate": "yes"})


async def test_bridge_input_of_a_publish_candidate_has_one_worker(engine):
    tid, _ids = await _term()
    async with get_session_factory()() as s:
        inp, _m = await build_solver_input(s, _probe(tid, params={"workers": 8, "publish_candidate": True}))
        assert inp.workers == 1
        inp, _m = await build_solver_input(s, _probe(tid, params={"workers": 8}))
        assert inp.workers == 8


async def test_unlock_releases_the_planner_lock_and_keeps_its_room_as_a_wish(engine):
    tid, ids = await _term()
    async with get_session_factory()() as s:
        inp, _m = await build_solver_input(s, _probe(tid))
        ev = next(e for e in inp.events if e.id == ids["lock"])
        assert ev.locked is not None
        probe = _probe(tid, params={"unlock_request_ids": [ids["lock"]]})
        inp, _m = await build_solver_input(s, probe)
        ev = next(e for e in inp.events if e.id == ids["lock"])
        assert ev.locked is None and ev.preferred_room_ids[0] == ids["room:A101"]
        assert (ev.fixed_day, ev.fixed_start, ev.duration) == (1, 1, 2) and "TIP" in ev.forbidden_tags
        assert any(d["code"] == "unlocked" for d in probe.stats["bridge_diagnoses"])


def _room(rid: int, code: str, tags: list[str] | None = None) -> Room:
    return Room(id=rid, code=code, display_name=f"{code[:1]} {code[1:]}", capacity=60, tags=tags or [])


def test_flags_and_verdicts():
    rooms = {1: _room(1, "D202"), 2: _room(2, "A206"), 3: _room(3, "A103", ["PC"])}
    # PHY 102 (Bahar R49): asked D 204, got D 202 -> building yes, room no -> partly
    want = Want(room_groups=[frozenset({"D204"})], building="D", days=frozenset({5}), start=3, end=4)
    f = flags_for(want, Place(5, 3, 4, (1,), (3,)), rooms)
    assert f == {"room": False, "building": True, "tags": None, "day": True, "period": True}
    assert verdict_of(f) == "partial"
    # alternatives: one whole group is enough ("A 206 veya C 403-404")
    want = Want(room_groups=[frozenset({"A206"}), frozenset({"C403", "C404"})])
    assert flags_for(want, Place(1, 1, 2, (2,), ()), rooms)["room"] is True
    # tags and a moved time
    want = Want(tags=frozenset({"PC"}), days=frozenset({2}), start=1, end=2)
    f = flags_for(want, Place(2, 3, 4, (2,), ()), rooms)
    assert f["tags"] is False and f["period"] is False and verdict_of(f) == "not_as_requested"
    assert verdict_of(flags_for(want, Place(2, 1, 2, (3,), ()), rooms)) == "satisfied"
    # nothing asked beyond the time: satisfied when the time holds
    assert verdict_of({"room": None, "building": None, "tags": None, "day": True, "period": True}) == "satisfied"
