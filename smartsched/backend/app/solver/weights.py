"""Default soft-objective weights, overridable through ``SolverInput.weights``.

Every penalty unit of a soft term is multiplied by ``base_weight(kind) * Constraint.weight``.
Implicit (event-field derived) terms use ``Constraint.weight == 1``.
"""

from __future__ import annotations

from collections.abc import Mapping

DEFAULT_WEIGHTS: dict[str, int] = {
    # soft versions of structural rules (only when an explicit Constraint says hard=False)
    "capacity": 50,
    "fixed_time": 30,
    "room_tags": 20,
    "room_pin": 20,
    "room_forbid": 20,
    "room_closed": 20,
    # genuinely soft preferences
    "room_preference": 10,
    "building_preference": 5,
    "min_capacity_waste": 1,
    "same_room_group": 8,
    "same_room_across_weeks": 8,
    "stability": 1,
    "stability_room": 20,
    "stability_time": 30,
    "exam_gap": 10,
    "max_exams_per_day": 10,
    "day_window": 5,
    "evening_programs_in_buildings": 5,
}

#: capacity waste is counted in units of this many seats (a 156-seat hall for 20 students = 13 units)
CAPACITY_WASTE_UNIT = 10


def base_weight(weights: Mapping[str, int], name: str) -> int:
    """Weight for a named term: user override, else default, else 1."""
    value = weights.get(name)
    if value is None:
        value = DEFAULT_WEIGHTS.get(name, 1)
    return max(0, int(value))


def constraint_weight(weights: Mapping[str, int], kind: str, multiplier: int, name: str | None = None) -> int:
    """Effective weight of a soft term: ``base_weight(name or kind) * Constraint.weight``."""
    return base_weight(weights, name or kind) * max(0, int(multiplier))
