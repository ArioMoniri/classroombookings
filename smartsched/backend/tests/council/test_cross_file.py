"""Reconciler, planner and critic over the real files (fast-path records, as the orchestrator builds them)."""

from __future__ import annotations

import pytest
from app.council import critic, fastpath, planner, reconcile
from app.council.render import render_file

from tests.council.conftest import (
    BAHAR_GRID,
    BAHAR_LIST,
    EN_CSV,
    EXAM_LIST,
    FINAL_GRID,
    GUZ_LIST,
    MEMO_DOCX,
    ROOM_MASTER,
    gen,
)


@pytest.fixture(scope="module")
def six():
    files, recs = [], {}
    for i, p in enumerate([ROOM_MASTER, BAHAR_GRID, BAHAR_LIST, EXAM_LIST, FINAL_GRID, GUZ_LIST]):
        r = render_file(p.read_bytes(), p.name)
        shape = fastpath.detect_shape(r)
        recs[i], _ = fastpath.records_for(shape, p, p.name, 2026)
        files.append({"index": i, "filename": p.name, "sheets": [g.name for g in r.grids]})
    return files, recs


def test_planner_groups_the_files_into_terms(six):
    files, recs = six
    plan = planner.plan(files, recs, [[[p["start"], p["end"]] for p in planner.DEFAULT_GRID]])
    groups = {g["code"]: g for g in plan["groups"]}
    assert set(groups) == {"2026-BAHAR", "2026-FINAL", "2026-2027-GUZ"}
    assert groups["2026-BAHAR"]["files"] == [1, 2] and groups["2026-BAHAR"]["kind"] == "REGULAR"
    assert groups["2026-FINAL"]["files"] == [3, 4] and groups["2026-FINAL"]["kind"] == "FINAL"
    assert groups["2026-BAHAR"]["start_date"] == "2026-02-02"  # Monday of "2 - 8 Şubat"
    assert len(groups["2026-BAHAR"]["weeks"]) == 19
    assert plan["global_files"] == [0]  # the room master belongs to every term
    assert plan["period_grid"]["periods"][0] == {"index": 1, "start": "08:30", "end": "09:10"}


def test_period_grid_inferred_without_a_board():
    meetings = [r for r in gen(EN_CSV)[2] if r["type"] == "meeting"]
    grid = planner.period_grid([], meetings)
    assert grid["source"] in ("default-18", "inferred")
    assert grid["coverage"] is not None and grid["coverage"] > 0.5


def test_reconciler_merges_rooms_and_finds_duplicates(six):
    files, recs = six
    # the English CSV repeats the Bahar list: its meetings are duplicates across files
    en = [r for r in gen(EN_CSV)[2] if r["type"] == "meeting"]
    data = reconcile.reconcile([(2, BAHAR_LIST.name, recs[2]), (9, EN_CSV.name, en)])
    assert len(data["duplicates"]) >= 0.9 * len(en)
    data = reconcile.reconcile([(f["index"], f["filename"], recs[f["index"]]) for f in files])
    rooms = {r["key"]: r for r in data["rooms"]}
    assert rooms["A101"]["capacity"] == 58  # the room master wins over board headers
    assert rooms["A101"]["exam_capacity"] == 30
    assert not data["conflicts"]
    assert any(m["kind"] == "instructor" for m in data["merges"])  # spelled two ways in the real files


def test_critic_cross_checks_and_runs_the_solver_static_checker(six):
    files, recs = six
    sub = {i: recs[i] for i in (0, 1, 2)}
    data = reconcile.reconcile([(i, files[i]["filename"], sub[i]) for i in sub])
    plan = planner.plan([files[i] for i in sub], sub, [[[p["start"], p["end"]] for p in planner.DEFAULT_GRID]])
    issues = critic.check(data, sub, plan)
    codes = {i["code"] for i in issues}
    cap = next(i for i in issues if i["code"] == "capacity")
    assert "MAT112: 180 students, 156 seats in A204" in cap["message"]  # real over-full request
    assert any(c.startswith("solver_static:") for c in codes)
    assert all(i["severity"] in ("error", "warning", "info") for i in issues)
    assert cap["sources"][0]["file"] == BAHAR_LIST.name


def test_memo_rule_texts_are_collected():
    from app.council.extract import rule_texts

    rendered, analyses, recs = gen(MEMO_DOCX)
    texts = rule_texts(rendered, analyses, recs)
    assert any("FYT 112" in t["text"] and "FYT112" in t["course_codes"] for t in texts)
    assert all(t["source"]["file"] == MEMO_DOCX.name and "paragraph" in t["source"] for t in texts)
