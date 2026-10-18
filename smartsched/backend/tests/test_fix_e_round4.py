"""FIX-E (round 4, 2026-10-18): week navigation from a weekend (PER-F01), the default day/week on a day without
periods (HX12B-F01, PER-F11), past slots say "past" (PER-F10).

Fixture: Bahar 2026 weekly grid; the clock sits inside the term (see tests/crbs_env.py)."""

from __future__ import annotations

from datetime import datetime

from tests.api_fixtures import client  # noqa: F401
from tests.crbs_env import env  # noqa: F401
from tests.crbs_support import role_id


async def _weekdays_only(e) -> None:  # type: ignore[no-untyped-def]
    for pid in e.periods.values():
        await e.client.put(f"/api/v1/booking-admin/periods/{pid}", json={"days": [1, 2, 3, 4, 5]}, headers=e.admin)


async def test_per_f01_week_next_from_a_sunday_is_the_coming_week(env):  # noqa: F811
    await _weekdays_only(env)
    _, teacher = await env.user("pazar@uni.edu.tr")
    week = (
        await env.client.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": "2026-03-01", "room_id": env.rooms["A101"]},
            headers=teacher,
        )
    ).json()
    # Sunday 1 March shows Mon 23 – Fri 27 Feb; "Sonraki hafta" is Mon 2 March, not Mon 9 March
    assert week["dates"][0]["date"] == "2026-02-23"
    assert week["nav"]["next"] == "2026-03-02"
    assert week["nav"]["prev"] == "2026-02-16"


async def test_hx12b_f01_default_opens_on_the_next_teaching_day_on_a_weekend(env):  # noqa: F811
    await _weekdays_only(env)
    env.set_now(datetime(2026, 3, 1, 10, 0))  # Sunday
    _, teacher = await env.user("hafta-sonu@uni.edu.tr")
    day = (await env.client.get("/api/v1/bookings/grid", params={"display": "day"}, headers=teacher)).json()
    assert day["date"] == "2026-03-02"
    assert day["periods"], "the opening day has bookable periods"
    week = (
        await env.client.get(
            "/api/v1/bookings/grid", params={"display": "room", "room_id": env.rooms["A101"]}, headers=teacher
        )
    ).json()
    assert week["dates"][0]["date"] == "2026-03-02"
    # an explicit Sunday stays on Sunday (the page then says the day is closed and offers nav.next)
    sun = (
        await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": "2026-03-01"}, headers=teacher)
    ).json()
    assert sun["date"] == "2026-03-01" and sun["periods"] == [] and sun["nav"]["next"] == "2026-03-02"


async def test_per_f10_past_days_read_past_not_too_soon(env):  # noqa: F811
    env.set_now(datetime(2026, 3, 4, 10, 0))
    teacher_role = await role_id(env.client, env.admin, "TEACHER")
    await env.client.put(f"/api/v1/roles/{teacher_role}", json={"range_min": 1}, headers=env.admin)
    _, teacher = await env.user("gecmis@uni.edu.tr")
    grid = (
        await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": "2026-03-02"}, headers=teacher)
    ).json()
    reasons = {s["reason"] for s in grid["slots"] if s["status"] == "unavailable"}
    assert "range_min" not in reasons and "past" in reasons


async def test_hx12b_f02_dates_name_the_next_open_teaching_day(env):  # noqa: F811
    await _weekdays_only(env)
    env.set_now(datetime(2026, 3, 1, 10, 0))  # Sunday
    _, teacher = await env.user("bos-oda@uni.edu.tr")
    out = (await env.client.get("/api/v1/bookings/dates", headers=teacher)).json()
    assert out["today"] == "2026-03-01" and out["next_open"] == "2026-03-02"
    env.set_now(datetime(2026, 3, 2, 10, 0))  # Monday: today itself
    out = (await env.client.get("/api/v1/bookings/dates", headers=teacher)).json()
    assert out["next_open"] == "2026-03-02"


async def test_per_f03_approver_refusal_is_turkish_and_names_no_raw_key(env):  # noqa: F811
    r = await env.client.post(
        "/api/v1/users",
        json={"email": "onayci-degil@uni.edu.tr", "role": "TEACHER", "approves_for": [{"type": "all"}]},
        headers=env.admin,
    )
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "not_an_administrator"
    assert "approvals.decide" not in d["message_tr"]
    assert "Rezervasyon taleplerini onayla" in d["message_tr"] and "Roller" in d["message_tr"]


async def test_aux12_f03_session_names_the_browser_after_a_server_side_first_request(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """The token's first request came from the Next server (no browser UA): the row said "bilinmeyen tarayıcı,
    bilinmeyen cihaz" for ever. A later request with the browser's UA names it."""
    from app.services import sessions

    from tests.api_fixtures import login
    from tests.au_b_support import API, bearer, make_user, password_step

    sessions.forget()
    admin = await login(client)
    await make_user(client, admin, "cihaz.adi@uni.edu.tr")
    step = await password_step(client, "cihaz.adi@uni.edu.tr", **{"User-Agent": "node"})
    phone = bearer(step["access_token"])
    safari = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.6 Mobile/15E148 Safari/604.1"
    )
    assert (await client.get(f"{API}/auth/me", headers={**phone, "User-Agent": "node"})).status_code == 200
    sessions.forget()  # past the cache window
    assert (await client.get(f"{API}/auth/me", headers={**phone, "User-Agent": safari})).status_code == 200
    rows = (await client.get(f"{API}/auth/sessions", headers=phone)).json()
    assert next(x for x in rows if x["current"])["device"] == "Safari, iPhone"


async def test_cal10_f02_no_panel_address_no_link_channel(env):  # noqa: F811
    from tests.integrations_support import calendar_consent, kvkk_sign_off

    await kvkk_sign_off(env)
    await env.client.put("/api/v1/calendar/admin/settings", json={"public_url": ""}, headers=env.admin)
    _, ayse = await env.user("panel.adresi@uni.edu.tr")
    await calendar_consent(env.client, ayse)
    link = (await env.client.get("/api/v1/calendar/export/options", headers=ayse)).json()["channels"]["link"]
    assert link["available"] is False and link["reason"] == "no_public_url"
    assert "panel adresini" in link["message_tr"]
    await env.client.put(
        "/api/v1/calendar/admin/settings", json={"public_url": "https://rezervasyon.uni.edu.tr"}, headers=env.admin
    )
    link = (await env.client.get("/api/v1/calendar/export/options", headers=ayse)).json()["channels"]["link"]
    assert link["available"] is True and "reason" not in link
