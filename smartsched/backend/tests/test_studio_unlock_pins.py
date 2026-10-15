"""Recording bug: a pre-check "Unlock ..." fix is stored on the draft as a pin entry with only ``unlock: true``.
It is not a pin: the summary and the class list must not count or flag it as pinned. Also the summary's
English sentences use singular forms for a count of one ("for 1 week", not "for 1 weeks")."""

from __future__ import annotations

from app.services.studio import is_placement_pin, placement_pin_ids

from tests import studio_support
from tests.studio_support import meeting_id, room

bahar = studio_support.bahar


def test_placement_pin_helper():
    assert not is_placement_pin({"event_id": 1, "unlock": True})
    assert not is_placement_pin({"event_id": 1, "size": 40, "required_tags": ["PC"]})
    assert is_placement_pin({"event_id": 1, "room_ids": [3]})
    assert is_placement_pin({"event_id": 1, "day": 0})
    assert is_placement_pin({"event_id": 1, "start_period": 0})
    assert placement_pin_ids([{"event_id": 1, "unlock": True}, {"event_id": 2, "room_ids": [3], "unlock": True}]) == {2}


async def test_unlock_only_entry_is_not_pinned(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    phar = await meeting_id("PHAR 240", day=1, start=1)  # LOCKED in A 206
    a206 = await room("A206")
    # one unlock-only entry (the fix) plus one real pin on a different class
    rows = (await c.get(f"{url}/classes", params={"limit": 5}, headers=h)).json()["items"]
    other = next(r["id"] for r in rows if r["id"] != phar)
    body = {
        "version": 1,
        "horizon": "WEEK",
        "horizon_params": {"weeks": [3]},
        "pins": [{"event_id": phar, "unlock": True}, {"event_id": other, "room_ids": [a206.id]}],
    }
    r = await c.put(url, json=body, headers=h)
    assert r.status_code == 200, r.text
    assert {p["event_id"]: p for p in r.json()["pins"]}[phar] == {"event_id": phar, "unlock": True}

    s = (await c.get(f"{url}/summary", headers=h)).json()
    assert s["counts"]["pinned"] == 1 and s["counts"]["unlocked"] == 1
    assert "for 1 week." in s["sentence"]["en"] and "1 weeks" not in s["sentence"]["en"]
    assert "1 class is pinned" in s["human_summary"]["en"] and "for week 3." in s["human_summary"]["en"]
    assert "1 ders sabitlendi" in s["human_summary"]["tr"]

    got = (await c.get(f"{url}/classes", params={"ids": f"{phar},{other}"}, headers=h)).json()
    by_id = {r["id"]: r for r in got["items"]}
    assert by_id[phar]["pinned"] is False and by_id[other]["pinned"] is True
    assert got["counts"]["pinned"] == 1
    pinned_only = (await c.get(f"{url}/classes", params={"pinned": "true"}, headers=h)).json()["items"]
    assert [r["id"] for r in pinned_only] == [other]
