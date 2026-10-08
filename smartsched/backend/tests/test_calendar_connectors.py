"""Google Calendar / Microsoft 365 push connectors end to end against mocked provider APIs
(``tests/integrations_support``: httpx.MockTransport with real-shaped answers) on the real Bahar 2026 import:
configured flags, PKCE + state, encrypted tokens, create / update / delete through the outbox and the
integrations worker, retries with backoff, token refresh, re-authorisation, calendar choice, disconnect and the
KVKK switch."""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core import db as dbmod
from app.core.security import decrypt_secret
from app.models import CalendarConnection, CalendarEventLink, CalendarSyncJob, OAuthState
from app.models.base import utcnow
from app.services import calendar_connectors
from app.workers import integrations as worker
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import FakeGoogle, FakeGraph, client_factory, google_error

MON = date(2026, 2, 16)
TUE = date(2026, 2, 17)
PANEL = "https://rezervasyon.uni.edu.tr"


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def configure(env, provider: str, **extra) -> None:  # noqa: F811
    body = {
        f"{provider}_client_id": f"{provider}-client-id-uni",
        f"{provider}_client_secret": f"{provider}-secret-uni",
        "public_url": PANEL,
        **extra,
    }
    r = await env.client.put("/api/v1/calendar/admin/settings", json=body, headers=env.admin)
    assert r.status_code == 200, r.text


async def connect(env, fake, headers, provider: str, code: str = "4/0AeanS0test-code") -> str:  # noqa: F811
    r = await env.client.post(
        f"/api/v1/calendar/connectors/{provider}/connect", json={"return_path": "/profile/calendar"}, headers=headers
    )
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert q["redirect_uri"] == f"{PANEL}/api/v1/calendar/connectors/{provider}/callback"
    assert q["response_type"] == "code" and q["client_id"] == f"{provider}-client-id-uni" and len(q["state"]) >= 32
    fake.codes[code] = q["code_challenge"]  # the provider remembers the challenge for this code
    cb = await env.client.get(
        f"/api/v1/calendar/connectors/{provider}/callback", params={"code": code, "state": q["state"]}
    )
    assert cb.status_code == 302, cb.text
    assert cb.headers["location"] == f"{PANEL}/profile/calendar?calendar=connected&provider={provider}"
    await worker.wait_idle()
    return q["state"]


async def connection(provider: str) -> CalendarConnection:
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(CalendarConnection).where(CalendarConnection.provider == provider))).scalar_one()


async def jobs() -> list[CalendarSyncJob]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(CalendarSyncJob).order_by(CalendarSyncJob.id))).scalars())


async def test_connectors_report_not_configured_until_the_admin_enters_a_client(env):  # noqa: F811
    _, teacher = await env.user("baglanti.yok@uni.edu.tr")
    out = (await env.client.get("/api/v1/calendar/connectors", headers=teacher)).json()
    assert [(c["provider"], c["configured"], c["connected"]) for c in out] == [
        ("google", False, False),
        ("microsoft", False, False),
    ]
    settings = (await env.client.get("/api/v1/calendar/admin/settings", headers=env.admin)).json()
    assert settings["google"]["client_id"] == "" and settings["microsoft"]["client_id"] == ""  # nothing shipped
    r = await env.client.post("/api/v1/calendar/connectors/google/connect", headers=teacher)
    assert r.status_code == 409
    assert (await env.client.post("/api/v1/calendar/connectors/yahoo/connect", headers=teacher)).status_code == 404
    # id + secret without a public URL is still not usable (the redirect URI must be absolute)
    await env.client.put(
        "/api/v1/calendar/admin/settings",
        json={"google_client_id": "x", "google_client_secret": "y"},
        headers=env.admin,
    )
    out = (await env.client.get("/api/v1/calendar/sync", headers=teacher)).json()["connectors"]
    assert out[0]["configured"] is False


async def test_google_connect_then_create_update_cancel_reach_the_calendar(env, monkeypatch):  # noqa: F811
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    uid, teacher = await env.user("ayse.yilmaz@uni.edu.tr", displayname="Ayşe Yılmaz")
    before = (await env.book(teacher, "A101", MON, "P1", notes="Bölüm toplantısı; İç denetim")).json()
    state = await connect(env, fake, teacher, "google")
    conn = await connection("google")
    assert conn.user_id == uid and conn.account_email == "ayse.yilmaz@uni.edu.tr" and conn.status == "ACTIVE"
    assert conn.access_token_enc and "ya29" not in conn.access_token_enc  # stored encrypted
    assert decrypt_secret(conn.refresh_token_enc or "") == "1//0gLkXtestRefreshTokenGoogle"
    async with dbmod.get_session_factory()() as s:
        assert (await s.execute(select(OAuthState))).first() is None  # single use
    # the full sync pushed the booking made before connecting
    eid = f"smartsched{conn.id}p{before['id']}"
    ev = fake.events[("primary", eid)]
    assert ev["summary"] == "A 101 – P1" and ev["location"] == "A 101"
    assert ev["start"] == {"dateTime": "2026-02-16T08:30:00", "timeZone": "Europe/Istanbul"}
    assert ev["end"] == {"dateTime": "2026-02-16T09:10:00", "timeZone": "Europe/Istanbul"}
    assert ev["description"] == "Bölüm toplantısı; İç denetim"
    assert ev["extendedProperties"]["private"]["smartsched_booking_id"] == str(before["id"])
    # a new booking -> created; an edit -> PUT on the same event; a cancel -> DELETE
    new = (await env.book(teacher, "A101", TUE, "P1")).json()
    await worker.wait_idle()
    assert ("primary", f"smartsched{conn.id}p{new['id']}") in fake.events
    r = await env.client.put(f"/api/v1/bookings/{new['id']}", json={"notes": "Şube değişti"}, headers=teacher)
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    assert fake.events[("primary", f"smartsched{conn.id}p{new['id']}")]["description"] == "Şube değişti"
    assert len(fake.calls("PUT", f"smartsched{conn.id}p{new['id']}")) == 1
    r = await env.client.post(f"/api/v1/bookings/{new['id']}/cancel", json={}, headers=teacher)
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    assert ("primary", f"smartsched{conn.id}p{new['id']}") not in fake.events
    async with dbmod.get_session_factory()() as s:
        links = list((await s.execute(select(CalendarEventLink))).scalars())
    assert [link.booking_id for link in links] == [before["id"]]
    assert {j.status for j in await jobs()} == {"DONE"}
    status = next(
        c
        for c in (await env.client.get("/api/v1/calendar/sync", headers=teacher)).json()["connectors"]
        if c["provider"] == "google"
    )
    assert status["connected"] and status["calendar_id"] == "primary" and status["last_synced_at"]
    assert status["pending_jobs"] == 0 and status["failed_jobs"] == 0
    # the state cannot be replayed
    again = await env.client.get("/api/v1/calendar/connectors/google/callback", params={"code": "x", "state": state})
    assert again.status_code == 302 and "reason=state" in again.headers["location"]
    # an admin can read the outbox
    log = (await env.client.get("/api/v1/calendar/admin/jobs", headers=env.admin)).json()
    assert log and {x["provider"] for x in log} == {"google"}
    assert (await env.client.get("/api/v1/calendar/admin/jobs", headers=teacher)).status_code == 403


async def test_google_choose_calendar_moves_events_and_duplicate_ids_are_idempotent(env, monkeypatch):  # noqa: F811
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    _, teacher = await env.user("takvim.secimi@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P1")).json()
    await connect(env, fake, teacher, "google")
    conn = await connection("google")
    cals = (await env.client.get("/api/v1/calendar/connectors/google/calendars", headers=teacher)).json()
    assert cals[1] == {
        "id": "c_8f1e2d@group.calendar.google.com",
        "name": "Derslik rezervasyonları",
        "primary": False,
        "can_write": True,
    }
    r = await env.client.put(
        "/api/v1/calendar/connectors/google",
        json={"calendar_id": cals[1]["id"], "calendar_name": "Derslik rezervasyonları"},
        headers=teacher,
    )
    assert r.status_code == 200 and r.json()["calendar_id"] == cals[1]["id"]
    await worker.wait_idle()
    eid = f"smartsched{conn.id}p{b['id']}"
    assert ("primary", eid) not in fake.events and (cals[1]["id"], eid) in fake.events
    # the external calendar already holds the id (an earlier lost answer): 409 -> overwrite, one event
    other = (await env.book(teacher, "A101", TUE, "P1")).json()
    fake.events[(cals[1]["id"], f"smartsched{conn.id}p{other['id']}")] = {"summary": "eski"}
    await worker.wait_idle()
    assert fake.events[(cals[1]["id"], f"smartsched{conn.id}p{other['id']}")]["summary"] == "A 101 – P1"


async def test_microsoft_refreshes_tokens_retries_with_backoff_and_needs_reauth(env, monkeypatch):  # noqa: F811
    fake = FakeGraph()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "microsoft", microsoft_tenant="uni.edu.tr")
    _, teacher = await env.user("mehmet.kaya@uni.edu.tr", displayname="Mehmet Kaya")
    await connect(env, fake, teacher, "microsoft")
    token_calls = fake.calls("POST", "/oauth2/v2.0/token")
    assert "/uni.edu.tr/oauth2/v2.0/token" in str(token_calls[0].url)
    assert fake.form(token_calls[0])["scope"] == "offline_access openid email User.Read Calendars.ReadWrite"
    conn = await connection("microsoft")
    assert conn.account_email == "mehmet.kaya@uni.edu.tr"  # mail is null: the UPN is used
    # Graph is down for the first attempt
    fake.fail_next.append(("POST", "/me/events", httpx_503()))
    b = (await env.book(teacher, "A101", MON, "P1", notes="Sınav")).json()
    await worker.wait_idle()
    [job] = [j for j in await jobs() if j.booking_id == b["id"]]
    assert job.status == "PENDING" and job.attempts == 1 and "503" in (job.last_error or "")
    assert timedelta(seconds=50) < job.next_attempt_at - utcnow() <= timedelta(seconds=61)
    assert await worker.drain(now=utcnow()) == 0  # not due yet
    assert await worker.drain(now=utcnow() + timedelta(minutes=2)) >= 1
    [job] = [j for j in await jobs() if j.booking_id == b["id"]]
    assert job.status == "DONE" and job.attempts == 2
    posts = fake.calls("POST", "/me/events")
    assert len(posts) == 2 and fake.body(posts[0])["transactionId"] == fake.body(posts[1])["transactionId"]
    assert posts[1].headers["prefer"] == 'IdType="ImmutableId"'  # ids survive a move to another folder
    body = fake.body(posts[1])
    assert body["start"] == {"dateTime": "2026-02-16T05:30:00", "timeZone": "UTC"}  # 08:30 Istanbul
    assert body["subject"] == "A 101 – P1" and body["body"]["content"] == "Sınav"
    # the 60 s token was refreshed before the API call (grant_type=refresh_token, same scopes)
    refreshes = [r for r in fake.calls("POST", "/oauth2/v2.0/token") if fake.form(r)["grant_type"] == "refresh_token"]
    assert refreshes and fake.form(refreshes[0])["refresh_token"].startswith("0.AXkA-refresh-")
    # the grant is revoked at Microsoft: the connection asks for a reconnect, jobs stop
    fake.refresh_ok = False
    fake.access_tokens.clear()
    r = await env.client.put(f"/api/v1/bookings/{b['id']}", json={"notes": "Sınav saati değişti"}, headers=teacher)
    assert r.status_code == 200
    await worker.wait_idle()
    conn = await connection("microsoft")
    assert conn.status == "REAUTH" and "AADSTS70000" in (conn.last_error or "")
    status = next(
        c
        for c in (await env.client.get("/api/v1/calendar/connectors", headers=teacher)).json()
        if c["provider"] == "microsoft"
    )
    assert status["status"] == "REAUTH" and status["failed_jobs"] == 1


def httpx_503():  # type: ignore[no-untyped-def]
    import httpx

    return httpx.Response(
        503, json={"error": {"code": "ServiceNotAvailable", "message": "The service is temporarily unavailable."}}
    )


async def test_disconnect_deletes_tokens_and_revokes_at_google(env, monkeypatch):  # noqa: F811
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    _, teacher = await env.user("ayrilan@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1")
    await connect(env, fake, teacher, "google")
    assert (await env.client.delete("/api/v1/calendar/connectors/google", headers=teacher)).status_code == 204
    await worker.wait_idle()
    async with dbmod.get_session_factory()() as s:
        assert (await s.execute(select(CalendarConnection))).first() is None
        assert (await s.execute(select(CalendarEventLink))).first() is None
    revoke = fake.calls("POST", "oauth2.googleapis.com/revoke")
    assert len(revoke) == 1 and fake.form(revoke[0])["token"] == "1//0gLkXtestRefreshTokenGoogle"
    assert (await env.client.delete("/api/v1/calendar/connectors/google", headers=teacher)).status_code == 404


async def test_callback_errors_and_kvkk_switch(env, monkeypatch):  # noqa: F811
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    _, teacher = await env.user("izin.vermedi@uni.edu.tr")
    url = (await env.client.post("/api/v1/calendar/connectors/google/connect", headers=teacher)).json()["authorize_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    denied = await env.client.get(
        "/api/v1/calendar/connectors/google/callback", params={"error": "access_denied", "state": state}
    )
    assert denied.headers["location"] == f"{PANEL}/profile?calendar=error&provider=google&reason=denied"
    url = (await env.client.post("/api/v1/calendar/connectors/google/connect", headers=teacher)).json()["authorize_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    bad = await env.client.get("/api/v1/calendar/connectors/google/callback", params={"code": "wrong", "state": state})
    assert "reason=exchange" in bad.headers["location"]  # the provider refused the code (PKCE mismatch)
    unknown = await env.client.get(
        "/api/v1/calendar/connectors/google/callback", params={"code": "x", "state": "forged"}
    )
    assert "reason=state" in unknown.headers["location"]
    bad_path = await env.client.post(
        "/api/v1/calendar/connectors/google/connect", json={"return_path": "https://evil.example"}, headers=teacher
    )
    assert bad_path.status_code == 422
    # connected, then the admin turns calendar sync off: no connect, nothing queued, queued jobs skipped
    await connect(env, fake, teacher, "google")
    await env.client.put("/api/v1/calendar/admin/settings", json={"calendar_sync_enabled": False}, headers=env.admin)
    assert (await env.client.post("/api/v1/calendar/connectors/google/connect", headers=teacher)).status_code == 403
    before = len(await jobs())
    await env.book(teacher, "A101", MON, "P1")
    await worker.wait_idle()
    assert len(await jobs()) == before and not fake.events
    async with dbmod.get_session_factory()() as s:
        conn = (await s.execute(select(CalendarConnection))).scalar_one()
        s.add(CalendarSyncJob(connection_id=conn.id, booking_id=None, kind="full", next_attempt_at=utcnow()))
        await s.commit()
    await worker.drain()
    assert (await jobs())[-1].status == "SKIPPED"
    # back on: the panel's resync pushes what was missed
    await env.client.put("/api/v1/calendar/admin/settings", json={"calendar_sync_enabled": True}, headers=env.admin)
    assert (await env.client.post("/api/v1/calendar/connectors/google/resync", headers=teacher)).json() == {"queued": 1}
    await worker.wait_idle()
    assert len(fake.events) == 1


async def test_a_booking_given_to_another_user_leaves_the_old_calendar(env, monkeypatch):  # noqa: F811
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    _, teacher = await env.user("eski.sahip@uni.edu.tr")
    other_id, _ = await env.user("yeni.sahip@uni.edu.tr")
    await connect(env, fake, teacher, "google")
    b = (await env.book(env.planner, "A101", MON, "P1", user_id=(await connection("google")).user_id)).json()
    await worker.wait_idle()
    assert len(fake.events) == 1
    r = await env.client.put(f"/api/v1/bookings/{b['id']}", json={"user_id": other_id}, headers=env.planner)
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    assert fake.events == {}
    # a provider error that is not retryable fails the job at once (no retry storm)
    fake.fail_next.append(
        ("POST", "/events", google_error(403, "forbidden", "You need to have writer access to this calendar."))
    )
    c = (await env.book(env.planner, "A101", TUE, "P1", user_id=(await connection("google")).user_id)).json()
    await worker.wait_idle()
    [job] = [j for j in await jobs() if j.booking_id == c["id"]]
    assert job.status == "FAILED" and job.attempts == 1 and "writer access" in (job.last_error or "")
