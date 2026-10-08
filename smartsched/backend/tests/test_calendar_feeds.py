"""Calendar subscription feeds (docs/product/calendar-sync-api.md §2) on the real Bahar 2026 import: per-user hashed
tokens, RFC 5545 output parsed with ``icalendar``, visibility (room ACL, private notes, user names), SEQUENCE /
LAST-MODIFIED / STATUS:CANCELLED, ETag + 304, the KVKK switch and rate limits."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

import icalendar
from app.core import db as dbmod
from app.models import CalendarFeedToken, User
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)  # Bahar week 3
NOTE = "Şube toplantısı – İç Hastalıkları; ölçme, değerlendirme\nİkinci satır"
IST = ZoneInfo("Europe/Istanbul")


def events(text: str) -> dict[str, icalendar.Event]:
    cal = icalendar.Calendar.from_ical(text)
    return {str(e["UID"]): e for e in cal.walk("VEVENT")}


async def new_token(env, headers, label: str | None = None) -> dict:  # noqa: F811
    r = await env.client.post("/api/v1/calendar/feeds/tokens", json={"label": label} if label else {}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def admin_settings(env, **values) -> None:  # noqa: F811
    r = await env.client.put("/api/v1/calendar/admin/settings", json=values, headers=env.admin)
    assert r.status_code == 200, r.text


async def test_mine_feed_is_valid_rfc5545_and_token_is_stored_hashed(env):  # noqa: F811
    uid, teacher = await env.user("takvim.abone@uni.edu.tr", displayname="Çağrı Öztürk")
    b = (await env.book(teacher, "A101", MON, "P1", notes=NOTE)).json()
    tok = await new_token(env, teacher, label="Google Takvim  ")
    assert tok["token"].startswith("sst_") and len(tok["token"]) >= 40
    assert tok["label"] == "Google Takvim" and tok["hint"] == tok["token"][-4:]
    assert tok["urls"]["mine"].endswith(f"/api/v1/calendar/feeds/{tok['token']}/mine.ics")
    assert tok["subscribe"]["webcal"].startswith("webcal://") or tok["subscribe"]["webcal"].startswith("/")
    async with dbmod.get_session_factory()() as s:
        row = (await s.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == uid))).scalar_one()
        assert row.token_hash == hashlib.sha256(tok["token"].encode()).hexdigest()
        user = await s.get(User, uid)
        assert tok["token"] not in str(vars(user)) and tok["token"] not in str(vars(row))

    r = await env.client.get(f"/api/v1/calendar/feeds/{tok['token']}/mine.ics")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/calendar")
    assert r.headers["cache-control"].startswith("private") and r.headers["etag"]
    assert r.headers["referrer-policy"] == "no-referrer"
    cal = icalendar.Calendar.from_ical(r.text)
    assert cal["VERSION"] == "2.0" and cal["PRODID"]
    tz = cal.walk("VTIMEZONE")
    assert [str(t["TZID"]) for t in tz] == ["Europe/Istanbul"]
    ev = events(r.text)[f"booking-{b['id']}@smartsched"]
    assert ev.decoded("DTSTART") == datetime(2026, 2, 16, 8, 30, tzinfo=IST)
    assert ev.decoded("DTEND") == datetime(2026, 2, 16, 9, 10, tzinfo=IST)
    assert str(ev["SUMMARY"]) == "A 101 – P1" and str(ev["LOCATION"]) == "A 101"
    assert NOTE in str(ev["DESCRIPTION"])  # escaped on the wire, identical after parsing (İ, ş, ;, newline)
    assert str(ev["STATUS"]) == "CONFIRMED" and int(ev["SEQUENCE"]) == 0
    assert ev.decoded("LAST-MODIFIED") and ev.decoded("DTSTAMP") == ev.decoded("LAST-MODIFIED")
    assert all(len(line.encode()) <= 75 for line in r.text.split("\r\n"))
    # the panel lists the link by hint, never the token again
    status = (await env.client.get("/api/v1/calendar/sync", headers=teacher)).json()
    assert status["enabled"] is True
    assert [t["hint"] for t in status["feeds"]["tokens"]] == [tok["hint"]]
    assert tok["token"] not in str(status)


async def test_etag_304_and_sequence_on_update_then_cancelled_with_grace(env):  # noqa: F811
    _, teacher = await env.user("dizi.numarasi@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P1", notes="İlk not")).json()
    tok = (await new_token(env, teacher))["token"]
    url = f"/api/v1/calendar/feeds/{tok}/mine.ics"
    first = await env.client.get(url)
    again = await env.client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    same = await env.client.get(url)
    assert same.text == first.text  # unchanged bookings: byte-identical feed (DTSTAMP is stable)
    uid = f"booking-{b['id']}@smartsched"
    r = await env.client.put(f"/api/v1/bookings/{b['id']}", json={"notes": "Güncellendi"}, headers=teacher)
    assert r.status_code == 200, r.text
    changed = await env.client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200 and changed.headers["etag"] != first.headers["etag"]
    ev = events(changed.text)[uid]
    assert int(ev["SEQUENCE"]) == 1 and "Güncellendi" in str(ev["DESCRIPTION"])
    assert ev.decoded("LAST-MODIFIED") >= events(first.text)[uid].decoded("LAST-MODIFIED")
    r = await env.client.post(f"/api/v1/bookings/{b['id']}/cancel", json={"reason": "İptal"}, headers=teacher)
    assert r.status_code == 200, r.text
    ev = events((await env.client.get(url)).text)[uid]
    assert str(ev["STATUS"]) == "CANCELLED" and int(ev["SEQUENCE"]) == 2
    await admin_settings(env, feed_cancelled_grace_days=0)
    assert uid not in events((await env.client.get(url)).text)


async def test_room_feed_hides_private_notes_and_user_names(env):  # noqa: F811
    c = env.client
    _, owner = await env.user("not.sahibi@uni.edu.tr", displayname="Zeynep Şahin")
    b = (await env.book(owner, "A101", MON, "P1", notes="Gizli not: sınav soruları")).json()
    role = (await c.post("/api/v1/roles", json={"name": "Takvim misafiri", "permissions": ["room.view"]}, headers=env.admin)).json()
    _, guest = await env.user("takvim.misafir@uni.edu.tr", role=None, role_id=role["id"])
    tok = (await new_token(env, guest))["token"]
    r = await c.get(f"/api/v1/calendar/feeds/{tok}/room/{env.rooms['A101']}.ics")
    assert r.status_code == 200, r.text
    ev = events(r.text)[f"booking-{b['id']}@smartsched"]
    assert "DESCRIPTION" not in ev or ("Gizli" not in str(ev["DESCRIPTION"]) and "Zeynep" not in str(ev["DESCRIPTION"]))
    assert "Gizli" not in r.text and "Zeynep" not in r.text
    # the owner sees both in the same room's feed
    own = (await new_token(env, owner))["token"]
    text = (await c.get(f"/api/v1/calendar/feeds/{own}/room/{env.rooms['A101']}.ics")).text
    assert "Gizli not" in str(events(text)[f"booking-{b['id']}@smartsched"]["DESCRIPTION"])
    # the legacy token link still serves the same feed
    legacy = await c.get(f"/api/v1/ics/{tok}/room/{env.rooms['A101']}.ics")
    assert legacy.status_code == 200 and "Gizli" not in legacy.text


async def test_room_acl_department_and_room_group_feeds(env):  # noqa: F811
    c = env.client
    deps = (await c.get("/api/v1/departments", params={"q": "PSİKOLOJİ"}, headers=env.admin)).json()
    psy = next(d for d in deps if d["name"].casefold().startswith("psikoloji"))
    role = (await c.post("/api/v1/roles", json={"name": "Dar görüş", "permissions": []}, headers=env.admin)).json()
    uid, guest = await env.user("dar.gorus@uni.edu.tr", role=None, role_id=role["id"])
    r = await c.post(
        "/api/v1/room-admin/acl",
        json={"entity_type": "room", "entity_id": env.rooms["A102"], "context_type": "user", "context_id": uid,
              "permissions": ["room.view"]},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    group = (
        await c.post("/api/v1/room-admin/groups", json={"name": "Ağ Grubu", "room_ids": [env.rooms["A101"], env.rooms["A102"]]}, headers=env.admin)
    ).json()
    in_a101 = (await env.book(env.planner, "A101", MON, "P1", department_id=psy["id"])).json()
    in_a102 = (await env.book(env.planner, "A102", MON, "P2", department_id=psy["id"])).json()
    assert in_a101["id"] and in_a102["id"]
    tok = (await new_token(env, guest))["token"]
    base = f"/api/v1/calendar/feeds/{tok}"
    assert (await c.get(f"{base}/room/{env.rooms['A101']}.ics")).status_code == 404  # no room.view on A 101
    assert (await c.get(f"{base}/room/{env.rooms['A102']}.ics")).status_code == 200
    assert (await c.get(f"{base}/room/999999.ics")).status_code == 404
    dep = await c.get(f"{base}/department/{psy['id']}.ics")
    assert dep.status_code == 200
    assert set(events(dep.text)) == {f"booking-{in_a102['id']}@smartsched"}
    grp = await c.get(f"{base}/room-group/{group['id']}.ics")
    assert grp.status_code == 200 and set(events(grp.text)) == {f"booking-{in_a102['id']}@smartsched"}
    assert (await c.get(f"{base}/department/999999.ics")).status_code == 404
    assert (await c.get(f"{base}/room-group/999999.ics")).status_code == 404
    opts = (await c.get("/api/v1/calendar/feeds/options", headers=guest)).json()
    assert [r["code"] for r in opts["rooms"]] == ["A102"]
    assert [g["id"] for g in opts["room_groups"]] == [group["id"]]
    assert any(d["id"] == psy["id"] for d in opts["departments"])
    # the planner (room.view on every room) sees both bookings of the department
    ptok = (await new_token(env, env.planner))["token"]
    both = (await c.get(f"/api/v1/calendar/feeds/{ptok}/department/{psy['id']}.ics")).text
    assert {f"booking-{in_a101['id']}@smartsched", f"booking-{in_a102['id']}@smartsched"} <= set(events(both))


async def test_revoke_reset_disabled_user_and_kvkk_switch(env):  # noqa: F811
    c = env.client
    uid, teacher = await env.user("iptal.link@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1")
    one = await new_token(env, teacher, "Outlook")
    two = await new_token(env, teacher, "Apple")
    assert (await c.get(f"/api/v1/calendar/feeds/{one['token']}/mine.ics")).status_code == 200
    assert (await c.delete(f"/api/v1/calendar/feeds/tokens/{one['id']}", headers=teacher)).status_code == 204
    assert (await c.get(f"/api/v1/calendar/feeds/{one['token']}/mine.ics")).status_code == 404
    assert (await c.get(f"/api/v1/calendar/feeds/{two['token']}/mine.ics")).status_code == 200
    # someone else cannot revoke my link
    _, other = await env.user("baskasi@uni.edu.tr")
    assert (await c.delete(f"/api/v1/calendar/feeds/tokens/{two['id']}", headers=other)).status_code == 404
    # KVKK switch off: every token feed is 404, including the older /ics links; back on: they work again
    await admin_settings(env, calendar_sync_enabled=False)
    assert (await c.get(f"/api/v1/calendar/feeds/{two['token']}/mine.ics")).status_code == 404
    assert (await c.get(f"/api/v1/ics/{two['token']}/user.ics")).status_code == 404
    assert (await c.get("/api/v1/calendar/sync", headers=teacher)).json()["enabled"] is False
    settings = (await c.get("/api/v1/calendar/admin/settings", headers=env.admin)).json()
    assert settings["calendar_sync_signoff"]["enabled"] is False and settings["calendar_sync_signoff"]["by"]
    await admin_settings(env, calendar_sync_enabled=True)
    assert (await c.get(f"/api/v1/calendar/feeds/{two['token']}/mine.ics")).status_code == 200
    # reset: every older link stops; the legacy rotate endpoint is the same reset
    fresh = (await c.post("/api/v1/calendar/feeds/reset", headers=teacher)).json()
    assert (await c.get(f"/api/v1/calendar/feeds/{two['token']}/mine.ics")).status_code == 404
    assert (await c.get(f"/api/v1/calendar/feeds/{fresh['token']}/mine.ics")).status_code == 200
    legacy = (await c.post("/api/v1/bookings/feed/token", headers=teacher)).json()
    assert (await c.get(f"/api/v1/calendar/feeds/{fresh['token']}/mine.ics")).status_code == 404
    assert (await c.get(legacy["user_feed"])).status_code == 200
    # a disabled account's links stop working
    assert (await c.put(f"/api/v1/users/{uid}", json={"is_active": False}, headers=env.admin)).status_code == 200
    assert (await c.get(legacy["user_feed"])).status_code == 404


async def test_feed_rate_limit(env):  # noqa: F811
    _, teacher = await env.user("cok.sorgu@uni.edu.tr")
    tok = (await new_token(env, teacher))["token"]
    url = f"/api/v1/calendar/feeds/{tok}/mine.ics"
    codes = [(await env.client.get(url)).status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429
    r = await env.client.get(url)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    # unknown tokens are throttled per address too, never a 500
    assert (await env.client.get("/api/v1/calendar/feeds/sst_unknown_token_value_000000000000/mine.ics")).status_code == 404


async def test_admin_settings_require_setup_settings_and_mask_secrets(env):  # noqa: F811
    c = env.client
    _, teacher = await env.user("yetkisiz@uni.edu.tr")
    assert (await c.get("/api/v1/calendar/admin/settings", headers=teacher)).status_code == 403
    assert (await c.put("/api/v1/calendar/admin/settings", json={"webhooks_enabled": True}, headers=teacher)).status_code == 403
    r = await c.put(
        "/api/v1/calendar/admin/settings",
        json={"google_client_id": "  1234-abc.apps.googleusercontent.com ", "google_client_secret": "GOCSPX-gercek-gizli-deger",
              "public_url": "https://rezervasyon.uni.edu.tr/"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["google"]["client_id"] == "1234-abc.apps.googleusercontent.com"  # NBSP and spaces trimmed
    assert body["google"]["configured"] is True and body["microsoft"]["configured"] is False
    assert "gercek-gizli" not in r.text and body["google"]["client_secret"]["set"] is True
    assert body["public_url"] == "https://rezervasyon.uni.edu.tr"
    assert body["google"]["redirect_uri"] == "https://rezervasyon.uni.edu.tr/api/v1/calendar/connectors/google/callback"
    bad = await c.put("/api/v1/calendar/admin/settings", json={"public_url": "javascript:alert(1)"}, headers=env.admin)
    assert bad.status_code == 422
    tok = await new_token(env, teacher)
    assert tok["urls"]["mine"].startswith("https://rezervasyon.uni.edu.tr/api/v1/calendar/feeds/")
    assert tok["subscribe"]["webcal"].startswith("webcal://rezervasyon.uni.edu.tr/")
