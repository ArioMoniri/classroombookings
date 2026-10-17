"""WG-02 checklist signals and the feature-hint registry (docs/design/v3/welcome-guide.md §4.3, §4.5, §6.2, §6.4).

* checklist items tick from the real rows of the action (a booking, a decision, an audit event), never from a client
  claim: ``item_done`` exists only for view-only items;
* hints go to people who can use the feature, once, only to accounts created before the feature's release, for 60
  days; ``hints_for_all`` overrides;
* deep links (``first_route``), kiosk / embed / public pages and maintenance mode never get an automatic surface;
* ``GET /welcome`` costs at most 6 SQL statements in the service.

Real Bahar 2026 data (``tests/crbs_env``): A 102 is free at P1 on Thursday 19 Feb 2026.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from app.core import db as dbmod
from app.models import User
from app.services import welcome as wsvc
from app.services import welcome_hints as hints
from app.services.bookings_perms import load_access
from sqlalchemy import event, update

from tests.crbs_env import env  # noqa: F401
from tests.test_wg_01_welcome import academician, ev, get, staff

THU = date(2026, 2, 19)
T0 = datetime(2026, 10, 19, 9, 0)
BEFORE = datetime(2026, 9, 1, 8, 0)  # an account of the spring term
AFTER = datetime(2026, 10, 18, 8, 0)  # created after the wave-3 release


@pytest.fixture
def clock(monkeypatch):  # type: ignore[no-untyped-def]
    now = {"t": T0}
    monkeypatch.setattr(wsvc, "_now", lambda: now["t"])
    return now


async def _created(uid: int, when: datetime) -> None:
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(User).where(User.id == uid).values(created_at=when))
        await s.commit()


def _items(body: dict) -> dict[str, bool]:  # type: ignore[type-arg]
    return {i["key"]: i["done"] for i in body["checklist"]["items"]}


async def test_wg_02_a_real_booking_ticks_first_booking_without_a_client_event(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    assert _items(await get(env, h))["first_booking"] is False
    r = await env.book(h, "A102", THU, "P1", notes="FZT 132 telafi dersi")
    assert r.status_code == 201, r.text
    body = await get(env, h)
    assert _items(body)["first_booking"] is True
    assert body["checklist"]["done"] == 1
    item = next(i for i in body["checklist"]["items"] if i["key"] == "first_booking")
    assert item["manual"] is False and item["href"] == "/reserve"
    # sticky: cancelling the booking does not un-tick the step the person already did
    bid = r.json()["id"] if "id" in r.json() else r.json()["bookings"][0]["id"]
    r = await env.client.post(f"/api/v1/bookings/{bid}/cancel", json={"reason": "Ders iptal"}, headers=h)
    assert r.status_code == 200, r.text
    assert _items(await get(env, h))["first_booking"] is True


async def test_wg_02_profile_channel_and_calendar_come_from_rows(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h = await academician(env)
    r = await env.client.put(
        "/api/v1/me/notification-preferences", json={"channels": {"email": True}}, headers=h
    )
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(User).where(User.id == uid).values(department_id=None, language="tr"))
        await s.commit()
    items = _items(await get(env, h))
    assert items["profile"] is False  # no department yet
    assert items["channel"] is True  # an explicit e-mail preference (the stored settings row) counts
    assert items["calendar"] is False


async def test_wg_02_staff_never_gets_admin_hints(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h, _rid = await staff(env)
    await _created(uid, BEFORE)
    await ev(env, h, "sheet", "completed")
    body = await get(env, h)
    keys = [x["key"] for x in body["hints"]]
    assert "hint.quick_reserve" in keys
    assert not any(k.startswith("hint.admin_") for k in keys)
    assert body["show"] == {"kind": "hint", "key": "hint.quick_reserve", "audiences": [], "updated": False}
    r = await env.client.post(
        "/api/v1/welcome/events", json={"guide_key": "hint.admin_ai", "event": "seen"}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_eligible"
    # "Anladım" once: gone on every device
    await ev(env, h, "hint.quick_reserve", "seen")
    body = await get(env, h)
    assert "hint.quick_reserve" not in [x["key"] for x in body["hints"]] and body["show"] is None


async def test_wg_02_admin_hints_for_an_old_admin_account(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        from sqlalchemy import select

        aid = (await s.execute(select(User.id).where(User.email == "admin@example.com"))).scalar_one()
    await _created(aid, BEFORE)
    await ev(env, env.admin, "sheet", "completed")
    body = await get(env, env.admin)
    keys = {x["key"] for x in body["hints"]}
    assert {"hint.admin_ai", "hint.admin_ops", "hint.admin_integrations"} <= keys
    ai = next(x for x in body["hints"] if x["key"] == "hint.admin_ai")
    assert ai["route"] == "/admin/ai" and ai["release"] == hints.WAVE3_RELEASE.isoformat()


async def test_wg_02_accounts_created_after_the_release_get_no_hint(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h, _rid = await staff(env)
    await _created(uid, AFTER)
    await ev(env, h, "sheet", "completed")
    body = await get(env, h)
    assert body["hints"] == [] and body["show"] is None
    # 60 days after the release no one gets it any more, even an old account
    await _created(uid, BEFORE)
    assert "hint.quick_reserve" in [x["key"] for x in (await get(env, h))["hints"]]
    clock["t"] = datetime.combine(hints.WAVE3_RELEASE, datetime.min.time()) + timedelta(days=61)
    assert (await get(env, h))["hints"] == []


async def test_wg_02_hints_for_all_overrides_once(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h, _rid = await staff(env)
    await _created(uid, AFTER)
    await ev(env, h, "sheet", "completed")
    r = await env.client.put("/api/v1/welcome/settings", json={"hints_for_all": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert "hint.quick_reserve" in [x["key"] for x in (await get(env, h))["hints"]]
    clock["t"] = T0 + timedelta(minutes=5)
    await ev(env, h, "hint.quick_reserve", "seen")
    assert (await get(env, h))["hints"] == []


async def test_wg_02_deep_links_kiosk_and_maintenance_get_nothing(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    _uid, h = await academician(env)
    body = await get(env, h, first_route="/approvals/123")
    assert body["show"] is None and body["suppressed"] == "deep_link"
    assert (await get(env, h, first_route="/bookings"))["show"]["kind"] == "sheet"  # the audience's home
    assert (await get(env, h, first_route="/reserve?date=2026-02-19"))["show"]["kind"] == "sheet"
    for params, why in (
        ({"kiosk": "1"}, "kiosk"),
        ({"embed": "1"}, "embed"),
        ({"first_route": "/public/rooms/A101"}, "excluded_route"),
        ({"first_route": "/setup"}, "excluded_route"),
        ({"first_route": "/welcome"}, "excluded_route"),
    ):
        body = await get(env, h, **params)
        assert body["show"] is None and body["suppressed"] == why, params
    r = await env.client.put("/api/v1/org/settings", json={"maintenance_mode": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    body = await get(env, h)
    assert body["show"] is None and body["suppressed"] == "maintenance"
    # the planner is exempt from maintenance (system.bypass_maintenance_mode): the guide may still show
    assert (await get(env, env.planner))["suppressed"] is None


async def test_wg_02_get_welcome_costs_at_most_six_statements(env, clock):  # type: ignore[no-untyped-def]  # noqa: F811
    uid, h = await academician(env)
    await env.book(h, "A102", THU, "P1")
    await get(env, h)  # first call stores the checklist snapshot
    engine = dbmod.get_engine().sync_engine
    statements: list[str] = []

    def count(_conn, _cursor, statement, *_a):  # type: ignore[no-untyped-def]
        statements.append(statement)

    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        assert user is not None
        access = await load_access(s, user)
        event.listen(engine, "before_cursor_execute", count)
        try:
            body = await wsvc.payload(s, user, access)
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert body["checklist"]["items"]
    assert len(statements) <= 6, statements
