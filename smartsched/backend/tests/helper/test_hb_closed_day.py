"""BUG-01 follow-up: the helper's ``create_booking`` card checks the closed weekday like ``POST /bookings``.

Real Bahar 2026 data (``tests/crbs_env``), the schedule set to Monday-Friday as on the stack. Sunday 22 Feb 2026 is
in Bahar week 3: the card is refused as 409 ``closed_day`` with the Turkish "… rezervasyona kapalı bir gün" text, not
as the generic ``calendar`` error."""

from __future__ import annotations

from datetime import date

from app.ai.helper.actions import registry as reg

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import card, personas
from tests.test_bug01_find_room_closed_day import _weekdays_only

SUN = date(2026, 2, 22)


async def test_helper_booking_on_a_closed_day_is_refused_as_closed_day(env) -> None:  # noqa: F811
    reg.RATE.reset()
    await _weekdays_only(env)
    t = (await personas(env))["teacher"]
    for args in ({"period_id": env.periods["P3"]}, {"start": "10:00"}):
        r = await card(env, t, "create_booking", room="A 102", date=SUN.isoformat(), **args)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "closed_day", d
        assert d["message_tr"] == "22.02.2026 Pazar rezervasyona kapalı bir gün"
        assert d["message_en"] == "22.02.2026 is a Sunday, closed for bookings"
        assert d["card"]["type"] in ("refusal", "error")
