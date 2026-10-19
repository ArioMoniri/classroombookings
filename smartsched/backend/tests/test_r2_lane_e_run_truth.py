"""Round-2 lane E (T-R2-26 / T-R2-30): the run truth lists every unplaced class and speaks Turkish.

R2-M-04 / R1-M-14: the report's unplaced list rendered the first diagnoses only (19 of 28, 22 of 34); the truth now
carries ``unplaced_list`` - one entry per unplaced *class* (a joint lecture's members are one entry, like
``unplaced``). R2-M-18: the broken-rule sentences read 'A102 week 3 day 1 P1: ...'; every ``broken`` entry gets a
``message_tr`` ('A102 · 3. hafta Pzt P1: ...') and move_guard uses the same translation.
"""

from __future__ import annotations

from typing import Any

from app.services import run_truth
from app.services.planner_check import CheckData, Req, RoomInfo, Row, check


def _req(i: int, label: str | None = None, **kw: Any) -> Req:
    fields: dict[str, Any] = {
        "id": i,
        "label": label or f"C {i}",
        "day": 1,
        "days": frozenset({1}),
        "start": 1,
        "end": 2,
        "date": None,
        "weeks": frozenset({1, 2}),
        "size": 30,
        "locked": False,
        "definitive": frozenset(),
        "tags": frozenset(),
        "cohort": frozenset(),
        "instructors": frozenset(),
    }
    fields.update(kw)
    return Req(**fields)


def _row(i: int, req: int, rooms: tuple[int, ...] = (1,), **kw: Any) -> Row:
    fields: dict[str, Any] = {
        "id": i,
        "req": req,
        "day": 1,
        "start": 1,
        "end": 2,
        "date": None,
        "weeks": frozenset({1, 2}),
        "rooms": rooms,
        "origin": "SOLVER",
        "is_locked": False,
    }
    fields.update(kw)
    return Row(**fields)


class _Run:
    """The fields ``run_truth.build`` reads (no DB)."""

    def __init__(self, stats: dict[str, Any]) -> None:
        self.status = "FEASIBLE_PARTIAL"
        self.stats = stats
        self.hard_score = 100
        self.diagnosis: list[dict[str, Any]] = []


def test_unplaced_list_names_every_unplaced_class_once() -> None:
    # requests 1..5: 1 placed; 2 and 3 are one joint lecture (head 2) left out; 4 not placed; 5 placed in week 1 only
    reqs = [_req(1), _req(2, "EHM 212 §B1 A"), _req(3, "EHM 212 §B1 B"), _req(4, "MAT 112 §1"), _req(5, "ING 101")]
    rows = [_row(1, 1), _row(2, 5, weeks=frozenset({1}))]
    diags = [{"code": "unplaced", "severity": "error", "event_ids": [2, 4, 5], "event_labels": []}]
    data = CheckData(
        run_id=1,
        exam=False,
        reqs={r.id: r for r in reqs},
        rows=rows,
        rooms={1: RoomInfo(1, "A 102", 60, frozenset(), True)},
        blocks=[],
        members={2: [2, 3]},
        diagnoses=diags,
    )
    res = check(data)
    run = _Run({"placed": 2, "events_total": 4, "event_members": {"2": [2, 3]}})
    truth = run_truth.build(run, res)  # type: ignore[arg-type]
    # Yerleşmeyen = the classes not fully placed (decision 2026-10-19): the two never placed and the partial one
    assert truth["unplaced"] == 3
    lst = truth["unplaced_list"]
    labels = [x["label"] for x in lst]
    assert labels == ["EHM 212 §B1 A + EHM 212 §B1 B", "ING 101", "MAT 112 §1"]
    joint = lst[0]
    assert joint["id"] == 2 and joint["request_ids"] == [2, 3] and joint["weeks"] is None
    partial = next(x for x in lst if x["label"] == "ING 101")
    assert partial["weeks"] == [2]  # placed in week 1, missing week 2
    assert truth["unplaced_count"] == 3  # the list's own length (every class with a missing week)


def test_broken_entries_carry_a_turkish_sentence() -> None:
    reqs = [_req(1, "PHAR 240 §1"), _req(2, "PHAR 474 §1")]
    rows = [_row(1, 1), _row(2, 2)]  # the same room, day and period: a double booking nobody reported
    data = CheckData(
        run_id=1,
        exam=False,
        reqs={r.id: r for r in reqs},
        rows=rows,
        rooms={1: RoomInfo(1, "A102", 60, frozenset(), True)},
        blocks=[],
        members={},
        diagnoses=[],
    )
    res = check(data)
    truth = run_truth.build(_Run({"placed": 2, "events_total": 2}), res)  # type: ignore[arg-type]
    assert truth["verdict"] == "broken"
    b = truth["broken"][0]
    assert b["rule"] == "room_double_booking"
    assert b["message"].startswith("A102 week 1 day 1 P1: PHAR 240 §1, PHAR 474 §1")
    assert b["message_tr"] == "A102 · 1. hafta Pzt P1: PHAR 240 §1, PHAR 474 §1"
    assert "week" not in b["message_tr"] and "day" not in b["message_tr"]


def test_message_tr_covers_the_planner_check_patterns() -> None:
    tr = run_truth.message_tr
    assert tr("MAT 112 §1: not placed") == "MAT 112 §1: yerleşmedi"
    assert tr("ING 101: not placed in week(s) [3, 4]") == "ING 101: 3. ve 4. haftalarda yerleşmedi"
    assert (
        tr("PHAR 240 §1 in A 206 week(s) [3] day 2 P1-P2 vs block 'Bakım'")
        == "PHAR 240 §1, A 206 · 3. hafta Sal P1-P2 · dolu derslik: 'Bakım'"
    )
    assert (
        tr("B 201 week 3 day 1 P1: X, Y (room outside the pool)")
        == "B 201 · 3. hafta Pzt P1: X, Y (havuz dışı derslik)"
    )
    assert tr("ING 302: 100 students in B 201 (30 seats)") == "ING 302: 100 öğrenci, B 201 (30 koltuk)"
    assert tr("ING 302 needs a PC room, placed in A 102") == "ING 302 PC derslik ister; yerleştiği derslik A 102"
    assert tr("cohort 'TIP-1': A day 1 P1-P2 vs B day 1 P2-P3") == "sınıf 'TIP-1': A Pzt P1-P2 ↔ B Pzt P2-P3"
    assert tr("MAT 112 §1: requested 1 P1-P2, placed 2 P3-P4") == "MAT 112 §1: istenen Pzt P1-P2, yerleşen Sal P3-P4"
