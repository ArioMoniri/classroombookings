"""POST /runs/{id}/diagnoses/{idx}/apply on real Güz rows + suggestion parsing against real solver output."""

from __future__ import annotations

from dataclasses import asdict

from app.core.db import get_session_factory
from app.models import MeetingRequest, ScheduleRun, Section
from app.services.diagnosis_fixes import parse_option, structure_diagnosis
from app.solver import model as sm
from app.workers.queue import get_queue
from sqlalchemy import select

from tests.api_fixtures import login
from tests.test_api_runs import _import_guz


def _cpsat_available() -> bool:
    try:
        import app.solver.cpsat  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def test_parse_options_match_real_solver_strings():
    """Two fixed-time lectures need the only big room at the same time -> the solver's own suggestion
    strings ("use ...", "alternative periods ...", "release ...") are classified as applicable moves."""
    if not _cpsat_available():
        return
    from app.solver.cpsat import solve

    rooms = (sm.Room(1, "A101", 58, 30, "A", frozenset()), sm.Room(2, "A204", 156, 74, "A", frozenset()))
    common = dict(kind="course", duration=3, weeks=frozenset({3}), allowed_days=frozenset({1}))
    events = (
        # flexible inside P4-P7 (two options, so the static pigeonhole check does not fire) ...
        sm.Event(
            id=11, label="PSI 155", size=120, fixed_day=1, fixed_start=None, earliest_start=4, latest_end=7, **common
        ),  # type: ignore[arg-type]
        # ... while fixed-time lectures hold the only big room at P4-P6 and P7-P9
        sm.Event(id=12, label="PSİ 156 İleri", size=110, fixed_day=1, fixed_start=4, **common),  # type: ignore[arg-type]
        sm.Event(id=13, label="FİZ 111 §1", size=100, fixed_day=1, fixed_start=7, **common),  # type: ignore[arg-type]
    )
    res = solve(sm.SolverInput(rooms=rooms, events=events, constraints=(), weeks=(3,), time_limit_s=5, workers=1))
    assert res.status == "INFEASIBLE" and res.diagnoses
    structured = [structure_diagnosis(asdict(d), i) for i, d in enumerate(res.diagnoses)]
    options = [o for d in structured for o in d["suggestions"]]
    texts = [o["text"] for o in options]
    room_moves = [o for o in options if o["action"] in {"move", "release_room"} and o["applicable"]]
    assert room_moves and all(o["params"]["room_code"] == "A204" for o in room_moves), texts
    assert all(
        o["params"]["day"] == 1 and o["params"]["end_period"] - o["params"]["start_period"] == 2 for o in room_moves
    )
    labels = [lbl for d in structured for lbl in d["event_labels"]]
    assert any(lbl in {"PSI 155", "PSİ 156 İleri"} for lbl in labels), labels  # Turkish İ survives


def test_parse_option_shapes():
    diag = {"event_ids": [7], "message": "MAT 112 (#7) (size 60, 2 period(s), day 3 P5-P6) cannot be placed"}
    assert parse_option(0, "use B201 at day 3 P5-P6", diag).params == {
        "event_id": 7,
        "room_code": "B201",
        "day": 3,
        "start_period": 5,
        "end_period": 6,
    }
    alt = parse_option(1, "alternative periods on the same day: P8-P9 in C301, P10-P11 in C302", diag)
    assert alt.action == "move" and alt.applicable and (alt.params["day"], alt.params["start_period"]) == (3, 8)
    rel = parse_option(2, "release A204 (156) at day 3 P5-P6 held by PSI 155 (#12), FİZ 111 §1 (#14)", diag)
    assert rel.action == "release_room" and rel.params["holder_event_ids"] == [12, 14]
    assert parse_option(3, "unlock MAT 112 or FİZ 111", diag).action == "unlock"
    assert parse_option(4, "make the day_window rule soft or exempt this event", diag).params["kind"] == "day_window"
    assert (
        parse_option(5, "allow splitting across rooms (max_rooms > 1) or raise a room's capacity", diag).action
        == "split"
    )
    assert parse_option(5, "allow splitting (max_rooms>1)", diag, "COURSE").applicable is False  # courses never split
    manual = parse_option(6, "release the block", diag)
    assert manual.action == "manual" and not manual.applicable


async def _psi155(term_id: int) -> MeetingRequest:
    async with get_session_factory()() as s:
        q = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term_id, MeetingRequest.day == 1, MeetingRequest.start_period == 4)
        )
        for mr in (await s.execute(q)).scalars():
            sec = await s.get(Section, mr.section_id)
            assert sec is not None
            if sec.enrolment == 120 and mr.end_period == 6:
                return mr
    raise AssertionError("PSI 155 row not found")


async def test_apply_move_relax_and_errors_on_real_row(client):
    h = await login(client)
    term_id = await _import_guz()
    psi = await _psi155(term_id)
    diag = {
        "event_ids": [psi.id],
        "constraint_kinds": ["no_room_overlap"],
        "message": f"PSI 155 (#{psi.id}) (size 120, 3 period(s), day 1 P4-P6) cannot be placed: rooms that fit are busy",
        "suggestions": [
            "use A204 at day 1 P4-P6",
            "alternative periods on the same day: P7-P9 in A204, P10-P12 in A204",
            "release the block",
            "make the building_preference rule soft or exempt this event",
            "use Z999 at day 1 P4-P6",
        ],
        "severity": "error",
    }
    async with get_session_factory()() as s:
        run = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 3},
            status="INFEASIBLE",
            params={"solver": "stub"},
            diagnosis=[diag],
            stats={"progress": 100},
        )
        s.add(run)
        await s.commit()
        run_id = run.id

    shown = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()["diagnosis"][0]
    assert shown["event_labels"] == ["PSI 155"]
    assert [o["action"] for o in shown["suggestions"]] == ["move", "move", "manual", "relax", "move"]
    assert shown["suggestions"][2]["applicable"] is False

    # option 1: the alternative period -> MANUAL + locked assignment, no re-solve
    r = await client.post(
        f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 1, "re_solve": False}, headers=h
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "move" and out["child_run_id"] is None and "A 204" in out["message"]
    rows = (await client.get(f"/api/v1/runs/{run_id}/assignments", headers=h)).json()
    a = next(x for x in rows if x["meeting_request_id"] == psi.id)
    assert (a["day"], a["start_period"], a["end_period"], a["room_codes"]) == (1, 7, 9, ["A 204"])
    assert a["is_locked"] is True and a["origin"] == "MANUAL" and a["week_set"] == [3]
    assert a["course_name"] == "Felsefede Temel Kavramlar ve Sorunlar"

    # option 0 re-places the same event (replaces, never duplicates) and queues a child run
    r = await client.post(f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 0}, headers=h)
    assert r.status_code == 200 and r.json()["child_run_id"]
    child_id = r.json()["child_run_id"]
    await get_queue().wait_idle()
    child = (await client.get(f"/api/v1/runs/{child_id}", headers=h)).json()
    assert child["parent_run_id"] == run_id and child["status"] in {"FEASIBLE", "OPTIMAL", "INFEASIBLE", "FEASIBLE_PARTIAL"}
    rows = (await client.get(f"/api/v1/runs/{run_id}/assignments", headers=h)).json()
    assert [(x["start_period"], x["end_period"]) for x in rows if x["meeting_request_id"] == psi.id] == [(4, 6)]
    child_rows = (await client.get(f"/api/v1/runs/{child_id}/assignments", headers=h)).json()
    kept = [x for x in child_rows if x["meeting_request_id"] == psi.id]
    assert kept and kept[0]["room_codes"] == ["A 204"] and kept[0]["start_period"] == 4

    # unstructured / unknown room / no constraint row -> 422 with a reason
    r = await client.post(f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 2}, headers=h)
    assert r.status_code == 422 and "by hand" in r.json()["detail"]
    r = await client.post(f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 4}, headers=h)
    assert r.status_code == 422 and "Z999" in r.json()["detail"]
    r = await client.post(f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 3}, headers=h)
    assert r.status_code == 422 and "building_preference" in r.json()["detail"]
    assert (
        await client.post(f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 9}, headers=h)
    ).status_code == 422
    assert (
        await client.post(f"/api/v1/runs/{run_id}/diagnoses/5/apply", json={"option_index": 0}, headers=h)
    ).status_code == 404

    # with a hard term rule of that kind, "relax" makes it soft
    c = (
        await client.post(
            "/api/v1/constraints",
            json={
                "term_id": term_id,
                "kind": "building_preference",
                "params": {"building": "C"},
                "hardness": "hard",
                "nl_text": "Psikoloji C blokta",
            },
            headers=h,
        )
    ).json()
    r = await client.post(
        f"/api/v1/runs/{run_id}/diagnoses/0/apply", json={"option_index": 3, "re_solve": False}, headers=h
    )
    assert r.status_code == 200 and r.json()["constraint_id"] == c["id"]
    rules = (await client.get("/api/v1/constraints", params={"term_id": term_id}, headers=h)).json()
    assert next(x for x in rules if x["id"] == c["id"])["hardness"] == "soft"


async def test_apply_unlock_on_real_cpsat_diagnosis(client):
    """Güz week 3 with CP-SAT: the planner's locked rooms clash somewhere; the solver suggests
    "unlock A or B" and applying it resets the request to PARSED and queues a child run."""
    if not _cpsat_available():
        return
    h = await login(client)
    term_id = await _import_guz()
    r = await client.post(
        "/api/v1/runs",
        json={
            "term_id": term_id,
            "kind": "COURSE",
            "horizon": "WEEK",
            "horizon_params": {"week": 3},
            "params": {"solver": "cpsat", "time_limit_s": 20, "workers": 2},
        },
        headers=h,
    )
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] in {"INFEASIBLE", "FEASIBLE_PARTIAL", "FEASIBLE", "OPTIMAL"}
    assert run["stats"]["merged_joint_lectures"] > 20  # FIZ 111 §1 etc. listed once per programme
    if run["status"] not in {"INFEASIBLE", "FEASIBLE_PARTIAL"}:
        return
    found = [
        (d["index"], o["index"], d["event_ids"])
        for d in run["diagnosis"]
        for o in d["suggestions"]
        if o["action"] == "unlock" and o["applicable"]
    ]
    assert found, "expected at least one applicable unlock suggestion on the real Güz data"
    idx, opt, event_ids = found[0]
    r = await client.post(f"/api/v1/runs/{run_id}/diagnoses/{idx}/apply", json={"option_index": opt}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "unlock" and body["details"]["unlocked_request_ids"] and body["child_run_id"]
    m = (await client.get(f"/api/v1/requests/meetings/{body['details']['unlocked_request_ids'][0]}", headers=h)).json()
    assert m["status"] == "PARSED"
    await get_queue().wait_idle()
    child = (await client.get(f"/api/v1/runs/{body['child_run_id']}", headers=h)).json()
    assert child["parent_run_id"] == run_id and child["status"] in {"INFEASIBLE", "FEASIBLE_PARTIAL", "FEASIBLE", "OPTIMAL"}
    assert set(event_ids)  # the pair named by the diagnosis
