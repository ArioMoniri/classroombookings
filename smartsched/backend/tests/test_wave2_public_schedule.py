"""V2 public read-only day view on the real Bahar 2026 board (``tests/crbs_env``; clock Monday 16 Feb 2026).

Board facts: on Wednesday 18 Feb 2026 A 204 holds PHY 102 at P3-P5 (the T1 finder test reads the same cell); the
imported board also has cells that are not course codes (HAZIRLIK blocks, instructors' names)."""

from __future__ import annotations

import json
from datetime import date

from app.core import db as dbmod
from app.core import throttle
from app.models import AuditEvent, Instructor, Setting, User
from app.services import public_schedule
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.wave2_support import free_rooms

PUB = "/api/v1/public/schedule"
ADMIN = "/api/v1/public-schedule/admin/settings"
ITEM_KEYS = {"kind", "start_period", "end_period", "start", "end", "label"}


async def _names() -> tuple[set[str], set[str]]:
    from app.importers import normalize as n

    async with dbmod.get_session_factory()() as s:
        people = {n.tr_casefold(i.full_name) for i in (await s.execute(select(Instructor))).scalars() if i.full_name}
        mails = {u.email.lower() for u in (await s.execute(select(User))).scalars() if u.email}
    return {p for p in people if len(p) >= 6}, mails


async def test_off_by_default_then_signed_off_and_minimal(env):  # noqa: F811
    throttle.PUBLIC_PER_ADDRESS.reset()
    c = env.client
    # off: every page is the same 404, nothing to enumerate
    off = await c.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})
    assert off.status_code == 404
    assert (await c.get(PUB)).status_code == 404
    # a stored "on" without an administrator's sign-off does not count (like calendar sync, M-18)
    async with dbmod.get_session_factory()() as s:
        s.add(Setting(key="public.schedule_enabled", value="1", is_secret=False))
        await s.commit()
    assert (await c.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})).status_code == 404
    assert (await c.put(ADMIN, json={"enabled": True}, headers=env.planner)).status_code == 403
    r = await c.put(ADMIN, json={"enabled": True}, headers=env.admin)
    assert r.status_code == 200 and r.json()["enabled"] is True, r.text
    sign = r.json()["signoff"]
    assert (
        isinstance(sign["by_user_id"], int)
        and sign["features"] == ["public_schedule"]
        and "KVKK" in sign["legal_basis"]
    )

    # a teacher's booking with a personal note in a free room on the same day
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    wed = date(2026, 2, 18)
    room = (await free_rooms(wed, 13, 13))[0]
    r = await env.book(ayse, room, wed, "P13", notes="Ayşe Hoca ile tez toplantısı")
    assert r.status_code == 201, r.text

    # room view: Turkish date and a lower-case, spaced code
    r = await c.get(f"{PUB}/rooms/a 204", params={"date": "18.02.2026"})
    assert r.status_code == 200, r.text
    day = r.json()
    assert day["room"] == {"code": "A204", "name": "A 204", "building": "A", "capacity": 156}
    phy = [x for x in day["items"] if x["label"]["tr"] == "PHY 102"]
    assert phy and phy[0]["start_period"] == 3 and phy[0]["end_period"] == 5 and phy[0]["start"] == "10:10"
    assert all(set(x) == ITEM_KEYS for x in day["items"])
    assert r.headers["cache-control"] == "public, max-age=60"
    r = await c.get(f"{PUB}/rooms/{room}", params={"date": "2026-02-18"})
    booked = [x for x in r.json()["items"] if x["kind"] == "booked"]
    assert booked == [
        {
            "kind": "booked",
            "start_period": 13,
            "end_period": 13,
            "start": "18:00",
            "end": "18:40",
            "label": {"tr": "Rezerve", "en": "Booked"},
        }
    ]

    # whole buildings: no personal names, notes, e-mails or ids anywhere (scanned against every known person)
    people, mails = await _names()
    from app.importers import normalize as n

    for b in ("A", "B", "C", "D"):
        r = await c.get(f"{PUB}/buildings/{b.lower()}", params={"date": "2026-02-18"})
        assert r.status_code == 200, r.text
        text = json.dumps(r.json(), ensure_ascii=False)
        folded = n.tr_casefold(text)
        assert not any(p in folded for p in people), [p for p in people if p in folded][:3]
        assert not any(m in text.lower() for m in mails)
        assert "@" not in text and "Ayşe" not in text and "tez toplantısı" not in text
        for rm in r.json()["rooms"]:
            assert set(rm) == {"code", "name", "building", "capacity", "items"}
            assert all(set(x) == ITEM_KEYS for x in rm["items"])
            for x in rm["items"]:
                assert x["kind"] in ("class", "reserved", "booked")
                if x["kind"] == "reserved":
                    assert x["label"]["tr"] in {"Hazırlık", "UZEM", "Etkinlik", "Sınav", "Ayrılmış"}
    # the index lists buildings and rooms only
    idx = (await c.get(PUB)).json()
    assert {b["code"] for b in idx["buildings"]} >= {"A", "B", "C"}

    # unknown room, unknown building, out-of-window date, garbage: the same 404 as "off"
    for path, params in (
        ("/rooms/Z999", {"date": "2026-02-18"}),
        ("/rooms/A204", {"date": "2027-02-18"}),
        ("/rooms/A204", {"date": "yarın"}),
        ("/buildings/Q", {"date": "2026-02-18"}),
    ):
        r = await c.get(PUB + path, params=params)
        assert r.status_code == 404 and r.json() == off.json(), path

    # bookings can be hidden altogether
    r = await c.put(ADMIN, json={"show_bookings": "hidden"}, headers=env.admin)
    assert r.status_code == 200 and r.json()["show_bookings"] == "hidden"
    r = await c.get(f"{PUB}/rooms/{room}", params={"date": "2026-02-18"})
    assert not [x for x in r.json()["items"] if x["kind"] == "booked"]
    assert (await c.put(ADMIN, json={"show_bookings": "names"}, headers=env.admin)).status_code == 422

    # switching off records a new sign-off and closes every page again
    r = await c.put(ADMIN, json={"enabled": False}, headers=env.admin)
    assert r.json()["enabled"] is False
    assert (await c.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})).status_code == 404
    async with dbmod.get_session_factory()() as s:
        evs = list(
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "public_schedule.settings"))).scalars()
        )
        assert [e.after["enabled"] for e in evs] == [True, True, False]


async def test_rate_limited_per_address(env):  # noqa: F811
    throttle.PUBLIC_PER_ADDRESS.reset()
    r = await env.client.put(ADMIN, json={"enabled": True}, headers=env.admin)
    assert r.status_code == 200
    codes = [
        (await env.client.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})).status_code
        for _ in range(throttle.PUBLIC_PER_ADDRESS.limit + 1)
    ]
    assert codes[:-1] == [200] * throttle.PUBLIC_PER_ADDRESS.limit and codes[-1] == 429
    r = await env.client.get(f"{PUB}/rooms/A204", params={"date": "2026-02-18"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    throttle.PUBLIC_PER_ADDRESS.reset()


def test_labels_keep_course_codes_only():
    assert public_schedule._class_label("HEM 334 / NRS 304") == {"tr": "HEM 334 / NRS 304", "en": "HEM 334 / NRS 304"}
    assert public_schedule._class_label("NAFİYE HOCA") == {"tr": "Ders", "en": "Class"}
    assert public_schedule._block_label("hazırlık") == {"tr": "Hazırlık", "en": "Preparatory school"}
    assert public_schedule._block_label("Adli Tıp Staj") == {"tr": "Ayrılmış", "en": "Reserved"}
