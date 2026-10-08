"""Planner-facing data-conflict report (``GET /runs/{id}/data-issues`` + ``?format=xlsx``): the run's
warnings and unplaced reasons grouped by the problem in the planner's own data, with every class
(request) involved."""

from __future__ import annotations

import io

from app.core.db import get_session_factory
from app.models import (
    Assignment,
    Block,
    Course,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
)
from app.services.data_issues import GROUPS, TextContext, classify, message_tr, order_for_report, planner_text
from app.workers.queue import get_queue
from openpyxl import load_workbook

from tests.api_fixtures import login


def test_classify_maps_every_named_group() -> None:
    cases = {
        "locked_room_overlap": {"code": "locked_overlap"},
        "fixed_instructor_clash": {"code": "input_conflict", "params": {"keys": [["no_instructor_overlap", "INS:1"]]}},
        "fixed_cohort_clash": {"code": "input_conflict", "params": {"keys": [["no_cohort_overlap", "PROG:x:Y1"]]}},
        "locked_room_too_small": {"code": "trusted_lock_capacity"},
        "missing_tags": {"code": "no_room", "params": {"reason": "tags"}},
        "rooms_outside_pool": {"code": "outside_room_pool"},
        "no_free_room": {"code": "unplaced", "severity": "error"},
        "shared_room_overflow": {"code": "trusted_lock_capacity", "event_ids": [1, 2], "params": {"shared": True}},
        "locked_room_blocked": {"code": "locked_ineligible"},
        "week_room_changes": {"code": "week_split"},
        "missing_enrolment": {"code": "missing_enrolment"},
        "same_lecture_twice": {"code": "input_conflict", "params": {"same_lecture": True}},
        "other": {"code": "timeout", "severity": "warning"},
    }
    assert {g.code for g in GROUPS} == set(cases) | {"board_vs_list"}
    for group, d in cases.items():
        assert classify(d) == [group], (group, d)
    both = {"code": "input_conflict", "constraint_kinds": ["no_cohort_overlap", "no_instructor_overlap"]}
    assert classify(both) == ["fixed_instructor_clash", "fixed_cohort_clash"]
    assert classify({"code": "partial"}) == [] and classify({"code": "unplaced_summary"}) == []
    assert classify({"code": "no_room", "params": {"reason": "capacity"}}) == ["no_free_room"]
    # review M6: merged / clipped joint lectures, overlaps outside the pool, info notes
    assert classify({"code": "joint_lecture_clipped", "severity": "warning"}) == ["locked_room_too_small"]
    assert classify({"code": "outside_pool_overlap", "severity": "warning"}) == ["locked_room_overlap"]
    assert classify({"code": "manual_lock", "severity": "info"}) == []
    assert all(len(g.sheet) <= 31 and not set(g.sheet) & set("[]:*?/\\") for g in GROUPS)
    acu = {
        "code": "trusted_lock_capacity",
        "event_ids": [5],
        "params": {"size": 122, "seats": 120, "room_codes": ["A207"]},
    }
    tr = message_tr(acu, TextContext(labels={5: "ACU 132"}))
    assert tr.startswith("ACU 132: beklenen 122 öğrenci, kilitli derslik A207 120 kişilik.")
    assert [g.code for g in GROUPS][:2] == ["no_free_room", "locked_room_blocked"]  # unplaced classes first


CTX = TextContext(
    labels={1: "MAT 112 §1", 786: "MAT 102 §1", 7: "ING 202", 9: "HEM 236"},
    times={1: (4, 7, 9), 786: (4, 8, 9)},
    instructors={1: "Elçim Elgün Kırımlı"},
    programs={"fizyoterapi": "Fizyoterapi"},
)


def test_planner_texts_use_names_days_and_clock_times_never_ids_or_keys() -> None:
    clash = {
        "code": "input_conflict",
        "severity": "warning",
        "event_ids": [1, 786],
        "message": "input conflict: MAT 112 §1 (#1) (day 4 P7-P9) and MAT 102 §1 (#786) ... 'INS:1 (Elçim)'",
        "params": {"keys": [["no_instructor_overlap", "INS:1"]], "noun": "instructor", "key": "INS:1", "day": 4},
    }
    t = planner_text(clash, CTX)
    assert t["tr"].startswith("MAT 112 §1 (Perşembe 13:30–15:50) ve MAT 102 §1 (Perşembe")
    assert (
        "aynı öğretim elemanı (Elçim Elgün Kırımlı)" in t["tr"]
        and "the same instructor (Elçim Elgün Kırımlı)" in t["en"]
    )
    for text in t.values():
        assert "#" not in text and "INS:" not in text and "P7" not in text and "no_instructor_overlap" not in text
    cohort = {**clash, "params": {"keys": [["no_cohort_overlap", "PROG:fizyoterapi:Y1"]]}}
    assert "aynı sınıf (Fizyoterapi 1. sınıf)" in planner_text(cohort, CTX)["tr"]

    busy = {
        "code": "unplaced",
        "event_ids": [1],
        "params": {
            "size": 180,
            "day": 4,
            "start": 7,
            "end": 9,
            "problem": "rooms_busy",
            "busy": [{"room": "A204", "capacity": 156, "day": 4, "start": 7, "end": 9, "holders": [7, 9]}],
            "free": [{"room": "A101", "day": 4, "start": 10, "end": 12}],
        },
    }
    t = planner_text(busy, CTX)
    assert t["tr"].startswith(
        "MAT 112 §1 (180 öğrenci, Perşembe 13:30–15:50) yerleşemedi: sığan derslikler o saatte dolu"
    )
    assert "A204 (156 kişilik: ING 202 + HEM 236)" in t["tr"] and "Free option: A101 Thursday" in t["en"]
    cap = {
        "code": "unplaced",
        "event_ids": [1],
        "params": {"size": 400, "problem": "capacity", "largest_capacity": 156},
    }
    assert "kapasite sorunu" in planner_text(cap, CTX)["tr"] and "a capacity problem" in planner_text(cap, CTX)["en"]


def test_every_solver_code_has_a_turkish_planner_text() -> None:
    """Codes that used to fall back to the English message now have TR / EN templates; none leaks ids,
    rule kinds or period numbers, and the Turkish text is not the English one."""
    cases = [
        {
            "code": "trusted_hint_capacity",
            "event_ids": [1],
            "params": {"size": 130, "seats": 92, "room_codes": ["A206"]},
        },
        {"code": "no_time", "event_ids": [1], "params": {"categories": {"cohort": 3, "day_window": 2}}},
        {"code": "bad_time", "event_ids": [1], "params": {"day": 7}},
        {"code": "bad_time", "event_ids": [1], "params": {"start": 17, "duration": 3}},
        {"code": "out_of_horizon", "event_ids": [1], "params": {"weeks": [15, 16]}},
        {"code": "core", "event_ids": [1, 786], "params": {}},
        {"code": "no_core", "event_ids": [], "params": {}},
        {"code": "relax_timeout", "event_ids": [], "params": {}},
        {"code": "timeout", "event_ids": [], "params": {}},
        {"code": "internal", "event_ids": [], "message": "solver error: KeyError: 3", "params": {}},
    ]
    for d in cases:
        t = planner_text({"severity": "warning", "message": "english fallback (#1)", **d}, CTX)
        assert t["tr"] != t["en"] and "english fallback" not in t["tr"], d["code"]
        for text in t.values():
            assert "#" not in text and "no_cohort_overlap" not in text and "day_window" not in text, (d, text)
    hint = planner_text(cases[0], CTX)
    assert hint["tr"].startswith("MAT 112 §1: beklenen 130 öğrenci, planlayıcının dersliği A206 92 kişilik.")
    assert "92 seats" in hint["en"] and "hint" in hint["en"]
    assert "sınıfın başka dersi var" in planner_text(cases[1], CTX)["tr"]
    assert "Pazar" in planner_text(cases[2], CTX)["tr"] and "Sunday" in planner_text(cases[2], CTX)["en"]
    assert "MAT 112 §1, MAT 102 §1" in planner_text(cases[5], CTX)["tr"]
    assert classify({"code": "trusted_hint_capacity"}) == ["locked_room_too_small"]


def test_capacity_pin_case_names_capacity_and_the_rooms_that_fit() -> None:
    """Usability M7: 137 students pinned to a 30-seat room said "not in the pinned room set ×9"."""
    from app.solver.cpsat import solve
    from app.solver.model import Assignment

    from tests.solver.conftest import event, make_input, room

    rooms = (*(room(i, f"A10{i}", 58) for i in range(1, 4)), room(8, "A204", 156), room(9, "B201", 30))
    e = event(
        1,
        size=137,
        weeks=(1,),
        day=3,
        start=2,
        label="ING 302",
        max_rooms=3,
        locked=Assignment(1, 3, 2, 3, (1, 2, 3), frozenset({1})),
        required_room_ids=(9,),
    )
    res = solve(make_input(rooms, (e,), weeks=(1,), trust_locked_rooms=True))
    d = next(x for x in res.diagnoses if x.code == "no_room")
    assert d.params["reason"] == "capacity" and d.params["pin_vs_lock"] is True and "capacity" in d.constraint_kinds
    assert d.params["excluded"] == {"pin": 3, "locked": 2}  # collapsed per category
    assert d.params["fitting_rooms"] == [{"room": "A204", "capacity": 156}]
    t = planner_text({"code": d.code, "event_ids": [1], "params": d.params}, TextContext(labels={1: "ING 302"}))
    assert t["tr"].startswith("ING 302: kapasite sorunu — 137 öğrenci var, sabitlenen derslik B201 30 kişilik.")
    assert "Sığan derslikler: A204 (156 kişilik)" in t["tr"] and "pinned to B201" in t["en"]
    locked = next(x for x in res.diagnoses if x.code == "locked_ineligible")
    assert "×3" in locked.message and locked.message.count("not in the pinned room set") == 1


def test_report_order_puts_unplaced_classes_first() -> None:
    diags = [
        {"code": "input_conflict", "severity": "warning"},
        {"code": "trusted_lock_capacity", "severity": "warning"},
        {"code": "unplaced", "severity": "error"},
        {"code": "partial", "severity": "warning"},
        {"code": "locked_overlap", "severity": "error"},
        {"code": "trusted_lock_capacity", "severity": "warning", "params": {"shared": True}},
        {"code": "no_room", "severity": "error"},
    ]
    assert [(d["code"], bool(d.get("params"))) for d in order_for_report(diags)] == [
        ("partial", False),
        ("unplaced", False),
        ("no_room", False),
        ("locked_overlap", False),
        ("trusted_lock_capacity", True),
        ("input_conflict", False),
        ("trusted_lock_capacity", False),
    ]


async def _seed() -> int:
    """Real-data style problems in a one-week term: a locked overlap (MAT 112 / HEM 236 in A204), an
    instructor clash (MAT 101 / MAT 205), a cohort clash (FIZ 101 / KIM 101), a locked room too small
    (ACU 132), a PC request without a PC room (BIL 101), a room outside the pool (LAB 1), a group nobody
    seats (BIG 500) and a lock on a room the grid blocks (ETK 1 in A101)."""
    async with get_session_factory()() as s:
        term = Term(code="T-ISSUES", name="t", week_count=1)
        s.add(term)
        await s.flush()
        rooms = {
            code: Room(code=code, display_name=code, capacity=cap, exam_capacity=cap // 2, tags=[], is_bookable=book)
            for code, cap, book in (
                ("A207", 120, True),
                ("A204", 156, True),
                ("A101", 58, True),
                ("A701", 0, False),
            )
        }
        s.add_all(rooms.values())
        prog = Program(name="Fizyoterapi", canonical_name="fizyoterapi")
        ins = Instructor(full_name="Dr. Ayşe Kaya", canonical_name="ayse kaya")
        s.add_all([prog, ins])
        await s.flush()
        s.add(
            Block(
                term_id=term.id,
                room_id=rooms["A101"].id,
                day=5,
                start_period=1,
                end_period=4,
                weeks=[1],
                label="ETKİNLİK",
            )
        )

        async def meeting(code, year, size, day, start, end, locked=None, teacher=None, tags=(), requested=None):  # type: ignore[no-untyped-def]
            course = Course(code=code.replace(" ", ""), display_code=code, name=f"{code} name")
            s.add(course)
            await s.flush()
            sec = Section(
                term_id=term.id,
                course_id=course.id,
                program_id=prog.id,
                class_year=year,
                class_years=[year],
                enrolment=size,
                source_key=code,
                label="1",
            )
            s.add(sec)
            await s.flush()
            if teacher is None:  # everyone else teaches alone
                teacher = Instructor(full_name=f"Dr. {code}", canonical_name=f"dr {code.lower()}")
                s.add(teacher)
                await s.flush()
            s.add(SectionInstructor(section_id=sec.id, instructor_id=teacher.id, role="PRIMARY"))
            mr = MeetingRequest(
                section_id=sec.id,
                day=day,
                days=[day],
                start_period=start,
                end_period=end,
                weeks=[1],
                status="LOCKED" if locked else "PARSED",
                definitive_room_ids=[rooms[locked].id] if locked else [],
                needs_room=True,
                requested_tags=list(tags),
                requested_room_ids=[rooms[requested].id] if requested else [],
                source_row_index=7,
            )
            s.add(mr)
            await s.flush()

        await meeting("ACU 132", 1, 122, 1, 3, 4, "A207")
        await meeting("MAT 101", 2, 40, 2, 3, 5, teacher=ins)
        await meeting("MAT 205", 3, 40, 2, 4, 5, teacher=ins)
        await meeting("FIZ 101", 4, 30, 3, 1, 2)
        await meeting("KIM 101", 4, 30, 3, 2, 3)
        await meeting("MAT 112", 5, 100, 4, 7, 9, "A204")
        await meeting("HEM 236", 6, 60, 4, 9, 10, "A204")
        await meeting("BIL 101", 7, 20, 1, 7, 8, tags=("PC",))
        await meeting("LAB 1", 8, 20, 4, 1, 2, "A701")
        await meeting("BIG 500", 9, 400, 2, 9, 10)
        await meeting("ETK 1", 10, 20, 5, 1, 2, "A101")
        await meeting("PHAR 240", 11, 130, 5, 6, 7, requested="A101")  # usability m1: 130 students, 58 seats
        # the published board (grid import run) has MAT 112 in A207, the planning list says A204
        board = ScheduleRun(
            term_id=term.id,
            kind="COURSE",
            horizon="TERM",
            status="FEASIBLE",
            params={"source": "GRID_IMPORT"},
            label="Grid import: board.xlsx",
        )
        s.add(board)
        await s.flush()
        s.add(
            Assignment(
                run_id=board.id,
                course_codes=["MAT112"],
                label="MAT 112",
                day=4,
                start_period=7,
                end_period=9,
                week=1,
                weeks=[1],
                room_ids=[rooms["A207"].id],
                origin="IMPORT",
            )
        )
        await s.commit()
        return term.id


async def test_data_issues_groups_with_classes_and_xlsx(client):
    h = await login(client)
    term_id = await _seed()
    r = await client.post(
        "/api/v1/runs", json={"term_id": term_id, "kind": "COURSE", "params": {"time_limit_s": 10}}, headers=h
    )
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] == "FEASIBLE_PARTIAL" and run["hard_score"] == 100, run["diagnosis"][:3]

    assert run["partial"] is True and run["placed"] < run["events_total"]
    codes = [d["code"] for d in run["diagnosis"]]
    assert codes[0] == "partial" and codes.index("input_conflict") > max(
        i for i, c in enumerate(codes) if c in ("unplaced", "no_room", "locked_ineligible")
    )  # unplaced classes before the input clashes
    assert all(d.get("text") and "#" not in d["text"]["tr"] and "INS:" not in d["text"]["en"] for d in run["diagnosis"])
    clash = next(d for d in run["diagnosis"] if d["code"] == "input_conflict" and "MAT 101" in d["text"]["tr"])
    assert "Dr. Ayşe Kaya" in clash["text"]["tr"] and "Salı" in clash["text"]["tr"]
    summary = (await client.get(f"/api/v1/runs/{run_id}/summary", headers=h)).json()
    assert (
        summary["partial"] is True
        and summary["placed"] == run["placed"]
        and summary["events_total"] == run["events_total"]
    )
    assert summary["headline"]["tr"] == f"{run['placed']}/{run['events_total']} ders yerleşti · hiçbir kural bozulmadı"

    rep = (await client.get(f"/api/v1/runs/{run_id}/data-issues", headers=h)).json()
    assert rep["run_id"] == run_id and rep["status"] == "FEASIBLE_PARTIAL"
    groups = {g["code"]: g for g in rep["groups"]}
    assert [g["code"] for g in rep["groups"]] == [g.code for g in GROUPS]

    def courses(code: str) -> set[str]:
        return {c["course_code"] for it in groups[code]["items"] for c in it["classes"]}

    assert courses("locked_room_overlap") == {"MAT 112", "HEM 236"}
    assert courses("fixed_instructor_clash") == {"MAT 101", "MAT 205"}
    assert courses("fixed_cohort_clash") >= {"FIZ 101", "KIM 101"}
    assert courses("locked_room_too_small") == {"ACU 132", "PHAR 240"}
    phar = next(it for it in groups["locked_room_too_small"]["items"] if it["code"] == "room_capacity")
    assert phar["message_tr"] == "PHAR 240 §1: A101 58 kişilik, bu derste 130 öğrenci var."
    assert phar["message"] == "PHAR 240 §1: A101 has 58 seats, this class has 130."
    assert courses("missing_tags") == {"BIL 101"}
    assert courses("rooms_outside_pool") == {"LAB 1"}
    assert "BIG 500" in courses("no_free_room")
    assert courses("locked_room_blocked") == {"ETK 1"}
    board = groups["board_vs_list"]["items"]
    assert [it["message_tr"] for it in board] == [
        "MAT 112 §1 (Perşembe 13:30–15:50): planlama listesinde A204, yayınlanan panoda A207 (1. hafta)."
    ]
    assert board[0]["classes"][0]["board_rooms"] == "A207"
    acu = next(it for it in groups["locked_room_too_small"]["items"] if it["code"] == "trusted_lock_capacity")
    assert acu["message_tr"].startswith("ACU 132 §1: beklenen 122 öğrenci") and "options" not in acu["params"]
    cls = acu["classes"][0]
    assert cls["program"] == "Fizyoterapi" and cls["planner_rooms"] == "A207" and cls["time"] and cls["source_row"] == 7
    mat = groups["fixed_instructor_clash"]["items"][0]["classes"][0]
    assert mat["instructors"] == "Dr. Ayşe Kaya" and mat["weeks"] == "1"
    big = next(it for it in groups["no_free_room"]["items"] if it["classes"][0]["course_code"] == "BIG 500")
    assert big["unplaced"] is True and big["severity"] == "error"
    assert rep["totals"]["by_group"]["locked_room_overlap"] == 1 and rep["totals"]["unplaced"] >= 3

    x = await client.get(f"/api/v1/runs/{run_id}/data-issues", params={"format": "xlsx"}, headers=h)
    assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "data-issues.xlsx" in x.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames[0] == "Özet - Summary" and len(wb.sheetnames) == 1 + len(GROUPS)
    ws = wb["Kilitli çakışma - Lock overlap"]
    header = [c.value for c in ws[4]]
    assert header[:3] == ["No / No", "Önem / Severity", "Sorun / Issue (TR)"] and "Ders / Course" in header
    body = [[c.value for c in row] for row in ws.iter_rows(min_row=5)]
    col = header.index("Ders / Course")
    assert {row[col] for row in body} == {"MAT 112", "HEM 236"}
    summary = {row[1].value: row[2].value for row in wb["Özet - Summary"].iter_rows(min_row=2) if row[1].value}
    assert summary["Locked room overlaps"] == 1 and summary["Planned rooms too small"] == 2

    assert (await client.get("/api/v1/runs/999999/data-issues", headers=h)).status_code == 404
    assert (
        await client.get(f"/api/v1/runs/{run_id}/data-issues", params={"format": "pdf"}, headers=h)
    ).status_code == 422


async def test_shared_exam_room_overflow_is_a_prominent_data_issue(client):
    """Usability M8: two trusted planner locks seat 122 + 78 students in A207 (55 exam seats).  Trust
    (D1) keeps the plan; the overflow is its own group, in the run stats and in the summary."""
    import datetime as dt

    from app.models import ExamRequest

    h = await login(client)
    async with get_session_factory()() as s:
        term = Term(code="T-EXAM", name="t", week_count=1)
        s.add(term)
        await s.flush()
        a207 = Room(code="A207", display_name="A207", capacity=120, exam_capacity=55, tags=[], is_bookable=True)
        s.add(a207)
        await s.flush()
        for code, size, start, end in (("ACU 132", 122, 7, 8), ("ACU 310", 78, 6, 7)):
            s.add(
                ExamRequest(
                    term_id=term.id,
                    course_code=code,
                    enrolment=size,
                    date=dt.date(2026, 6, 2),
                    start_period=start,
                    end_period=end,
                    status="LOCKED",
                    definitive_room_ids=[a207.id],
                    needs_room=True,
                    requested_room_count=1,
                )
            )
        await s.commit()
        term_id = term.id
    r = await client.post(
        "/api/v1/runs", json={"term_id": term_id, "kind": "EXAM", "params": {"time_limit_s": 10}}, headers=h
    )
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["hard_score"] == 100 and run["status"] in {"OPTIMAL", "FEASIBLE"}, run["diagnosis"]
    rep = (await client.get(f"/api/v1/runs/{run_id}/data-issues", headers=h)).json()
    over = next(g for g in rep["groups"] if g["code"] == "shared_room_overflow")
    assert over["count"] == 1 and {c["course_code"] for c in over["items"][0]["classes"]} == {"ACU 132", "ACU 310"}
    assert over["items"][0]["message_tr"].startswith("Ortak sınav salonu taşıyor: A207 (55 sınav koltuğu) Salı")
    summary = (await client.get(f"/api/v1/runs/{run_id}/summary", headers=h)).json()
    assert (
        summary["shared_room_overflows"][0]["rooms"] == ["A207"] and summary["shared_room_overflows"][0]["size"] == 200
    )
    assert sorted(summary["shared_room_overflows"][0]["exams"]) == ["ACU 132", "ACU 310"]
