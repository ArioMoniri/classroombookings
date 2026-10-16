"""Flow loop round 1, lane F2 (docs/ROADMAP.md "Flow loop tickets — round 1", ``rounds/round-1-tickets.json``):
the invigilation default pool and the moderation match rate of an imported board, on the real 2026 fixtures.

* T-R1-42: the exam list's people are found among the Instructor rows the way the importer parses names (titles
  dropped, Turkish folding), plus the shapes a masked or hand-written list has (initials, a ``#id`` suffix, a middle
  name left out); the plan says how many matched (``pool`` on the brief), and an empty pool says why and offers
  'Tüm eğitmenler' as a one-tap suggestion.
* T-R1-39 part 2: with the imported Güz board published, the moderation matchings place its requests from the
  board's cells (course, day, period, week, room), so the header rate is not 0 % with 624 "unplaced" requests.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services import invigilation as svc

from tests.api_fixtures import login
from tests.test_api_runs import _import_guz
from tests.test_invigilation_api import P, _wait, invig_dir, real  # noqa: F401
from tests.test_loop_r1_laneF import _publish_board

# --------------------------------------------------------------------------------------------------
# T-R1-42: exam-list people -> instructor rows
# --------------------------------------------------------------------------------------------------


@dataclass
class _Ins:
    id: int
    canonical_name: str
    full_name: str


def test_t_r1_42_exam_people_match_initials_titles_and_masked_rows():
    # the KVKK-masked stack: rows are "E. E. K." / "e. e. k. #1", the exam list says "Dr. Öğr. Üyesi E. E. K."
    rows = [
        _Ins(1, "e. e. k. #1", "E. E. K."),
        _Ins(2, "a. a. #2", "A. A."),
        _Ins(3, "a. a. #3", "A. A."),
        _Ins(4, "mehmet yılmaz", "Mehmet Yılmaz"),
        _Ins(5, "ayşe can kaya", "Ayşe Can Kaya"),
        _Ins(6, "özgür şen", "Özgür Şen"),
    ]
    owners = {
        k: shown
        for text in (
            "Dr. Öğr. Üyesi E. E. K.",
            "Prof. Dr. A. A.",
            "Öğ. Üy. Mehmet YILMAZ",  # a title abbreviation the importer does not know
            "Ayşe Kaya",  # middle name left out
            "Ozgur SEN",  # no diacritics
            "Zeynep Demir",  # not an instructor
        )
        for k, shown in svc.person_keys(text)
    }
    m = svc.match_exam_people(owners, rows)
    assert m.exam_people == 6
    assert m.key_of == {1: "e. e. k.", 4: "öğ. üy. mehmet yılmaz", 5: "ayşe kaya", 6: "ozgur sen"}
    assert m.matched == 4 and m.ambiguous == ["A. A."] and m.unmatched == ["Zeynep Demir"]
    assert m.by == {"folded": 3, "middle_name": 1}


async def test_t_r1_42_plan_reports_the_pool_match_and_an_empty_pool_offers_all_instructors(real):  # noqa: F811
    c = real["client"]
    d = (await c.get(f"{P}/plans/{real['plan']}")).json()
    pool = d["pool"]
    assert pool["instructor_pool"] == "exam_instructors"
    assert pool["exam_people"] > 100 and pool["matched"] > 100 and pool["size"] > 100
    assert pool["matched"] + pool["ambiguous"] + pool["unmatched"] == pool["exam_people"]
    # the list view carries the same numbers
    briefs = (await c.get(f"{P}/plans", params={"exam_run_id": real["exam_run"]})).json()
    assert next(b for b in briefs if b["id"] == real["plan"])["pool"] == pool
    # headline numbers are written with a decimal comma in Turkish, never "12.0"
    assert ".0" not in d["headline"]["tr"] and "12.0" not in d["headline"]["en"]

    r = await c.post(f"{P}/plans", json={"exam_run_id": real["exam_run"], "params": {"instructor_pool": "none"}})
    e = await _wait(c, r.json()["plan_id"])
    assert e["pool"]["instructor_pool"] == "none" and e["pool"]["size"] == 0
    empty = next(x for x in e["diagnosis"] if x["code"] == "pool_empty")
    assert empty["severity"] == "error" and "Eğitmen yok" in empty["text"]["tr"]
    assert [s["code"] for s in empty["suggestions"]] == ["pool_all"]
    assert "Tüm eğitmenler" in empty["suggestions"][0]["text"]["tr"]


# --------------------------------------------------------------------------------------------------
# T-R1-39 part 2: the moderation rate of a published imported board
# --------------------------------------------------------------------------------------------------


async def test_t_r1_39_board_assignments_place_the_requests_for_the_moderation_rate(client):
    h = await login(client)
    term_id = await _import_guz()
    board = await _publish_board(term_id)
    r = await client.get(f"/api/v1/terms/{term_id}/moderation/matchings", params={"limit": 5000}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["run_id"] == board and d["source"] == "run"
    counts = d["counts"]
    # the board (weeks 1-2 of the grid, one row per period) places most of the requests that need a room
    assert counts["satisfied"] > 300, counts
    assert d["match_rate"] is not None and d["match_rate"] > 0.5, (d["match_rate"], counts)
    placed = [it for it in d["items"] if it["assigned"] is not None]
    assert placed
    # a placed request reads the board's cell: the request's own day and period range, the board's room, weeks 1-2
    for it in placed[:50]:
        a = it["assigned"]
        assert a["origin"] == "IMPORT" and a["room_ids"] and set(a["weeks"]) <= {1, 2}
        if it["verdict"] == "satisfied":
            req = it["requested"]
            assert (a["day"], a["start_period"], a["end_period"]) == (
                req["day"],
                req["start_period"],
                req["end_period"],
            )
    # BCT 133 §1 (Mon P1-P2, planner room A 101 = board room): satisfied from two one-period cells
    bct = next(it for it in d["items"] if it["label"] == "BCT 133 §1")
    assert bct["verdict"] == "satisfied", bct["reason"]
    assert (bct["assigned"]["start_period"], bct["assigned"]["end_period"]) == (1, 2)
