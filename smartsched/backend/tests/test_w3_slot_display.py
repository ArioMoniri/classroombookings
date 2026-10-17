"""Wave 3 W3-SLOT: how a slot is shown everywhere bookings appear is an administrator's decision
(``booking.slot_display.*`` in settings_service SPECS, written through PUT /settings by ADMIN only) and every signed-in
user reads it, sanitised, from the bookings config (``GET /bookings/context`` -> ``slot_display`` and the light
``GET /bookings/slot-display``)."""

from __future__ import annotations

from app.services import settings_service as ss

from tests.crbs_env import env  # noqa: F401

DEFAULTS = {
    "unit": "periods",
    "block_minutes": 30,
    "label": "both",
    "density": "comfortable",
    "default_view": "day",
    "day_start": None,
    "day_end": None,
    "hide_weekend": False,
    "hidden_periods": [],
    "min_length": 1,
}


def test_w3_slot_specs_are_registered_key_value_settings():
    keys = {k for k in ss.SPECS if k.startswith("booking.slot_display.")}
    assert keys == {f"booking.slot_display.{k}" for k in DEFAULTS}
    assert not any(ss.SPECS[k].is_secret for k in keys)
    assert ss.SPECS["booking.slot_display.hide_weekend"].kind == "bool"
    assert ss.SPECS["booking.slot_display.min_length"].kind == "int"
    assert ss.SPECS["booking.slot_display.block_minutes"].kind == "int"


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
    extra = {
        "booking.slot_display.unit": "blocks",
        "booking.slot_display.block_minutes": 15,
        "booking.slot_display.label": "time",
        "booking.slot_display.density": "compact",
        "booking.slot_display.default_view": "week",
        "booking.slot_display.day_start": "08:30",
        "booking.slot_display.day_end": "17:00",
        "booking.slot_display.hide_weekend": True,
        "booking.slot_display.hidden_periods": "P0, p18 ,P18",
        "booking.slot_display.min_length": 2,
    }
    r = await env.client.put("/api/v1/settings", json={"extra": extra}, headers=env.admin)
    assert r.status_code == 200, r.text
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got == {
        "unit": "blocks",
        "block_minutes": 15,
        "label": "time",
        "density": "compact",
        "default_view": "week",
        "day_start": "08:30",
        "day_end": "17:00",
        "hide_weekend": True,
        "hidden_periods": ["P0", "p18"],  # first spelling kept; surfaces match case-insensitively
        "min_length": 2,
    }
    # the admin settings view lists the keys too (they are SPECS, not hidden dotted rows)
    view = (await env.client.get("/api/v1/settings", headers=env.admin)).json()
    assert view["booking.slot_display.unit"] == "blocks"


async def test_w3_slot_teacher_cannot_write(env):  # noqa: F811
    _, teacher = await env.user("w3slot-t3@example.edu")
    r = await env.client.put(
        "/api/v1/settings", json={"extra": {"booking.slot_display.unit": "blocks"}}, headers=teacher
    )
    assert r.status_code == 403
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["unit"] == "periods"


async def test_w3_slot_garbage_falls_back_to_defaults(env):  # noqa: F811
    """PUT /settings stores ``extra`` as given; the read side never hands a surface a value it cannot draw."""
    _, teacher = await env.user("w3slot-t4@example.edu")
    extra = {
        "booking.slot_display.unit": "hours",
        "booking.slot_display.block_minutes": 45,
        "booking.slot_display.label": "<script>",
        "booking.slot_display.density": "huge",
        "booking.slot_display.default_view": "month",
        "booking.slot_display.day_start": "25:99",
        "booking.slot_display.day_end": "noon",
        "booking.slot_display.hidden_periods": "," * 3,
        "booking.slot_display.min_length": "lots",
    }
    assert (await env.client.put("/api/v1/settings", json={"extra": extra}, headers=env.admin)).status_code == 200
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got == DEFAULTS
    # out of range lengths are clamped to 1..8; a start after the end drops the window
    extra = {
        "booking.slot_display.min_length": 99,
        "booking.slot_display.day_start": "18:00",
        "booking.slot_display.day_end": "09:00",
    }
    await env.client.put("/api/v1/settings", json={"extra": extra}, headers=env.admin)
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["min_length"] == 8 and got["day_start"] is None and got["day_end"] is None
    # an empty value resets the key to its default
    await env.client.put("/api/v1/settings", json={"extra": {"booking.slot_display.min_length": ""}}, headers=env.admin)
    got = (await env.client.get("/api/v1/bookings/slot-display", headers=teacher)).json()
    assert got["min_length"] == 1
