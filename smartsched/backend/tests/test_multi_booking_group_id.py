"""T-R1-13 (lane B2 finding): two submissions of one person must never share a ``group_id``.

``create_from_selection`` used to delete the ``multi_bookings`` row after converting it; SQLite then reused
the rowid for the next selection, so every submission carried ``multi_booking_id == 1`` and Taleplerim merged
them into one row. The row is now kept (slots dropped) and a consumed selection still answers 404.
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)


@pytest.mark.asyncio
async def test_two_submissions_get_distinct_group_ids(env):  # noqa: F811
    _, teacher = await env.user("grup@uni.edu.tr")
    c = env.client
    groups: list[int] = []
    for period in ("P1", "P3"):
        sel = await c.post(
            "/api/v1/bookings/multi",
            json={"slots": [{"date": MON.isoformat(), "period_id": env.periods[period], "room_id": env.rooms["A101"]}]},
            headers=teacher,
        )
        assert sel.status_code == 201, sel.text
        mb = sel.json()
        r = await c.post(f"/api/v1/bookings/multi/{mb['id']}/create", json={"type": "single"}, headers=teacher)
        assert r.status_code == 200, r.text
        created = r.json()["created"]
        assert len(created) == 1 and created[0]["group_id"] == mb["id"]
        groups.append(created[0]["group_id"])
        # consumed: not fetchable, not re-creatable
        assert (await c.get(f"/api/v1/bookings/multi/{mb['id']}", headers=teacher)).status_code == 404
        again = await c.post(f"/api/v1/bookings/multi/{mb['id']}/create", json={"type": "single"}, headers=teacher)
        assert again.status_code == 404
    assert len(set(groups)) == 2, groups
    mine = (await c.get("/api/v1/bookings/mine", headers=teacher)).json()
    assert len({b["group_id"] for b in mine}) == 2
