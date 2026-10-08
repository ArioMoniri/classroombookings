"""``app.solver.calibrate``: reproduction metrics and the weight-set choice (no DB; the real-data grid
search itself is the CLI)."""

from __future__ import annotations

from app.solver.calibrate import WEIGHT_SETS, Instance, choose, metrics, run_grid, summarise
from tests.solver.conftest import event, make_input, room


def _instance() -> Instance:
    rooms = (room(1, "A101", 40), room(2, "A204", 120))
    a = event(1, size=30, weeks=(1,), day=1, start=1, preferred_room_ids=(2,))  # the planner put it in the hall
    b = event(2, size=30, weeks=(1,), day=2, start=1, preferred_room_ids=(1,))
    return Instance("tiny", "COURSE", make_input(rooms, (a, b), weeks=(1,)), {1: frozenset({2}), 2: frozenset({1})})


def test_metrics_and_choice_follow_the_planners_rooms() -> None:
    inst = _instance()
    sets = {"defaults": {}, "waste-heavy": {"room_preference": 1, "min_capacity_waste": 50}}
    rows = run_grid([inst], sets, time_limit_s=5, workers=1)
    by = {r["weights"]: r for r in rows}
    assert by["defaults"]["repro_exact"] == 2 and by["defaults"]["repro_exact_rate"] == 1.0
    assert by["waste-heavy"]["repro_exact"] == 1  # 9 waste units x 50 beat one preference rank
    assert all(r["hard"] == 100 and r["placed_roomed"] == 2 for r in rows)
    summary = summarise(rows)
    assert choose(summary) == "defaults"
    assert (
        metrics(
            inst, type("R", (), {"assignments": [], "hard_score": 100, "soft_score": 100, "status": "X", "stats": {}})()
        )["repro_exact"]
        == 0
    )
    assert "defaults" in WEIGHT_SETS


def test_choice_needs_a_real_gain_and_never_trades_placement() -> None:
    def per(rate: float, placed: float, hard: float = 100) -> dict[str, dict[str, float]]:
        m = {"repro_exact_rate": rate, "repro_overlap_rate": rate, "placed_roomed": placed, "hard": hard}
        return {"bahar_w3": m, "final": m}

    base = {"defaults": per(0.889, 561)}
    assert choose({**base, "pref30": per(0.894, 560)}) == "defaults"  # +0.5 point: within the seed spread
    assert choose({**base, "pref30": per(0.92, 560)}) == "pref30"  # +3 points, placement within 2 %
    assert choose({**base, "pref30": per(0.95, 520)}) == "defaults"  # better reproduction, 7 % fewer placed
    assert choose({**base, "pref30": per(0.95, 561, hard=99)}) == "defaults"  # never at the cost of a hard rule
