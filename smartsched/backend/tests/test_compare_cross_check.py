"""tools/compare_planner.py: the data-issues cross-check knows the board-only groups (2026-10-08 follow-ups).

The rows are the real Bahar term findings of the comparison re-run (run 8): before this mapping every
``board_*`` item of the report was counted as "not confirmed by the independent audit" (541 of 722 false
alarms were ``board_time_not_in_list``) although the audit found the same board cells itself.
"""

from __future__ import annotations

from typing import Any

from tools.compare_planner import audit_cross_check


def _finding(sub: str, ids: list[int], label: str) -> dict[str, Any]:
    return {"cls": "e", "sub": sub, "request_ids": ids, "label": label, "detail": "", "refs": []}


def _item(code: str, ids: list[int], course: str = "") -> dict[str, Any]:
    classes = [{"course_code": course}] if course else []
    return {"code": code, "message": f"{code} {ids}", "request_ids": ids, "classes": classes}


def _res(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"instance": {"kind": "REGULAR"}, "planner_errors": [], "findings": []}
    base["data_rule_requests"] = {"same_course_two_rows": [], "joint_cell_not_in_list": []}
    return base | kw


def test_board_only_cells_confirm_the_board_groups() -> None:
    res = _res(
        findings=[
            # '2  - 8 Şubat Bahar Dönem Açılış'!M3: the list has HEM 334 on Friday, the board on Monday P1-P3
            _finding("board_only_no_request_at_time", [40, 64, 281], "HEM 334 / NRS 304"),
            # '2  - 8 Şubat Bahar Dönem Açılış'!EI8: PHAR224 is not in the list
            _finding("board_only_unknown_code", [106, 120, 265], "PHAR 220-224"),
        ],
        data_rule_requests={"same_course_two_rows": [], "joint_cell_not_in_list": [240]},  # ING 106 'BO26'
    )
    groups = {
        "board_time_not_in_list": [_item("board_time_not_in_list", [40, 64, 281])],
        "board_unknown_code": [_item("board_unknown_code", [106])],
        "board_two_classes": [_item("board_two_classes", [240])],
    }
    missed, false_alarms = audit_cross_check(res, groups)
    assert missed == []
    assert false_alarms == []


def test_unconfirmed_board_items_stay_false_alarms() -> None:
    groups = {"board_time_not_in_list": [_item("board_time_not_in_list", [999])]}
    _missed, false_alarms = audit_cross_check(_res(), groups)
    assert [(f["group"], f["request_ids"]) for f in false_alarms] == [("board_time_not_in_list", [999])]
    assert false_alarms[0]["why"] == "not confirmed by the independent audit"


def test_board_capacity_and_instructor_errors_count_in_either_group() -> None:
    err = {"source": "board", "label": "MBG 034 §1", "severity": 50, "text": "room too small", "refs": []}
    res = _res(
        planner_errors=[
            {**err, "request_id": 257, "rule": "capacity"},  # 80 students in B 407 (30 seats)
            {**err, "request_id": 29, "rule": "instructor_clash", "text": "Cemre SAVAŞAN in A 204 and A 207"},
            {**err, "request_id": 31, "rule": "capacity"},
        ]
    )
    groups = {
        "board_capacity": [_item("board_capacity", [257])],
        "fixed_instructor_clash": [_item("fixed_instructor_clash", [29])],
    }
    missed, false_alarms = audit_cross_check(res, groups)
    assert [(m["request_id"], m["group"]) for m in missed] == [(31, "locked_room_too_small")]
    assert false_alarms == []


def test_same_lecture_twice_is_confirmed_by_the_audit_data_rule() -> None:
    res = _res(data_rule_requests={"same_course_two_rows": [389, 200], "joint_cell_not_in_list": []})
    groups = {"same_lecture_twice": [_item("same_lecture_twice", [200, 389], "BME 528")]}
    assert audit_cross_check(res, groups) == ([], [])
