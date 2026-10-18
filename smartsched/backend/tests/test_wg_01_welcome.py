"""WG-01 welcome guide per role: audiences from permissions + the instructor link, the server's ``show`` decision
(T1 first sign-in, T2 "Sonra" 3 days x 2, T3 role-change delta, T4 content version; one per call), events and
restart (docs/design/v3/welcome-guide.md §5.9, §6).

Real Bahar 2026 data (``tests/crbs_env``): Ayşe is a TEACHER linked to a real instructor row of the imported
planning list (a name with a Turkish dotted capital İ); İsmail is staff (a custom role with ``room.view`` +
``book_single.create``, no instructor link). The welcome clock is the service's ``_now``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from app.core import db as dbmod
from app.models import Instructor, Role, User
from app.services import welcome as wsvc
from app.services.bookings_perms import ROLE_DEFAULTS
from sqlalchemy import select

from tests.api_fixtures import login
from tests.crbs_env import env  # noqa: F401

W = "/api/v1/welcome"
T0 = datetime(2026, 10, 19, 9, 0)


@pytest.fixture
def clock(monkeypatch):  # type: ignore[no-untyped-def]
    now = {"t": T0}
    monkeypatch.setattr(wsvc, "_now", lambda: now["t"])
    return now


async def academician(env):  # type: ignore[no-untyped-def]  # noqa: F811
    """Ayşe Yılmaz (TEACHER) linked to the first imported instructor whose name has an İ."""
    uid, h = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    async with dbmod.get_session_factory()() as s:
        ins = (
            (await s.execute(select(Instructor).where(Instructor.full_name.like("%İ%")).order_by(Instructor.id)))
            .scalars()
            .first()
        )
        assert ins is not None, "the Bahar planning list has an instructor with İ"
        ins.user_id = uid
        await s.commit()
    return uid, h


async def staff_role(env, perms: set[str] | None = None) -> int:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(
        "/api/v1/roles",
        json={"name": "İdari personel", "permissions": sorted(perms or {"room.view", "book_single.create"})},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def staff(env):  # type: ignore[no-untyped-def]  # noqa: F811
    rid = await staff_role(env)
    r = await env.client.post(
        "/api/v1/users",
        json={
            "email": "ismail.oz@uni.edu.tr",
            "role_id": rid,
            "password": "parola-1234",
            "firstname": "İsmail",
            "lastname": "Öz",
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"]), await login(env.client, "ismail.oz@uni.edu.tr", "parola-1234"), rid


async def ev(env, h, guide_key: str, event: str, **extra):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(f"{W}/events", json={"guide_key": guide_key, "event": event, **extra}, headers=h)
    assert r.status_code == 204, r.text


async def get(env, h, **params):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(W, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------------
# audiences (pure)
# --------------------------------------------------------------------------------------------------


def test_wg_01_audiences_follow_permissions_and_precedence() -> None:
    teacher = ROLE_DEFAULTS["TEACHER"]["permissions"]
    assert wsvc.audiences_for(teacher, instructor_linked=True) == ["academician"]
    assert wsvc.audiences_for(teacher, instructor_linked=False) == ["staff"]
    assert wsvc.audiences_for(ROLE_DEFAULTS["VIEWER"]["permissions"], instructor_linked=False) == ["viewer"]
    assert wsvc.audiences_for(ROLE_DEFAULTS["PLANNER"]["permissions"], instructor_linked=False) == ["planner"]
    admin = wsvc.audiences_for(ROLE_DEFAULTS["ADMIN"]["permissions"], instructor_linked=True)
    assert admin[0] == "admin" and "approver" in admin and "academician" not in admin
    # approver + department admin on top of staff; primary by precedence (dept_admin > approver > staff)
    custom = {"room.view", "book_single.create", "approvals.decide", "book_recur.create"}
    assert wsvc.audiences_for(custom, instructor_linked=False) == ["dept_admin", "approver", "staff"]
    # never role codes: the same permission set gives the same audiences whatever the role is called
    assert wsvc.audience_hash(["staff", "approver"]) == wsvc.audience_hash(["approver", "staff"])
    assert len(wsvc.audience_hash(["staff"])) == 16


# --------------------------------------------------------------------------------------------------
# T1 first sign-in
# --------------------------------------------------------------------------------------------------


async def test_wg_01_new_linked_teacher_is_academician_and_gets_the_sheet(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    body = await get(env, h)
    assert body["audiences"] == ["academician"] and body["primary"] == "academician"
    assert body["show"] == {"kind": "sheet", "key": "sheet", "audiences": ["academician"], "updated": False}
    assert [c["key"] for c in body["sheet"]["cards"]] == ["quick_reserve", "my_requests", "my_bookings", "calendar"]
    assert body["sheet"]["cards"][0]["href"] == "/reserve"
    assert body["name"] == "Ayşe"
    assert [s["anchor"] for s in body["tour"]["steps"]][:2] == ["nav-reserve", "reserve-when"]
    keys = [i["key"] for i in body["checklist"]["items"]]
    assert keys == ["profile", "first_booking", "channel", "calendar", "requests_seen"]
    assert body["checklist"]["total"] == 5 and body["checklist"]["done"] == 0
    assert body["enabled"] == {"sheet": True, "tour": True, "checklist": True, "hints": True}
    # shown once: after the client says it rendered the sheet, nothing is due any more
    await ev(env, h, "sheet", "shown")
    assert (await get(env, h))["show"] is None


# --------------------------------------------------------------------------------------------------
# T2 "Sonra": back after 3 days, at most twice, then checklist only
# --------------------------------------------------------------------------------------------------


async def test_wg_01_snooze_three_days_twice_then_never(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "snoozed")
    assert (await get(env, h))["show"] is None
    clock["t"] = T0 + timedelta(days=2, hours=23)
    assert (await get(env, h))["show"] is None
    clock["t"] = T0 + timedelta(days=3, minutes=1)
    assert (await get(env, h))["show"]["kind"] == "sheet"
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "snoozed")  # second snooze, 3 days from now (not from the first one)
    clock["t"] = T0 + timedelta(days=6)
    assert (await get(env, h))["show"] is None
    clock["t"] = T0 + timedelta(days=6, minutes=2)
    assert (await get(env, h))["show"]["kind"] == "sheet"
    await ev(env, h, "sheet", "snoozed")  # third snooze: never again
    clock["t"] = T0 + timedelta(days=60)
    body = await get(env, h)
    assert body["show"] is None
    assert body["sheet"]["state"] == "snoozed" and body["sheet"]["snooze_count"] == 3
    assert body["checklist"]["items"], "the checklist stays"


# --------------------------------------------------------------------------------------------------
# T3 role change: delta with only the new audience; revoking shows nothing and drops its items
# --------------------------------------------------------------------------------------------------


async def test_wg_01_granting_approvals_decide_shows_delta_and_revoking_drops_items(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h, rid = await staff(env)
    body = await get(env, h)
    assert body["audiences"] == ["staff"] and body["show"]["kind"] == "sheet"
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "completed")
    assert (await get(env, h))["show"] is None
    r = await env.client.put(
        f"/api/v1/roles/{rid}",
        json={"permissions": ["room.view", "book_single.create", "approvals.decide"]},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    body = await get(env, h)
    assert body["audiences"] == ["approver", "staff"]
    assert body["show"] == {"kind": "delta", "key": "sheet", "audiences": ["approver"], "updated": False}
    assert [c["key"] for c in body["sheet"]["cards"]] == ["approvals_inbox"]
    assert "first_decision" in [i["key"] for i in body["checklist"]["items"]]
    await ev(env, h, "sheet", "completed")
    assert (await get(env, h))["show"] is None
    # revoke: no sheet, the approver items are gone
    r = await env.client.put(
        f"/api/v1/roles/{rid}", json={"permissions": ["room.view", "book_single.create"]}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    body = await get(env, h)
    assert body["audiences"] == ["staff"] and body["show"] is None
    keys = [i["key"] for i in body["checklist"]["items"]]
    assert "first_decision" not in keys and "approver_channel" not in keys


# --------------------------------------------------------------------------------------------------
# state is per user on the server: two devices see the same thing
# --------------------------------------------------------------------------------------------------


async def test_wg_01_two_devices_share_the_state(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, phone = await academician(env)
    desktop = await login(env.client, "ayse.yilmaz@uni.edu.tr", "parola-1234")
    assert phone != desktop
    assert (await get(env, phone))["show"]["kind"] == "sheet"
    await ev(env, phone, "sheet", "shown")
    await ev(env, phone, "sheet", "snoozed")
    a, b = await get(env, phone), await get(env, desktop)
    assert a["show"] is None and b["show"] is None
    assert a["sheet"] == b["sheet"] and a["checklist"] == b["checklist"]
    await ev(env, desktop, "tour", "step", step=2)
    assert (await get(env, phone))["tour"]["step"] == 2


# --------------------------------------------------------------------------------------------------
# events: idempotent; unknown keys 422 in Turkish and English
# --------------------------------------------------------------------------------------------------


async def test_wg_01_events_are_idempotent_and_refuse_unknown_keys(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h = await academician(env)
    await ev(env, h, "sheet", "shown")
    await ev(env, h, "sheet", "snoozed")
    await ev(env, h, "sheet", "snoozed")  # a double tap / retried request
    assert (await get(env, h))["sheet"]["snooze_count"] == 1
    await ev(env, h, "checklist", "item_done", item="requests_seen")
    await ev(env, h, "checklist", "item_done", item="requests_seen")
    body = await get(env, h)
    done = {i["key"]: i["done"] for i in body["checklist"]["items"]}
    assert done["requests_seen"] is True and body["checklist"]["done"] == 1
    for payload, code in (
        ({"guide_key": "karşılama", "event": "shown"}, "unknown_guide_key"),
        ({"guide_key": "sheet", "event": "uçtu"}, "unknown_event"),
        ({"guide_key": "hint.yok_boyle", "event": "seen"}, "unknown_guide_key"),
        ({"guide_key": "checklist", "event": "item_done", "item": "nope"}, "unknown_item"),
        # a detectable item is ticked by the server from the real booking, never by the client
        ({"guide_key": "checklist", "event": "item_done", "item": "first_booking"}, "not_manual"),
    ):
        r = await env.client.post(f"{W}/events", json=payload, headers=h)
        assert r.status_code == 422, (payload, r.text)
        detail = r.json()["detail"]
        assert detail["code"] == code
        assert detail["message_tr"] and detail["message_en"] and detail["message_tr"] != detail["message_en"]
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        assert user is not None
        rows = await wsvc.dsr_rows(s, uid)
    assert {r["guide"] for r in rows} == {"sheet", "checklist"}


# --------------------------------------------------------------------------------------------------
# restart (Help › Turu yeniden başlat)
# --------------------------------------------------------------------------------------------------


async def test_wg_01_restart_reopens_the_sheet_and_tour(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    await ev(env, h, "sheet", "dismissed")
    await ev(env, h, "tour", "dismissed", step=2)
    assert (await get(env, h))["show"] is None
    r = await env.client.post(f"{W}/restart", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["show"]["kind"] == "sheet" and body["show"].get("reason") == "restart"
    assert body["sheet"]["state"] == "shown" and body["tour"]["state"] == "shown" and body["tour"]["step"] is None
    # a restart is the user's own ask: the next automatic load does not interrupt again
    assert (await get(env, h))["show"] is None


async def test_wg_01_signed_out_is_401(env):  # type: ignore[no-untyped-def]  # noqa: F811
    assert (await env.client.get(W)).status_code == 401
    assert (await env.client.post(f"{W}/events", json={"guide_key": "sheet", "event": "shown"})).status_code == 401


async def test_wg_01_custom_role_names_do_not_matter(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    """A custom role called "ADMIN-like" with only booking rights is staff: audiences never read role codes."""
    async with dbmod.get_session_factory()() as s:
        assert (await s.execute(select(Role).where(Role.name == "Yönetici gibi"))).scalar_one_or_none() is None
    r = await env.client.post(
        "/api/v1/roles",
        json={"name": "Yönetici gibi", "permissions": ["room.view", "book_single.create"]},
        headers=env.admin,
    )
    rid = r.json()["id"]
    r = await env.client.post(
        "/api/v1/users",
        json={"email": "nur.ilgin@uni.edu.tr", "role_id": rid, "password": "parola-1234"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    h = await login(env.client, "nur.ilgin@uni.edu.tr", "parola-1234")
    assert (await get(env, h))["audiences"] == ["staff"]
