"""BUG-02 (launch video, 2026-10-18): the audit log's before/after table showed raw ids (``room_id`` 14 -> 17). The
audit API now names the records behind the id fields in ``refs`` (``{field: {id: name}}``), for this viewer only:
rooms the viewer may see (``room.view``), people only where the booking screens already show them (the viewer
themself, ``audit.view``, or ``book_*.view_other_users`` on the room); periods, departments and terms by name.

Real Bahar 2026 data (``tests/crbs_env``): A 101 and A 106 are free at P1 on Monday 16 Feb 2026."""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)
AUDIT = "/api/v1/audit"


async def _event(env, headers, **params):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(AUDIT, params={"limit": 1, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


async def test_move_event_names_the_rooms_period_and_person(env):  # noqa: F811
    ayse_id, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    bid = (await env.book(ayse, "A101", MON, "P1")).json()["id"]
    r = await env.client.put(f"/api/v1/bookings/{bid}", json={"room_id": env.rooms["A106"]}, headers=ayse)
    assert r.status_code == 200, r.text
    a101, a106 = str(env.rooms["A101"]), str(env.rooms["A106"])
    for headers in (env.admin, ayse):  # the administrator and the owner both read names, not ids
        mv = await _event(env, headers, action="booking.move")
        assert mv["diff"]["room_id"] == [env.rooms["A101"], env.rooms["A106"]]
        assert mv["refs"]["room_id"] == {a101: "A 101", a106: "A 106"}
        assert mv["refs"]["user_id"] == {str(ayse_id): "Ayşe Yılmaz"}
        assert mv["refs"]["period_id"] == {str(env.periods["P1"]): "P1"}
    one = (await env.client.get(f"{AUDIT}/{mv['id']}", headers=ayse)).json()
    assert one["refs"]["room_id"][a106] == "A 106"


async def test_other_peoples_names_stay_hidden_without_view_other_users(env):  # noqa: F811
    mehmet_id, _ = await env.user("mehmet.oz@uni.edu.tr", firstname="Mehmet", lastname="Öz")
    ayse_id, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    r = await env.client.post(
        "/api/v1/bookings",
        json={"room_id": env.rooms["A101"], "date": MON.isoformat(), "period_id": env.periods["P1"], "user_id": mehmet_id},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    r = await env.client.put(f"/api/v1/bookings/{bid}", json={"user_id": ayse_id}, headers=env.admin)
    assert r.status_code == 200, r.text
    # the administrator (audit.view) reads both names
    ev = await _event(env, env.admin, entity_type="booking", entity_id=str(bid))
    assert ev["diff"]["user_id"] == [mehmet_id, ayse_id]
    assert ev["refs"]["user_id"] == {str(mehmet_id): "Mehmet Öz", str(ayse_id): "Ayşe Yılmaz"}
    # Ayşe (TEACHER: no book_single.view_other_users) sees the event of her booking, her own name, not Mehmet's
    mine = await _event(env, ayse, entity_type="booking", entity_id=str(bid))
    assert mine["id"] == ev["id"]
    assert mine["refs"]["user_id"] == {str(ayse_id): "Ayşe Yılmaz"}
    assert "Mehmet" not in str(mine["refs"])
