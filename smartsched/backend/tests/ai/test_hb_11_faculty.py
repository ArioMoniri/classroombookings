"""HB-11 faculty AI quota managers (architecture doc §5.9): permission ``ai.usage_faculty`` with TR/EN labels, the
scope (``faculties[id].managers``, else the own department's faculty), RA-11 (another faculty's numbers are
refused), department-level views by default, per person only with ``show_people`` and then tokens only, the
allocation split (sum ≤ the faculty's), and the ``ai.faculty_allocation`` audit row."""

from __future__ import annotations

import pytest
from app.ai import gateway as gw
from app.core.db import get_session_factory
from app.models import AuditEvent, Faculty, User
from app.models.catalog import Program
from app.services import ai_usage as meter
from app.services import bookings_perms as perms
from sqlalchemy import select

from tests.api_fixtures import login

U = "/api/v1/ai/faculty/usage"
A = "/api/v1/ai/faculty/allocations"


@pytest.fixture(autouse=True)
def _reset():
    meter.reset_state()
    yield
    meter.reset_state()


async def _world(client) -> dict:
    h_admin = await login(client)
    async with get_session_factory()() as s:
        f1, f2 = (
            Faculty(name="Eczacılık Fakültesi", canonical_name="ecz-f"),
            Faculty(name="Tıp", canonical_name="tip-f"),
        )
        s.add_all([f1, f2])
        await s.flush()
        p1 = Program(name="Eczacılık", canonical_name="ecz-p", faculty_id=f1.id)
        p2 = Program(name="Farmakoloji", canonical_name="farm-p", faculty_id=f1.id)
        p3 = Program(name="Tıp", canonical_name="tip-p", faculty_id=f2.id)
        s.add_all([p1, p2, p3])
        await s.commit()
        ids = {"f1": f1.id, "f2": f2.id, "p1": p1.id, "p2": p2.id, "p3": p3.id}
    r = await client.post(
        "/api/v1/roles",
        json={"name": "Fakülte AI yöneticisi", "permissions": ["room.view", "ai.usage_faculty"]},
        headers=h_admin,
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    people = {}
    for key, email, dep, rid in (
        ("dekan", "dekan@uni.edu.tr", ids["p2"], role_id),
        ("other", "tipdekan@uni.edu.tr", ids["p3"], role_id),
        ("a", "ayse@uni.edu.tr", ids["p1"], None),
        ("b", "berk@uni.edu.tr", ids["p2"], None),
        ("c", "can@uni.edu.tr", ids["p3"], None),
    ):
        body = {"email": email, "password": "parola-1234", "firstname": key.title(), "lastname": "Test"}
        if rid:
            body["role_id"] = rid
        r = await client.post("/api/v1/users", json=body, headers=h_admin)
        assert r.status_code == 201, r.text
        async with get_session_factory()() as s:
            u = await s.get(User, r.json()["id"])
            u.department_id = dep
            await s.commit()
            people[key] = u.id
    for key, tokens, feature in (("a", 300, "chat"), ("b", 200, "helper"), ("c", 999, "chat")):
        await meter.record(user_id=people[key], feature=feature, provider="anthropic", model="m", outcome="ok",
                           input_tokens=tokens)  # fmt: skip
    return {**ids, **people, "admin": h_admin, "role_id": role_id}


async def _limits(w, client, **values):
    r = await client.put("/api/v1/ai/admin/limits", json=values, headers=w["admin"])
    assert r.status_code == 200, r.text


def test_permission_is_seeded_with_turkish_and_english_labels():
    from app.api.deps import PERMISSION_TR

    assert "ai.usage_faculty" in perms.PERMISSION_NAMES
    text = perms.permission_text("ai.usage_faculty")
    assert text["tr"] == "Fakültemin yapay zekâ kullanımını görme ve paylaştırma" and text["en"]
    assert PERMISSION_TR["ai.usage_faculty"] == text["tr"]
    assert "ai.usage_faculty" in perms.ROLE_DEFAULTS["ADMIN"]["permissions"]
    assert "ai.usage_faculty" not in perms.ROLE_DEFAULTS["TEACHER"]["permissions"]


async def test_manager_sees_only_their_faculty_by_department(client):
    w = await _world(client)
    await _limits(w, client, faculties={str(w["f1"]): {"monthly_tokens": 2000, "managers": [w["dekan"]]}})
    h = await login(client, "dekan@uni.edu.tr", "parola-1234")
    r = await client.get(U, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["faculty"]["id"] == w["f1"] and [f["id"] for f in body["faculties"]] == [w["f1"]]
    assert body["totals"]["tokens"] == 500 and body["allocation"]["monthly_tokens"] == 2000
    deps = {d["name"]: d["tokens"] for d in body["by_department"]}
    assert deps == {"Eczacılık": 300, "Farmakoloji": 200}  # Tıp's 999 never shows
    assert {f["feature"]: f["tokens"] for f in body["by_feature"]} == {"chat": 300, "helper": 200}
    assert sum(d["tokens"] for d in body["trend"]) == 500
    assert body["show_people"] is False and "people" not in body
    # RA-11: another faculty's numbers
    r = await client.get(U, params={"faculty_id": w["f2"]}, headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "faculty_not_managed"


async def test_default_scope_is_the_own_departments_faculty(client):
    w = await _world(client)
    h = await login(client, "tipdekan@uni.edu.tr", "parola-1234")
    r = await client.get(U, headers=h)
    assert r.status_code == 200 and r.json()["faculty"]["id"] == w["f2"] and r.json()["totals"]["tokens"] == 999
    assert (await client.get(U, params={"faculty_id": w["f1"]}, headers=h)).status_code == 403


async def test_people_only_with_show_people_and_tokens_only(client):
    w = await _world(client)
    await _limits(
        w, client, faculties={str(w["f1"]): {"monthly_tokens": 2000, "managers": [w["dekan"]], "show_people": True}}
    )
    h = await login(client, "dekan@uni.edu.tr", "parola-1234")
    people = (await client.get(U, headers=h)).json()["people"]
    assert all(set(p) == {"label", "department", "tokens"} for p in people)
    assert sorted(p["tokens"] for p in people) == [200, 300]


async def test_without_the_permission_nothing_is_shown(client):
    await _world(client)
    h = await login(client, "ayse@uni.edu.tr", "parola-1234")
    assert (await client.get(U, headers=h)).status_code == 403


async def test_admin_sees_any_faculty(client):
    w = await _world(client)
    r = await client.get(U, params={"faculty_id": w["f2"]}, headers=w["admin"])
    assert r.status_code == 200 and r.json()["totals"]["tokens"] == 999


async def test_allocation_split_is_checked_and_audited(client):
    w = await _world(client)
    h = await login(client, "dekan@uni.edu.tr", "parola-1234")
    r = await client.put(
        A, json={"faculty_id": w["f1"], "departments": {str(w["p1"]): {"monthly_tokens": 1}}}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_faculty_allocation"
    await _limits(
        w,
        client,
        faculties={str(w["f1"]): {"monthly_tokens": 1000, "managers": [w["dekan"]]}},
        departments={str(w["p3"]): {"monthly_tokens": 50}},
    )
    too_much = {str(w["p1"]): {"monthly_tokens": 700}, str(w["p2"]): {"monthly_tokens": 400}}
    r = await client.put(A, json={"faculty_id": w["f1"], "departments": too_much}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "department_sum_exceeds_faculty"
    r = await client.put(
        A, json={"faculty_id": w["f1"], "departments": {str(w["p3"]): {"monthly_tokens": 1}}}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "department_not_in_faculty"
    r = await client.put(A, json={"faculty_id": w["f2"], "departments": {}}, headers=h)
    assert r.status_code == 403
    ok = {str(w["p1"]): {"monthly_tokens": 600}, str(w["p2"]): {"monthly_tokens": 400}}
    r = await client.put(A, json={"faculty_id": w["f1"], "departments": ok}, headers=h)
    assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        stored = await gw.get_limits(s)
        events = list(
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "ai.faculty_allocation"))).scalars()
        )
    assert stored["departments"][str(w["p1"])]["monthly_tokens"] == 600
    assert stored["departments"][str(w["p3"])]["monthly_tokens"] == 50  # another faculty's split is kept
    assert stored["faculties"][str(w["f1"])]["monthly_tokens"] == 1000  # the manager cannot change it
    assert len(events) == 1
    # the split is a ceiling the gateway enforces
    async with get_session_factory()() as s:
        with pytest.raises(meter.LimitRefusal) as exc:
            await meter.reserve(s, user_id=w["a"], est_tokens=400, est_cost=0)
    assert exc.value.code == "ai_department_limit_reached"
