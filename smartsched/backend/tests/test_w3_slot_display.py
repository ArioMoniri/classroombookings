"""Wave 3 W3-SLOT: how a slot is shown everywhere bookings appear is an administrator's decision
(``booking.slot_display.*`` in settings_service SPECS, docs/design/v3/slot-display.md §3, written through PUT /settings
by ADMIN only) and every signed-in user reads it, sanitised, from the bookings config (``GET /bookings/context`` ->
``slot_display`` and the light ``GET /bookings/slot-display``)."""

from __future__ import annotations

from app.services import settings_service as ss

from tests.crbs_env import env  # noqa: F401

DEFAULTS = {
    "unit": "periods",
    "block_minutes": 30,
    "label": "both",
    "period_name": "schedule",
    "time_format": "range",
    "density": "standard",
    "first_period": 0,
    "last_period": 0,
    "hide_short": False,
    "hide_weekend": False,
    "default_view_desktop": None,  # the organisation's CRBS display type decides
    "default_view_phone": "free_slots",
    "min_length": 1,
    "quick_span": 1,
}


def _extra(**values: object) -> dict[str, object]:
    return {f"booking.slot_display.{k}": v for k, v in values.items()}


def test_w3_slot_specs_are_registered_key_value_settings():
    keys = {k for k in ss.SPECS if k.startswith("booking.slot_display.")}
    assert keys == {f"booking.slot_display.{k}" for k in DEFAULTS}
    assert not any(ss.SPECS[k].is_secret for k in keys)
    for name in ("hide_short", "hide_weekend"):
        assert ss.SPECS[f"booking.slot_display.{name}"].kind == "bool"
    for name in ("block_minutes", "first_period", "last_period", "min_length", "quick_span"):
        assert ss.SPECS[f"booking.slot_display.{name}"].kind == "int"


async def test_w3_slot_defaults_reach_every_signed_in_user(env):  # noqa: F811
    _, teacher = await env.user("w3slot-t@example.edu")
    light = await env.client.get("/api/v1/bookings/slot-display", headers=teacher)
    assert light.status_code == 200, light.text
    assert light.json() == DEFAULTS
    ctx = (await env.client.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["slot_display"] == DEFAULTS
    # signed-in only
    assert (await env.client.get("/api/v1/bookings/slot-display")).status_code == 401


async def test_w3_slot_admin_writes_and_everyone_reads(env):  # noqa: F811
    _, teacher = await env.user("w3slot-t2@example.edu")
    chosen = {
        "unit": "blocks",
        "block_minutes": 15,
        "label": "time",
        "period_name": "ordinal",
        "time_format": "start",
        "density": "compact",
        "first_period": 1,
        "last_period": 11,
        "hide_short": True,
        "hide_weekend": True,
        "default_view_desktop": "free_week",
        "default_view_phone": "quick",
        "min_length": 2,
        "quick_span": 3,
    }
    r = await env.client.put("/api/v1/settings", json={"extra": _extra(**chosen)}, headers=env.admin)
    assert r.status_code == 200, r.text
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got == chosen
    # the admin settings view lists the keys too (they are SPECS, not hidden dotted rows)
    view = (await env.client.get("/api/v1/settings", headers=env.admin)).json()
    assert view["booking.slot_display.unit"] == "blocks"


async def test_w3_slot_teacher_cannot_write(env):  # noqa: F811
    _, teacher = await env.user("w3slot-t3@example.edu")
    r = await env.client.put("/api/v1/settings", json={"extra": _extra(unit="blocks")}, headers=teacher)
    assert r.status_code == 403
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["unit"] == "periods"


async def test_w3_slot_garbage_falls_back_to_defaults(env):  # noqa: F811
    """The read side never hands a surface a value it cannot draw, even when a stored row is garbage (an older
    release, a hand-edited database): PUT /settings refuses such values (SD-13, test below), so they are written here
    straight through the settings service."""
    from app.core import db as dbmod

    _, teacher = await env.user("w3slot-t4@example.edu")
    garbage = _extra(
        unit="hours",
        block_minutes=45,
        label="<script>",
        period_name="roman",
        time_format="ticks",
        density="huge",
        first_period="lots",
        last_period=-3,
        default_view_desktop="month",
        default_view_phone="grid_day",  # never a multi-room grid on a phone (MOBILE M-08)
        min_length="lots",
        quick_span=0,
    )
    async with dbmod.get_session_factory()() as s:
        for key, value in garbage.items():
            await ss.set_value(s, key, value)
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got == DEFAULTS
    # lengths are clamped to 1..8 and quick_span is never below min_length; first > last shows every period
    async with dbmod.get_session_factory()() as s:
        for key, value in _extra(min_length=99, quick_span=2, first_period=12, last_period=3).items():
            await ss.set_value(s, key, value)
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["min_length"] == 8 and got["quick_span"] == 8
    assert got["first_period"] == 0 and got["last_period"] == 0
    # an empty value resets the key to its default
    await env.client.put("/api/v1/settings", json={"extra": _extra(min_length="", quick_span="")}, headers=env.admin)
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["min_length"] == 1 and got["quick_span"] == 1


async def test_w3_slot_put_refuses_values_a_surface_cannot_draw(env):  # noqa: F811
    """SD-13: PUT /settings with an unknown slot display value answers 422 with the field and a Turkish message, and
    stores nothing of that request."""
    bad = {
        "unit": "hours",
        "block_minutes": 45,
        "label": "<script>",
        "density": "huge",
        "first_period": "lots",
        "last_period": -3,
        "default_view_desktop": "month",
        "default_view_phone": "grid_day",
        "min_length": 99,
        "quick_span": 0,
        "hide_short": "maybe",
        "colour": "red",  # not a slot display key at all
    }
    for name, value in bad.items():
        r = await env.client.put(
            "/api/v1/settings",
            json={"extra": {**_extra(period_name="ordinal"), **_extra(**{name: value})}},
            headers=env.admin,
        )
        assert r.status_code == 422, (name, r.text)
        detail = r.json()["detail"]
        assert detail["code"] == "invalid_slot_display" and detail["field"] == f"booking.slot_display.{name}"
        assert detail["message_tr"] and detail["message_en"] and detail["message_tr"] != detail["message_en"]
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=env.admin)).json()
    assert got["period_name"] == "schedule"  # the valid key of a refused request was not stored either
    r = await env.client.put(
        "/api/v1/settings", json={"extra": _extra(first_period=5, last_period=2)}, headers=env.admin
    )
    assert r.status_code == 422 and r.json()["detail"]["field"] == "booking.slot_display.first_period"
    ok = _extra(
        unit="blocks", block_minutes=15, first_period=2, last_period=9, hide_short=True, min_length=2, quick_span=3
    )
    assert (await env.client.put("/api/v1/settings", json={"extra": ok}, headers=env.admin)).status_code == 200
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=env.admin)).json()
    assert (got["unit"], got["block_minutes"], got["first_period"], got["last_period"]) == ("blocks", 15, 2, 9)
    assert got["hide_short"] is True and (got["min_length"], got["quick_span"]) == (2, 3)
