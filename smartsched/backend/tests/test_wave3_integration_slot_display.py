"""Wave-3 integration (W3-SLOT follow-up): the public kiosk is not signed in, so it cannot read
``GET /bookings/slot-display``; its day payloads carry the label part of the administrator's slot display
(``label``, ``period_name``, ``time_format``: docs/design/v3/slot-display.md §5) so the kiosk labels match the
bookings surfaces. Items are never hidden by the visible-period window on a kiosk (a class in a hidden evening
period still happens in that room)."""

from __future__ import annotations

from app.core import throttle

from tests.crbs_env import env  # noqa: F401

PUB = "/api/v1/public/schedule"
ADMIN = "/api/v1/public-schedule/admin/settings"


async def test_public_day_payloads_carry_the_slot_labels(env):  # noqa: F811
    throttle.PUBLIC_PER_ADDRESS.reset()
    c = env.client
    assert (await c.put(ADMIN, json={"enabled": True}, headers=env.admin)).status_code == 200
    room = (await c.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})).json()
    assert room["slot_display"] == {"label": "both", "period_name": "schedule", "time_format": "range"}
    extra = {
        "booking.slot_display.label": "period",
        "booking.slot_display.period_name": "ordinal",
        "booking.slot_display.time_format": "start",
        "booking.slot_display.first_period": 2,
        "booking.slot_display.last_period": 4,
    }
    assert (await c.put("/api/v1/settings", json={"extra": extra}, headers=env.admin)).status_code == 200
    room = (await c.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})).json()
    assert room["slot_display"] == {"label": "period", "period_name": "ordinal", "time_format": "start"}
    assert any(x["end_period"] == 5 for x in room["items"])  # PHY 102 P3-P5 is still listed in full
    building = (await c.get(f"{PUB}/buildings/A", params={"date": "2026-02-18"})).json()
    assert building["slot_display"] == room["slot_display"]
