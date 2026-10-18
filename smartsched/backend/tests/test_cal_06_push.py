"""CAL-06 push of classes into a calendar SmartSched creates ("SmartSched – Derslerim"), on the real Bahar 2026
import and mocked providers (``tests/cal_fakes``, httpx.MockTransport).

New connections ask Google for ``openid email calendar.app.created`` only; the first job creates the dedicated
calendar (Europe/Istanbul) and inserts one event per published class of the scope; a publish that moves one class
is one PATCH, a removed meeting one DELETE; a retried job never duplicates; a 429 backs off at least as long as
``Retry-After``; disconnect deletes the calendar in one call and revokes the grant; old broad grants keep working and
are flagged "Daha az izinle yeniden bağlan"; the nightly repair restores deleted events and re-creates a deleted
calendar once."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.core import db as dbmod
from app.models import Assignment, CalendarConnection, CalendarEventLink, CalendarSyncJob, ScheduleRun
from app.models.base import utcnow
from app.services import calendar_connectors, run_copy
from app.workers import integrations as worker
from sqlalchemy import delete, select, update

from tests.cal_fakes import APP_CREATED, FakeGoogleCal, FakeGraphCal
from tests.cal_support import link_instructor, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, client_factory, kvkk_sign_off

PANEL = "https://rezervasyon.uni.edu.tr"


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def configure(env, provider: str) -> None:  # noqa: F811
    body = {f"{provider}_client_id": f"{provider}-client-id-uni", f"{provider}_client_secret": f"{provider}-sec-uni",
            "public_url": PANEL}  # fmt: skip
    r = await env.client.put("/api/v1/calendar/admin/settings", json=body, headers=env.admin)
    assert r.status_code == 200, r.text


async def connect(env, fake, headers, provider: str, scopes: list[str] | None, code: str = "4/0Ae-cal") -> str:  # noqa: F811
    body: dict = {"return_path": "/profile/calendar"}
    if scopes is not None:
        body["scopes"] = scopes
    r = await env.client.post(f"/api/v1/calendar/connectors/{provider}/connect", json=body, headers=headers)
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    fake.codes[code] = q["code_challenge"]
    cb = await env.client.get(
        f"/api/v1/calendar/connectors/{provider}/callback", params={"code": code, "state": q["state"]}
    )
    assert cb.status_code == 302, cb.text
    await worker.wait_idle()
    return q["scope"] + "|" + cb.headers["location"]


async def conn_of(provider: str) -> CalendarConnection:
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(CalendarConnection).where(CalendarConnection.provider == provider))).scalar_one()


async def class_links(conn_id: int) -> list[CalendarEventLink]:
    async with dbmod.get_session_factory()() as s:
        q = select(CalendarEventLink).where(
            CalendarEventLink.connection_id == conn_id, CalendarEventLink.item_key.like("class:%")
        )
        return list((await s.execute(q)).scalars())


async def republish(env, p, *, move_week5: bool = False, drop_week6: bool = False) -> None:  # noqa: F811
    """A planner publishes a changed copy of the live run (run.activate)."""
    async with dbmod.get_session_factory()() as s:
        live = (
            await s.execute(
                select(ScheduleRun).where(
                    ScheduleRun.term_id == env.term_id, ScheduleRun.is_active.is_(True), ScheduleRun.kind == "COURSE"
                )
            )  # fmt: skip
        ).scalar_one()
        draft, _ = await run_copy.clone_as_draft(s, live, actor=None, reason="CAL-06 test")
        await s.commit()
        rows = {a.date: a for a in (await s.execute(select(Assignment).where(
            Assignment.run_id == draft.id, Assignment.label == "PSY 262"))).scalars()}  # fmt: skip
        if move_week5 and date(2026, 3, 2) in rows:  # a later copy of the moved run keeps the move
            await s.execute(update(Assignment).where(Assignment.id == rows[date(2026, 3, 2)].id).values(
                date=date(2026, 3, 3), day=2, start_period=3, end_period=5, room_ids=[env.rooms["A101"]]))  # fmt: skip
        if drop_week6:
            await s.execute(delete(Assignment).where(Assignment.id == rows[date(2026, 3, 9)].id))
        await s.commit()
        draft_id = draft.id
    r = await env.client.post(f"/api/v1/runs/{draft_id}/activate",
                              json={"confirm_forced_breaks": True, "confirm_scope_reduction": True}, headers=env.planner)  # fmt: skip
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    await worker.drain()  # whatever the after-commit kick has not reached yet (the drain is idempotent)
    await worker.wait_idle()


async def test_cal_06_google_publish_inserts_a_move_patches_a_removal_deletes_disconnect_drops_the_calendar(
    env,  # noqa: F811
    monkeypatch,
):
    fake = FakeGoogleCal(grant_scope=f"openid {APP_CREATED} https://www.googleapis.com/auth/userinfo.email")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    out = await connect(env, fake, ayse, "google", ["my_classes"])
    scope, location = out.split("|")
    assert scope == f"openid email {APP_CREATED}"  # least privilege: no calendar.events, no calendarList
    assert location.endswith("calendar=connected&provider=google")
    conn = await conn_of("google")
    assert conn.owned_calendar and conn.export_scopes == ["my_classes"] and conn.account_verified == "email"
    # the dedicated calendar, then one insert per published class from a week ago to the end of the term
    assert list(fake.calendars.values()) == ["SmartSched – Derslerim"]
    cal_id = conn.calendar_id
    assert cal_id in fake.calendars and fake.calendar_zone[cal_id] == "Europe/Istanbul"
    links = await class_links(conn.id)
    inserts = fake.calls("POST", f"/calendars/{cal_id.replace('@', '%40')}/events")
    assert links and len(inserts) == len(links) == len([k for k in fake.events if k[0] == cal_id])
    psy = [e for (c, _), e in fake.events.items() if c == cal_id and e["summary"] == "PSY 262 · Şube 1"]
    assert len(psy) == 14  # weeks 2-15 (week 1 is more than 7 days back)
    week5 = next(e for e in psy if e["start"]["dateTime"] == "2026-03-02T13:30:00")
    assert week5["start"]["timeZone"] == "Europe/Istanbul" and week5["location"] == p.room.display_name
    assert week5["extendedProperties"]["private"]["smartsched"] == "1"
    assert "Ezgi" not in str(fake.events)  # no instructor names
    assert not fake.calls("GET", "calendarList")  # never reads the user's other calendars
    # the planner moves week 5 and publishes: one PATCH, no new event
    fake.requests.clear()
    await republish(env, p, move_week5=True)
    patches = fake.calls("PATCH")
    async with dbmod.get_session_factory()() as s:
        seen = [
            (j.kind, j.status, j.attempts, j.last_error) for j in (await s.execute(select(CalendarSyncJob))).scalars()
        ]
    assert len(patches) == 1 and not fake.calls("POST", "/events") and not fake.calls("DELETE"), seen
    moved = fake.body(patches[0])
    assert moved["start"]["dateTime"] == "2026-03-03T10:10:00" and moved["location"] == "A 101"
    # a removed meeting: one DELETE
    fake.requests.clear()
    await republish(env, p, move_week5=True, drop_week6=True)
    assert len(fake.calls("DELETE")) == 1 and not fake.calls("PATCH") and not fake.calls("POST", "/events")
    assert len(await class_links(conn.id)) == len(links) - 1
    # push_out: least privilege, no reconnect flag
    sub = (await env.client.get("/api/v1/calendar/subscriptions", headers=ayse)).json()["push"]
    assert sub[0]["least_privilege"] is True and sub[0]["reconnect_tr"] is None and sub[0]["owned_calendar"]
    # disconnect: the whole calendar goes in one call, then the grant is revoked
    fake.requests.clear()
    assert (await env.client.delete("/api/v1/calendar/connectors/google", headers=ayse)).status_code == 204
    await worker.wait_idle()
    assert len(fake.calls("DELETE", "/calendars/")) == 1 and not fake.calls("DELETE", "/events/")
    assert cal_id not in fake.calendars and fake.calls("POST", "oauth2.googleapis.com/revoke")
    assert await class_links(conn.id) == []


async def test_cal_06_retry_is_idempotent_and_429_honours_retry_after(env, monkeypatch):  # noqa: F811
    fake = FakeGoogleCal(grant_scope=f"openid {APP_CREATED}")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    boom = httpx.Response(503, json={"error": {"code": 503, "message": "Backend Error"}})
    await connect(env, fake, ayse, "google", ["my_classes"])
    conn = await conn_of("google")
    full = len(await class_links(conn.id))
    assert full > 3
    # a retried job after lost answers (the links are gone, the events exist): a 503 first, then the retry finishes
    # the job with every class once and no duplicate
    async with dbmod.get_session_factory()() as s:
        await s.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        await s.commit()
    first_event_count = len(fake.events)
    fake.fail_next.append(("POST", "/events", boom))
    async with dbmod.get_session_factory()() as s:
        await calendar_connectors.queue_classes(s)
        await s.commit()
    await worker.wait_idle()
    async with dbmod.get_session_factory()() as s:
        job = (await s.execute(select(CalendarSyncJob).where(CalendarSyncJob.kind == "classes").order_by(
            CalendarSyncJob.id.desc()))).scalars().first()  # fmt: skip
        assert job is not None and job.status == "PENDING" and job.attempts == 1
    await worker.drain(now=utcnow() + timedelta(hours=1))
    assert len(fake.events) == first_event_count  # inserts hit 409 on their deterministic ids -> PATCH, no duplicates
    assert len(await class_links(conn.id)) == full
    # 429 with Retry-After: 900 -> not before 15 minutes
    async with dbmod.get_session_factory()() as s:
        await s.execute(
            update(Assignment).where(Assignment.id == p.week5_assignment_id).values(start_period=10, end_period=12)
        )
        await s.execute(
            update(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id).values(fingerprint=None)
        )
        await s.commit()
    fake.fail_next.append(("PATCH", "/events/", httpx.Response(429, headers={"Retry-After": "900"},
                                                                 json={"error": {"code": 429, "message": "Rate Limit Exceeded"}})))  # fmt: skip
    before = utcnow()
    async with dbmod.get_session_factory()() as s:
        await calendar_connectors.queue_classes(s)
        await s.commit()
    await worker.wait_idle()
    async with dbmod.get_session_factory()() as s:
        job = (await s.execute(select(CalendarSyncJob).where(CalendarSyncJob.kind == "classes").order_by(
            CalendarSyncJob.id.desc()))).scalars().first()  # fmt: skip
        assert job is not None and job.status == "PENDING"
        assert job.next_attempt_at >= before + timedelta(seconds=899)


async def test_cal_06_microsoft_owned_calendar_and_transaction_ids(env, monkeypatch):  # noqa: F811
    fake = FakeGraphCal()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "microsoft")
    p = await psy262(env)
    uid, mehmet = await env.user("mehmet.kaya@uni.edu.tr", full_name="Mehmet Kaya")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, mehmet)
    await connect(env, fake, mehmet, "microsoft", ["my_classes", "my_bookings"])
    conn = await conn_of("microsoft")
    assert list(fake.owned.values()) == ["SmartSched – Derslerim"] and conn.calendar_id in fake.owned
    posts = fake.calls("POST", f"/me/calendars/{conn.calendar_id.replace('=', '%3D')}/events")
    assert posts and all(fake.body(r)["transactionId"].startswith("smartsched-") for r in posts)
    assert all(fake.body(r)["categories"] == ["SmartSched"] for r in posts)
    # a booking goes into the same owned calendar (my_bookings)
    await env.book(mehmet, "A101", date(2026, 2, 17), "P1")
    await worker.wait_idle()
    assert any(k[0] == conn.calendar_id and v.get("subject") == "A 101 – P1" for k, v in fake.events.items())
    n_events = len(fake.events)
    # the same job again (links lost): transactionId makes Graph return the existing events
    async with dbmod.get_session_factory()() as s:
        await s.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id,
                                                        CalendarEventLink.item_key.like("class:%")))  # fmt: skip
        await calendar_connectors.queue_classes(s)
        await s.commit()
    await worker.wait_idle()
    assert len(fake.events) == n_events


async def test_cal_06_legacy_grant_is_flagged_and_cannot_take_classes(env, monkeypatch):  # noqa: F811
    fake = FakeGoogleCal()  # the old broad grant (calendar.events + calendarList)
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    out = await connect(env, fake, ayse, "google", None)
    assert "calendar.events" in out.split("|")[0]  # the legacy connect is unchanged
    push = (await env.client.get("/api/v1/calendar/subscriptions", headers=ayse)).json()["push"]
    assert push[0]["least_privilege"] is False and push[0]["reconnect_tr"] == "Daha az izinle yeniden bağlan"
    assert push[0]["export_scopes"] == ["my_bookings"] and push[0]["owned_calendar"] is False
    r = await env.client.put("/api/v1/calendar/connectors/google/scopes", json={"scopes": ["my_classes"]}, headers=ayse)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reconnect_required"
    # connectors_out keeps its shape for W3-HUB
    item = (await env.client.get("/api/v1/calendar/connectors", headers=ayse)).json()[0]
    assert set(item) == {"provider", "label", "configured", "connected", "status", "account_email", "calendar_id",
                         "calendar_name", "last_synced_at", "last_error", "pending_jobs", "failed_jobs"}  # fmt: skip
    # reconnecting with fewer permissions replaces the legacy connection (its events removed with the old grant)
    fake.grant_scope = f"openid {APP_CREATED}"
    await connect(env, fake, ayse, "google", ["my_classes", "my_bookings"], code="4/0Ae-again")
    conn = await conn_of("google")
    assert conn.owned_calendar and conn.export_scopes == ["my_classes", "my_bookings"]
    push = (await env.client.get("/api/v1/calendar/subscriptions", headers=ayse)).json()["push"]
    assert push[0]["least_privilege"] is True


async def test_cal_06_nightly_repair_restores_events_and_recreates_the_calendar_once(env, monkeypatch):  # noqa: F811
    fake = FakeGoogleCal(grant_scope=f"openid {APP_CREATED}")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    await connect(env, fake, ayse, "google", ["my_classes"])
    conn = await conn_of("google")
    total = len(fake.events)
    # the user deletes one event and edits another by hand
    victim = next(iter(fake.events))
    del fake.events[victim]
    edited = next(iter(fake.events))
    fake.events[edited] = {**fake.events[edited], "summary": "elle değişti"}
    fake.updated[edited] = (utcnow() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert await worker.nightly_once() == 1
    await worker.wait_idle()
    assert len(fake.events) == total and fake.events[edited]["summary"] != "elle değişti"
    conn = await conn_of("google")
    assert conn.last_reconciled_at is not None
    # the user deletes the whole calendar: recreated once
    del fake.calendars[conn.calendar_id]
    await worker.nightly_once()
    await worker.wait_idle()
    conn2 = await conn_of("google")
    assert conn2.calendar_id and conn2.calendar_id != conn.calendar_id and conn2.calendar_recreated_at
    assert len([k for k in fake.events if k[0] == conn2.calendar_id]) == total
    # deleted again: the connection now asks the user
    del fake.calendars[conn2.calendar_id]
    await worker.nightly_once()
    await worker.wait_idle()
    conn3 = await conn_of("google")
    assert conn3.status == "CAL_DELETED" and "silinmiş" in (conn3.last_error or "")
    settings = (await env.client.get("/api/v1/calendar/admin/export-settings", headers=env.admin)).json()
    assert settings["status"]["nightly_reconcile"]["queued"] >= 0 and settings["status"]["needs_attention"] == 1
    assert worker.seconds_until_nightly(datetime(2026, 2, 16, 0, 0)) == 30 * 60  # 03:00 Istanbul -> 03:30
