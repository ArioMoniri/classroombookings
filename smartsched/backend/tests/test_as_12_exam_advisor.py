"""AS-12 exam date advisor (docs/research/2026-10-17-adaptive-scheduling.md §3.5): advice cards for cohort days
with more than two exams, back-to-back exams of a cohort or an instructor, large exams in the last two days and the
seat peak per slot, with ranked date / slot moves and their conflict delta.  Nothing is changed: the advisor
returns suggestions; B6 applies them *in the test only*."""

from __future__ import annotations

import copy
from datetime import date

from app.services import exam_advisor as ea
from app.services.backtest_solver import b6_exam_advisor

MON, TUE, WED, THU, FRI = (date(2026, 6, d) for d in (1, 2, 3, 4, 5))


def item(i: int, d: date, start: int, *, end: int | None = None, seats: int = 30, cohorts=(), ins=(), rows: int = 1):  # type: ignore[no-untyped-def]
    return ea.ExamItem(
        id=i,
        request_ids=(i,),
        label=f"EX {i}",
        date=d,
        start=start,
        end=end if end is not None else start + 1,
        seats=seats,
        rows=rows,
        cohorts=frozenset(f"PROG:p:Y{c}" for c in cohorts),
        instructors=frozenset(f"INS:{x}" for x in ins),
    )


def kinds(out: dict) -> set[str]:  # type: ignore[type-arg]
    return {c["kind"] for c in out["cards"]}


def test_cohort_with_three_exams_gets_a_card_and_a_move_that_removes_it() -> None:
    items = [item(1, MON, 1, cohorts=(1,)), item(2, MON, 4, cohorts=(1,)), item(3, MON, 7, cohorts=(1,))]
    filler = [item(10 + i, d, 10) for i, d in enumerate((TUE, WED, THU, FRI))]
    out = ea.advise([*items, *filler], dates=[MON, TUE, WED, THU, FRI])
    card = next(c for c in out["cards"] if c["kind"] == "cohort_day")
    assert card["date"] == MON.isoformat() and card["params"]["exams"] == 3
    assert "en çok 2" in card["text"]["tr"] and "at most 2" in card["text"]["en"]
    top = out["suggestions"][0]
    assert top["rank"] == 1 and top["exam_id"] in (1, 2, 3)
    assert top["from"]["date"] == MON.isoformat() and top["to"]["date"] != MON.isoformat()
    assert top["delta"]["cohort_day"] == -1 and top["delta"]["score"] < 0
    assert top["text"]["tr"] and top["text"]["en"]
    assert card["suggestion_ranks"] and card["suggestion_ranks"][0] == 1
    after = ea.apply_moves([*items, *filler], out["suggestions"])
    assert ea.summary(after, dates=[MON, TUE, WED, THU, FRI])["cohort_days_over"] == 0


def test_back_to_back_for_a_cohort_and_an_instructor_is_reported() -> None:
    items = [
        item(1, MON, 1, end=2, cohorts=(1,)),
        item(2, MON, 3, end=4, cohorts=(1,)),  # same cohort right after: back-to-back
        item(3, TUE, 5, end=6, ins=("Kaya",)),
        item(4, TUE, 7, end=8, ins=("Kaya",)),  # same instructor right after
    ]
    out = ea.advise(items, dates=[MON, TUE, WED])
    b2b = [c for c in out["cards"] if c["kind"] == "back_to_back"]
    assert {c["params"]["who"] for c in b2b} == {"cohort", "instructor"}
    assert all(len(c["request_ids"]) == 2 for c in b2b)
    # each is fixable without a new conflict: moves exist and remove them
    assert ea.summary(ea.apply_moves(items, out["suggestions"]), dates=[MON, TUE, WED])["back_to_back"] == 0


def test_large_exam_in_the_last_two_days_is_front_load() -> None:
    big = item(1, FRI, 3, seats=250)
    out = ea.advise([big, item(2, MON, 3), item(3, TUE, 3)], dates=[MON, TUE, WED, THU, FRI])
    card = next(c for c in out["cards"] if c["kind"] == "front_load")
    assert card["request_ids"] == [1] and card["params"]["seats"] == 250
    top = out["suggestions"][0]
    assert top["exam_id"] == 1 and top["to"]["date"] in (MON.isoformat(), TUE.isoformat(), WED.isoformat())
    assert top["delta"]["front_load"] == -1


def test_seat_peak_per_slot_against_exam_capacity() -> None:
    items = [item(1, MON, 3, seats=300), item(2, MON, 3, seats=300), item(3, TUE, 3, seats=50)]
    out = ea.advise(items, exam_capacity=500, dates=[MON, TUE])
    card = next(c for c in out["cards"] if c["kind"] == "seats")
    assert card["date"] == MON.isoformat() and card["params"]["seats"] == 600
    assert card["params"]["exam_capacity"] == 500
    after = ea.summary(ea.apply_moves(items, out["suggestions"]), exam_capacity=500, dates=[MON, TUE])
    assert after["seat_slots_over"] == 0


def test_moves_never_add_a_cohort_or_instructor_conflict() -> None:
    """The only lighter day already holds two exams of the cohort: moving there would make three, so the advisor
    does not offer it (it offers nothing rather than a new conflict)."""
    items = [
        *(item(i, MON, 1 + 2 * (i % 9), cohorts=(9,) if i == 0 else ()) for i in range(10)),
        item(20, TUE, 1, cohorts=(9,)),
        item(21, TUE, 5, cohorts=(9,)),
        item(22, WED, 3, cohorts=(5,)),
    ]
    out = ea.advise(items, dates=[MON, TUE])
    for s in out["suggestions"]:
        assert s["delta"]["cohort_day"] <= 0 and s["delta"]["clash"] <= 0
    after = ea.apply_moves(items, out["suggestions"])
    assert ea.summary(after, dates=[MON, TUE])["cohort_days_over"] == 0
    assert ea.summary(after, dates=[MON, TUE])["clashes"] == 0


def test_advice_only_inputs_untouched_and_deterministic() -> None:
    items = [item(1, MON, 1, cohorts=(1,)), item(2, MON, 4, cohorts=(1,)), item(3, MON, 7, cohorts=(1,))]
    before = copy.deepcopy(items)
    a = ea.advise(items, dates=[MON, TUE, WED])
    b = ea.advise(list(reversed(items)), dates=[MON, TUE, WED])
    assert items == before
    assert a == b
    assert a["changes_nothing"] is True
    assert a["basis"]["tr"] and a["basis"]["en"]


def test_empty_list_answers_none_with_needs() -> None:
    out = ea.advise([])
    assert out["confidence"] == "none" and out["needs"]["tr"] and out["needs"]["en"]
    assert out["cards"] == [] and out["suggestions"] == []


# ------------------------------------------------------------------------------------------------ B6 (real Final)


def test_b6_final_2026_peak_day_98_to_at_most_78_without_new_cohort_conflicts(parsed_exam_list) -> None:  # type: ignore[no-untyped-def]
    # AS20-F13 (FIX-G, 2026-10-18): sittings, a merge group once (was 126 exam-list rows -> <= 100)
    res = b6_exam_advisor(parsed_exam_list)
    m = res.metrics
    assert m["peak_day_before"] == "2026-06-03" and m["peak_exams_before"] == 98
    assert m["peak_exams_after"] <= 78, m
    assert m["cohort_days_over_after"] <= m["cohort_days_over_before"]
    assert m["clashes_after"] <= m["clashes_before"]
    assert m["new_cohort_conflicts"] == 0
    assert m["cohort_days_over_before"] > 0  # reported
    assert 0 < m["moves_accepted"] <= m["suggestions"]
    assert m["deterministic"] is True
    assert res.passed is True
