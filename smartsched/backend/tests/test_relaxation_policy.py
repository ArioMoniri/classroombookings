"""Per-term relaxation policy (user decision 2026-10-15) end to end through the bridge: ``lock_first`` (default)
keeps the planner's locked rows, then the coordinator priority, then the most classes; ``most_classes_first``
is the alternative; the policy comes from ``params.relaxation_policy`` > the term setting
``term.<id>.relaxation_policy`` > the default; priorities from ``params.priorities``.  The run report names
every loser and the reason in TR and EN, and every run is valid at planner level."""

from __future__ import annotations

from typing import Any

import pytest
from app.core.db import get_session_factory
from app.models import ScheduleRun
from app.services import run_params as rp
from app.services.solver_bridge import POLICY_LOSS_TEXT, build_solver_input, policy_report

from tests.test_review_solver_fixes import Seed, _planner_ok, _solve


async def _lock_vs_two() -> tuple[int, dict[str, int]]:
    """One room; the planner's lock holds it P1-P4, two other classes need it at P1-P2 and P3-P4."""
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("T-POL")
        await seed.rooms(("A101", 60, [], True))
        await seed.meeting("lock", "PHAR 114", section="2", size=40, start=1, end=4, locked=["A101"])
        await seed.meeting("a", "MAT 112", section="1", size=40, year=2, start=1, end=2)
        await seed.meeting("b", "FIZ 101", section="1", size=40, year=3, start=3, end=4)
        await s.commit()
        return tid, dict(seed.ids)


def _unplaced(run: ScheduleRun) -> list[int]:
    return sorted(run.stats.get("unplaced_ids") or [])


def _loss(run: ScheduleRun, rid: int) -> dict[str, Any]:
    d = next(d for d in run.diagnosis if d["code"] == "unplaced" and d["event_ids"] == [rid])
    return d


async def test_default_lock_first_keeps_the_locked_row_and_explains_in_tr_and_en(engine):
    tid, ids = await _lock_vs_two()
    run = await _solve(tid)
    assert run.status == "FEASIBLE_PARTIAL" and run.hard_score == 100
    assert run.stats["relaxation_policy"]["policy"] == "lock_first"
    assert run.stats["relaxation_policy"]["source"] == "default"
    assert _unplaced(run) == sorted([ids["a"], ids["b"]])
    for rid in (ids["a"], ids["b"]):
        d = _loss(run, rid)
        assert d["params"]["policy"]["reason"] == "locked_row_kept"
        assert d["params"]["policy"]["winners"] == [ids["lock"]]
        assert "Kilitli satır korundu: PHAR" in d["text"]["tr"] and "Locked row kept: PHAR" in d["text"]["en"]
    summary = next(d for d in run.diagnosis if d["code"] == "policy_losses")
    assert summary["params"]["by_reason"] == {"locked_row_kept": 2}
    assert summary["text"]["tr"].startswith("Çakışma politikası (önce kilitli satırlar")
    assert "2 request(s) not placed (2 locked row kept)" in summary["text"]["en"]
    assert run.stats["policy_losses"] == {"locked_row_kept": 2}
    await _planner_ok(run)


async def test_most_classes_first_per_run_and_per_term(engine):
    tid, ids = await _lock_vs_two()
    run = await _solve(tid, relaxation_policy="most_classes_first")
    assert run.stats["relaxation_policy"]["source"] == "run"
    assert _unplaced(run) == [ids["lock"]]
    d = _loss(run, ids["lock"])
    assert d["params"]["policy"]["reason"] == "most_classes"
    assert "dışarıda kalacaktı" in d["text"]["tr"] and "at least as many other classes out" in d["text"]["en"]
    await _planner_ok(run)
    # the term setting (settings table, term.<id>.relaxation_policy) without a run param
    async with get_session_factory()() as s:
        await rp.set_term_relaxation_policy(s, tid, "most_classes_first")
        assert await rp.term_relaxation_policy(s, tid) == ("most_classes_first", "term")
    run = await _solve(tid)
    assert run.stats["relaxation_policy"] == {
        "policy": "most_classes_first",
        "source": "term",
        "priorities": 0,
        "prioritised_events": 0,
    }
    assert _unplaced(run) == [ids["lock"]]
    # a run param still wins over the term setting
    run = await _solve(tid, relaxation_policy="lock_first")
    assert _unplaced(run) == sorted([ids["a"], ids["b"]])
    # a stored typo falls back to the default and is reported
    async with get_session_factory()() as s:
        from app.services.settings_service import set_value

        await set_value(s, rp.term_policy_key(tid), "locks_please")
    run = await _solve(tid)
    assert run.stats["relaxation_policy"]["source"] == "invalid_setting"
    assert any(d["code"] == "invalid_setting" for d in run.diagnosis)
    assert _unplaced(run) == sorted([ids["a"], ids["b"]])


async def test_locked_rows_clash_higher_priority_wins_and_the_loser_is_named(engine):
    """Policy Q5: two locked rows hold one room at once; the higher coordinator priority is placed and the
    other is reported as "Karşılanmadı: kilit çakışması"; the priorities come from the run params."""
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("T-Q5")
        await seed.rooms(("B204", 60, [], True))
        await seed.meeting("bme", "BME 528", section="1", size=30, day=5, start=3, end=4, locked=["B204"])
        # overlapping but not the same slot: a double booking, not one lecture listed twice (no merge)
        await seed.meeting("rad", "RAD 282", section="1", size=50, year=2, day=5, start=4, end=5, locked=["B204"])
        await s.commit()
        ids = dict(seed.ids)
    run = await _solve(tid, priorities={str(ids["bme"]): 5})
    assert run.stats["relaxation_policy"]["priorities"] == 1
    assert _unplaced(run) == [ids["rad"]]  # the larger class loses: priority first
    d = _loss(run, ids["rad"])
    assert d["params"]["policy"]["reason"] == "lock_clash_priority"
    assert "Karşılanmadı: kilit çakışması; BME" in d["text"]["tr"] and "has the higher priority" in d["text"]["en"]
    pre = next(x for x in run.diagnosis if x["code"] == "locked_overlap")
    assert pre["params"]["keeps"] == ids["bme"]
    await _planner_ok(run)
    run = await _solve(tid)  # no priorities: equal; the larger class is kept, named as a tie
    assert _unplaced(run) == [ids["bme"]] and _loss(run, ids["bme"])["params"]["policy"]["reason"] == "lock_clash_tie"


async def test_priority_beats_the_count_under_lock_first(engine):
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("T-PRIO")
        await seed.rooms(("A101", 60, [], True))
        await seed.meeting("hi", "NRS 204", section="1", size=40, start=1, end=4)
        await seed.meeting("a", "MAT 112", section="1", size=40, year=2, start=1, end=2)
        await seed.meeting("b", "FIZ 101", section="1", size=40, year=3, start=3, end=4)
        await s.commit()
        ids = dict(seed.ids)
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={"priorities": {str(ids["hi"]): 2}})
        inp, _m = await build_solver_input(s, probe)
    assert {e.id: e.priority for e in inp.events}[ids["hi"]] == 2 and inp.relaxation_policy == "lock_first"
    run = await _solve(tid, priorities={str(ids["hi"]): 2})
    assert _unplaced(run) == sorted([ids["a"], ids["b"]])
    assert _loss(run, ids["a"])["params"]["policy"]["reason"] == "lower_priority"
    assert "Daha düşük öncelik: önce NRS" in _loss(run, ids["a"])["text"]["tr"]
    await _planner_ok(run)
    run = await _solve(tid, priorities={str(ids["hi"]): 2}, relaxation_policy="most_classes_first")
    assert _unplaced(run) == [ids["hi"]]


def test_run_params_validate_policy_and_priorities():
    ok = rp.clean_client_params({"relaxation_policy": "most_classes_first", "priorities": {"12": 3, 7: -2}})
    assert ok == {"relaxation_policy": "most_classes_first", "priorities": {"12": 3, "7": -2}}
    for bad in (
        {"relaxation_policy": "random"},
        {"priorities": {"x": 1}},
        {"priorities": {"5": 1000}},
        {"priorities": [1, 2]},
    ):
        with pytest.raises(rp.ParamError):
            rp.clean_client_params(bad)


def test_policy_report_texts_cover_every_reason():
    from app.solver.policy import LOSS_REASONS

    assert set(LOSS_REASONS) - {"no_option"} == set(POLICY_LOSS_TEXT)
    diags = [
        {"code": "unplaced", "event_ids": [1], "params": {"policy": {"reason": "no_option", "winners": []}}},
        {"code": "partial", "event_ids": [], "params": {}},
    ]
    rep = policy_report(diags, {1: "SYS 19"}, "most_classes_first")
    assert rep is not None and rep["params"]["by_reason"] == {"no_option": 1}
    assert "SYS 19: uygun oda/saat kalmadı." in rep["text"]["tr"] and "önce en çok ders" in rep["text"]["tr"]
    assert policy_report([{"code": "unplaced", "event_ids": [1], "params": {}}], {}, "lock_first") is None


def test_new_solver_codes_have_tr_and_en_texts():
    from app.services.solver_bridge import solver_code_text

    labels = {1: "ING 101", 2: "MAT 112 §1"}
    w = solver_code_text(
        {"code": "waived_rules", "event_ids": [1], "params": {"rules": ["capacity"], "events": 1}}, labels
    )
    assert w is not None and "kapasite" in w["tr"] and "ING 101" in w["tr"] and "covers the other" in w["en"]
    m = solver_code_text({"code": "missing_only_week", "event_ids": [2], "params": {"week": 1, "count": 1}}, labels)
    assert m is not None and "1. hafta dışında" in m["tr"] and "except week 1" in m["en"]
    a = solver_code_text({"code": "lock_accessibility", "event_ids": [2], "params": {"room_codes": ["C602"]}}, labels)
    assert a is not None and "erişilebilirlik" in a["tr"] and "C602" in a["en"]
    assert solver_code_text({"code": "unplaced", "event_ids": [1], "params": {}}, labels) is None
