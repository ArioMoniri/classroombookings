"""AS-03: season profiles. Draft -> activate -> a run shows ``weights_source`` ``profile:<key>@<version>``; editing an
active profile creates the next version as a draft; revert re-activates the parent; a weight outside 0..MAX_WEIGHT
gives 422 with ``message_tr``; planners draft, ADMIN approves (AS20-F09); audited ``season_profile.*``; admin period segments per term.

Real row: Bahar planning list row 120 (PTL 204, requested C 403, definitive C 501) in a term whose weeks are the 19
sheets of the Bahar 2026 weekly grid."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent, ScheduleRun
from app.services.seasons import BUILTIN_KEYS
from app.workers.queue import get_queue
from sqlalchemy import select

from tests.api_fixtures import login
from tests.as_support import add_grid_term, add_meeting, add_rooms, row_of

BAHAR_LECTURE = [{"season": "BAHAR", "period_kind": "LECTURE"}]


async def _seed(parsed_bahar_grid, parsed_bahar_list) -> int:
    async with get_session_factory()() as s:
        term = await add_grid_term(s, "2026-BAHAR", parsed_bahar_grid)
        rooms = await add_rooms(s, "C403", "C501")
        await add_meeting(s, term, row_of(parsed_bahar_list, 120), rooms)
        await s.commit()
        return term.id


async def _run(client, h, tid: int, **params) -> dict:
    body = {"term_id": tid, "kind": "COURSE", "horizon": "TERM", **({"params": params} if params else {})}
    r = await client.post("/api/v1/runs", json=body, headers=h)
    assert r.status_code == 202, r.text
    await get_queue().wait_idle()
    return (await client.get(f"/api/v1/runs/{r.json()['run_id']}", headers=h)).json()


async def _planner(client) -> dict[str, str]:
    from tests.crbs_support import make_user

    admin = await login(client)
    _uid, h = await make_user(client, admin, "planner@example.com", role="PLANNER")
    return h


async def test_as_03_draft_activate_run_edit_revert(client, stub_solver, parsed_bahar_grid, parsed_bahar_list):
    h = await login(client)
    tid = await _seed(parsed_bahar_grid, parsed_bahar_list)
    body = {
        "key": "bahar-ders",
        "name_tr": "Bahar – ders dönemi",
        "name_en": "Spring – lecture period",
        "applies_to": BAHAR_LECTURE,
        "solver_weights": {"room_preference": 4},
        "explanation": {"tr": "Oda isteği daha az önemli", "en": "Room wishes weigh less"},
    }
    r = await client.post("/api/v1/seasons/profiles", json=body, headers=h)
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert (v1["version"], v1["status"], v1["builtin"]) == (1, "draft", False)
    # a draft never applies
    run = await _run(client, h, tid)
    assert run["stats"]["weights_source"]["room_preference"] == "default"
    assert run["stats"]["profile"]["key"] == "standard" and run["stats"]["profile"]["builtin"] is True
    r = await client.post(f"/api/v1/seasons/profiles/{v1['id']}/activate", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["approved_by"]
    # edit the active v1 -> v2 draft; activate v2 -> v1 retired
    r = await client.put(
        f"/api/v1/seasons/profiles/{v1['id']}", json={"solver_weights": {"room_preference": 6}}, headers=h
    )
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert (v2["version"], v2["status"], v2["parent_id"]) == (2, "draft", v1["id"])
    r = await client.post(f"/api/v1/seasons/profiles/{v2['id']}/activate", headers=h)
    assert r.status_code == 200
    profiles = {p["id"]: p for p in (await client.get("/api/v1/seasons/profiles", headers=h)).json()["profiles"]}
    assert profiles[v1["id"]]["status"] == "retired" and profiles[v2["id"]]["status"] == "active"
    run = await _run(client, h, tid)
    assert run["stats"]["weights_source"]["room_preference"] == "profile:bahar-ders@2"
    assert run["stats"]["weights_effective"]["room_preference"] == 6
    assert run["stats"]["profile"]["key"] == "bahar-ders" and run["stats"]["profile"]["version"] == 2
    assert run["stats"]["season"] == {"key": "BAHAR", "period_kind": "LECTURE"}
    # run params still win; a run can switch the profile off
    run = await _run(client, h, tid, weights={"room_preference": 9})
    assert run["stats"]["weights_source"]["room_preference"] == "run"
    run = await _run(client, h, tid, season_profile="none")
    assert run["stats"]["profile"] is None and run["stats"]["weights_source"]["room_preference"] == "default"
    # editing active v2 makes v3 a draft; activating v3 then reverting re-activates v2
    r = await client.put(f"/api/v1/seasons/profiles/{v2['id']}", json={"peak_threshold_pct": 90}, headers=h)
    v3 = r.json()
    assert (v3["version"], v3["status"], v3["parent_id"]) == (3, "draft", v2["id"])
    assert v3["solver_weights"] == {"room_preference": 6}
    await client.post(f"/api/v1/seasons/profiles/{v3['id']}/activate", headers=h)
    r = await client.post(f"/api/v1/seasons/profiles/{v3['id']}/revert", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == v2["id"] and r.json()["status"] == "active"
    profiles = {p["id"]: p for p in (await client.get("/api/v1/seasons/profiles", headers=h)).json()["profiles"]}
    assert profiles[v3["id"]]["status"] == "retired"
    run = await _run(client, h, tid)
    assert run["stats"]["weights_source"]["room_preference"] == "profile:bahar-ders@2"
    # every step is audited
    async with get_session_factory()() as s:
        actions = [
            a
            for (a,) in (
                await s.execute(select(AuditEvent.action).where(AuditEvent.entity_type == "season_profile"))
            ).all()
        ]
    assert {
        "season_profile.create",
        "season_profile.update",
        "season_profile.activate",
        "season_profile.revert",
    } <= set(actions)


async def test_as_03_validation_and_builtins(client, parsed_bahar_grid, parsed_bahar_list):
    h = await login(client)
    r = await client.post(
        "/api/v1/seasons/profiles",
        json={
            "key": "kotu",
            "name_tr": "Kötü",
            "name_en": "Bad",
            "applies_to": BAHAR_LECTURE,
            "solver_weights": {"room_preference": 10_001},
        },
        headers=h,
    )
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "profile_invalid" and "room_preference" in d["message_tr"] and d["message_en"]
    r = await client.post(
        "/api/v1/seasons/profiles",
        json={
            "key": "kotu",
            "name_tr": "Kötü",
            "name_en": "Bad",
            "applies_to": [{"season": "KIS", "period_kind": "LECTURE"}],
        },
        headers=h,
    )
    assert r.status_code == 422 and "KIS" in r.json()["detail"]["message_tr"]
    r = await client.post(
        "/api/v1/seasons/profiles",
        json={
            "key": "kotu",
            "name_tr": "Kötü",
            "name_en": "Bad",
            "applies_to": BAHAR_LECTURE,
            "solver_weights": {"no_such_rule": 3},
        },
        headers=h,
    )
    assert r.status_code == 422 and "no_such_rule" in r.json()["detail"]["message_en"]
    # built-ins are listed, read-only and cannot be shadowed
    listed = (await client.get("/api/v1/seasons/profiles", headers=h)).json()
    assert {p["key"] for p in listed["profiles"] if p["builtin"]} == set(BUILTIN_KEYS)
    assert all(p["status"] == "active" and p["solver_weights"] == {} for p in listed["profiles"] if p["builtin"])
    r = await client.post(
        "/api/v1/seasons/profiles",
        json={"key": "standard", "name_tr": "S", "name_en": "S", "applies_to": BAHAR_LECTURE},
        headers=h,
    )
    assert r.status_code == 409
    assert listed["weight_keys"] and "room_preference" in listed["weight_keys"]


async def test_as_03_admin_only(client, parsed_bahar_grid, parsed_bahar_list):
    # AS20-F09 (FIX-G, owner's decision): planners draft, only admins approve; see tests/test_fix_g_2026_10_18.py
    hp = await _planner(client)
    r = await client.get("/api/v1/seasons/profiles", headers=hp)
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/seasons/profiles",
        json={"key": "x", "name_tr": "X", "name_en": "X", "applies_to": BAHAR_LECTURE},
        headers=hp,
    )
    assert r.status_code == 201
    r = await client.post(f"/api/v1/seasons/profiles/{r.json()['id']}/activate", headers=hp)
    assert r.status_code == 403


async def test_as_03_periods_and_segments(client, parsed_bahar_grid, parsed_bahar_list):
    h = await login(client)
    tid = await _seed(parsed_bahar_grid, parsed_bahar_list)
    r = await client.post(
        f"/api/v1/seasons/terms/{tid}/segments",
        json={
            "kind": "ADD_DROP",
            "week_from": 1,
            "week_to": 2,
            "label_tr": "Ekle-bırak: 1–2. hafta",
            "label_en": "Add/drop: weeks 1–2",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    seg = r.json()
    r = await client.post(
        f"/api/v1/seasons/terms/{tid}/segments",
        json={"kind": "MIDTERM", "week_from": 8, "label_tr": "Vize haftası", "label_en": "Midterm week"},
        headers=h,
    )
    assert r.status_code == 201
    out = (await client.get(f"/api/v1/seasons/terms/{tid}/periods", headers=h)).json()
    assert out["season"] == {"key": "BAHAR", "label": {"tr": "Bahar", "en": "Spring"}}
    kinds = [(p["kind"], p["week_from"], p["week_to"], p["source"]) for p in out["periods"]]
    assert ("ADD_DROP", 1, 2, "segment") in kinds and ("MIDTERM", 8, 8, "segment") in kinds
    assert ("EXAM", 17, 18, "week") in kinds
    assert out["periods"][0]["date_from"] == "2026-02-02"
    r = await client.post(
        f"/api/v1/seasons/terms/{tid}/segments",
        json={"kind": "PARTY", "week_from": 1, "label_tr": "x", "label_en": "x"},
        headers=h,
    )
    assert r.status_code == 422
    r = await client.delete(f"/api/v1/seasons/segments/{seg['id']}", headers=h)
    assert r.status_code == 204
    out = (await client.get(f"/api/v1/seasons/terms/{tid}/periods", headers=h)).json()
    assert not any(p["kind"] == "ADD_DROP" for p in out["periods"])


async def test_as_03_profile_for_exam_period_kind(engine, parsed_bahar_grid, parsed_bahar_list):
    """An exam run of the term resolves the (season, EXAM) profile; a course run the LECTURE one."""
    from app.services import seasons

    tid = await _seed(parsed_bahar_grid, parsed_bahar_list)
    async with get_session_factory()() as s:
        p = await seasons.create_profile(
            s,
            {
                "key": "final",
                "name_tr": "Final",
                "name_en": "Final",
                "applies_to": [{"season": "*", "period_kind": "EXAM"}],
                "solver_weights": {"exam_gap": 20},
            },
            actor=None,
        )
        await seasons.activate_profile(s, p.id, actor=None)
        exam = ScheduleRun(term_id=tid, kind="EXAM", horizon="TERM", params={})
        course = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        s.add_all([exam, course])
        await s.flush()
        ew = await seasons.effective_weights(s, exam)
        cw = await seasons.effective_weights(s, course)
    assert ew.period_kind == "EXAM" and ew.source["exam_gap"] == "profile:final@1" and ew.weights["exam_gap"] == 20
    assert cw.period_kind == "LECTURE" and cw.source["exam_gap"] == "default"
