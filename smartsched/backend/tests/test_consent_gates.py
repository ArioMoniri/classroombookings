"""Consent gates (``consent-gates-2026-10-16``; ROADMAP "Backend asks batch 3 finished", agent launched) on the real
Bahar 2026 import (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00):

* item 1 -- with the institution's calendar-sync KVKK sign-off on, a calendar feed link (``POST
  /calendar/feeds/tokens``, ``/calendar/feeds/reset``, ``/bookings/feed/token``) and a push connection (``POST
  /calendar/connectors/{provider}/connect``) need the person's active ``calendar_sync`` consent: 409
  ``consent_required`` with TR/EN text naming the consent and Profil › Gizlilik. ``kvkk.require_consent`` is the
  same gate for any future upload that stores a person's photo (``photo``);
* item 2 -- a KVKK erasure disconnects every push calendar through ``calendar_connectors.disconnect`` (the pushed
  events are removed and the grant revoked at the provider) before the rows go; a provider failure is recorded in
  the erasure result and never blocks the erasure;
* item 3 -- ``kvkk.ai_personal_default`` = ``included`` (default: only an explicit withdrawal keeps a person out of
  AI requests) | ``excluded`` (not granted = excluded), read by ``app.ai.personal.excluded_user_ids``.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.core import db as dbmod
from app.models import AuditEvent, CalendarConnection, CalendarEventLink, CalendarFeedToken, OAuthState, User
from app.workers import integrations as worker
from sqlalchemy import select

from tests.crbs_env import TODAY, env  # noqa: F401
from tests.integrations_support import FakeGoogle, client_factory, kvkk_sign_off

PANEL = "https://rezervasyon.uni.edu.tr"


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


def _consent_required(r: httpx.Response, purpose: str) -> dict:  # type: ignore[type-arg]
    assert r.status_code == 409, (r.status_code, r.text)
    d = r.json()["detail"]
    assert d["code"] == "consent_required" and d["purpose"] == purpose, d
    assert d["message"] == d["message_en"] and d["message_tr"] and d["message_tr"] != d["message_en"]
    assert "Profil › Gizlilik" in d["message_tr"] and "Profile › Privacy" in d["message_en"]
    assert d["label_tr"] in d["message_tr"] and d["label_en"] in d["message_en"]
    assert d["grant_path"] == "/profile#privacy" and d["grant_api"] == f"POST /api/v1/me/consents/{purpose}"
    return d


async def _links(uid: int) -> int:
    async with dbmod.get_session_factory()() as s:
        return len(list((await s.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == uid))).scalars()))


# ------------------------------------------------------------------------------------ item 1: consent gates


async def test_calendar_links_need_an_active_calendar_sync_consent_once_signed_off(env):  # noqa: F811
    c = env.client
    uid, ismail = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    # sync off (no sign-off yet): nothing is shared, a link can be prepared as before
    r = await c.post("/api/v1/calendar/feeds/tokens", json={"label": "İş telefonu"}, headers=ismail)
    assert r.status_code == 201, r.text
    status = (await c.get("/api/v1/calendar/sync", headers=ismail)).json()
    assert status["consent"] == {"purpose": "calendar_sync", "required": False, "granted": False}

    await kvkk_sign_off(env)
    status = (await c.get("/api/v1/calendar/sync", headers=ismail)).json()
    assert status["consent"] == {"purpose": "calendar_sync", "required": True, "granted": False}
    d = _consent_required(
        await c.post("/api/v1/calendar/feeds/tokens", json={"label": "İPAD"}, headers=ismail), "calendar_sync"
    )
    assert "Takvimimle eşitleme" in d["message_tr"] and "Sync with my calendar" in d["message_en"]
    # reset and the older bookings route are the same gate; a refused reset keeps the existing link
    _consent_required(await c.post("/api/v1/calendar/feeds/reset", headers=ismail), "calendar_sync")
    _consent_required(await c.post("/api/v1/bookings/feed/token", headers=ismail), "calendar_sync")
    assert await _links(uid) == 1

    # granted (Profil › Gizlilik): links are created and reset
    assert (await c.post("/api/v1/me/consents/calendar_sync", headers=ismail)).status_code == 200
    status = (await c.get("/api/v1/calendar/sync", headers=ismail)).json()
    assert status["consent"] == {"purpose": "calendar_sync", "required": True, "granted": True}
    r = await c.post("/api/v1/calendar/feeds/tokens", json={"label": "İPAD"}, headers=ismail)
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert (await c.get(f"/api/v1/calendar/feeds/{token}/mine.ics")).status_code == 200
    assert (await c.post("/api/v1/calendar/feeds/reset", headers=ismail)).status_code == 201
    assert (await c.post("/api/v1/bookings/feed/token", headers=ismail)).status_code == 200
    assert await _links(uid) == 1

    # withdrawn: the links go at once and a new one is refused again
    assert (await c.delete("/api/v1/me/consents/calendar_sync", headers=ismail)).status_code == 200
    assert await _links(uid) == 0
    _consent_required(await c.post("/api/v1/calendar/feeds/tokens", headers=ismail), "calendar_sync")
    # someone else's consent does not count
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    assert (await c.post("/api/v1/me/consents/calendar_sync", headers=ayse)).status_code == 200
    _consent_required(await c.post("/api/v1/calendar/feeds/tokens", headers=ismail), "calendar_sync")


async def test_push_connect_needs_the_consent_and_starts_nothing_without_it(env, monkeypatch):  # noqa: F811
    from app.services import calendar_connectors

    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await kvkk_sign_off(env)
    body = {
        "google_client_id": "google-client-id-uni",
        "google_client_secret": "google-secret-uni",
        "public_url": PANEL,
    }
    assert (await env.client.put("/api/v1/calendar/admin/settings", json=body, headers=env.admin)).status_code == 200
    uid, gokce = await env.user("gokce.sahin@uni.edu.tr", full_name="Gökçe Şahin")
    for provider in ("google", "microsoft"):
        r = await env.client.post(
            f"/api/v1/calendar/connectors/{provider}/connect", json={"return_path": "/profile"}, headers=gokce
        )
        _consent_required(r, "calendar_sync")
    async with dbmod.get_session_factory()() as s:
        assert list((await s.execute(select(OAuthState).where(OAuthState.user_id == uid))).scalars()) == []
    assert fake.requests == []
    assert (await env.client.post("/api/v1/me/consents/calendar_sync", headers=gokce)).status_code == 200
    r = await env.client.post(
        "/api/v1/calendar/connectors/google/connect", json={"return_path": "/profile"}, headers=gokce
    )
    assert r.status_code == 200, r.text
    assert r.json()["authorize_url"].startswith("https://accounts.google.com/")


async def test_require_consent_is_the_gate_for_a_photo_upload(env):  # noqa: F811
    """No profile-photo feature exists yet: the helper (and its route dependency) is what any upload path that stores
    a person's photo must call first."""
    from app.api.deps import consent_gate
    from app.services import kvkk

    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    gate = consent_gate("photo")
    async with dbmod.get_session_factory()() as s:
        me = await s.get(User, uid)
        assert me is not None
        with pytest.raises(kvkk.KvkkError) as exc:
            await kvkk.require_consent(s, me, "photo")
        d = exc.value.as_detail()
        assert exc.value.status == 409 and d["code"] == "consent_required" and d["purpose"] == "photo"
        assert "Profil fotoğrafı" in d["message_tr"] and "Profile photo" in d["message_en"]
        assert "Profil › Gizlilik" in d["message_tr"] and d["grant_path"] == "/profile#privacy"
        # the route dependency answers the same 409 detail
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as http:
            await gate(s, me)
        assert http.value.status_code == 409 and http.value.detail["code"] == "consent_required"  # type: ignore[index]
        with pytest.raises(ValueError):
            await kvkk.require_consent(s, me, "fotograf")
    assert (await env.client.post("/api/v1/me/consents/photo", headers=ayse)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        me = await s.get(User, uid)
        assert me is not None
        await kvkk.require_consent(s, me, "photo")
        assert await gate(s, me) is me
    assert (await env.client.delete("/api/v1/me/consents/photo", headers=ayse)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        me = await s.get(User, uid)
        assert me is not None
        with pytest.raises(kvkk.KvkkError):
            await kvkk.require_consent(s, me, "photo")


# ------------------------------------------------------------------------ item 2: erasure revokes at the provider


async def _google_connected(env, monkeypatch, email: str, name: str):  # type: ignore[no-untyped-def]  # noqa: F811
    from app.services import calendar_connectors

    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await kvkk_sign_off(env)
    body = {
        "google_client_id": "google-client-id-uni",
        "google_client_secret": "google-secret-uni",
        "public_url": PANEL,
    }
    assert (await env.client.put("/api/v1/calendar/admin/settings", json=body, headers=env.admin)).status_code == 200
    uid, who = await env.user(email, full_name=name)
    assert (await env.client.post("/api/v1/me/consents/calendar_sync", headers=who)).status_code == 200
    r = await env.book(who, "A101", TODAY, "P1")
    assert r.status_code in (201, 202), r.text
    r = await env.client.post(
        "/api/v1/calendar/connectors/google/connect", json={"return_path": "/profile"}, headers=who
    )
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    fake.codes["4/0AeanS0erase-code"] = q["code_challenge"]
    cb = await env.client.get(
        "/api/v1/calendar/connectors/google/callback", params={"code": "4/0AeanS0erase-code", "state": q["state"]}
    )
    assert cb.status_code == 302, cb.text
    await worker.wait_idle()
    assert (await env.client.post("/api/v1/calendar/feeds/tokens", headers=who)).status_code == 201
    return fake, uid, who


async def _erase(env, who: dict) -> dict:  # type: ignore[type-arg]  # noqa: F811
    r = await env.client.post(
        "/api/v1/me/data-requests", json={"kind": "erase", "note": "Kurumdan ayrıldım"}, headers=who
    )
    assert r.status_code == 201, r.text
    r = await env.client.post(f"/api/v1/admin/dsr/{r.json()['id']}/complete", json={"note": "Tamam"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DONE"
    await worker.wait_idle()
    return r.json()["result"]


async def _rows(uid: int) -> dict[str, int]:
    async with dbmod.get_session_factory()() as s:
        conns = list((await s.execute(select(CalendarConnection).where(CalendarConnection.user_id == uid))).scalars())
        links = list((await s.execute(select(CalendarEventLink))).scalars())
        feeds = list((await s.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == uid))).scalars())
        return {"connections": len(conns), "links": len(links), "feeds": len(feeds)}


async def _erase_audit() -> dict:  # type: ignore[type-arg]
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == "kvkk.erase").order_by(AuditEvent.id)
        return list((await s.execute(q)).scalars())[-1].after


async def test_erasure_removes_pushed_events_and_revokes_the_grant_at_the_provider(env, monkeypatch):  # noqa: F811
    fake, uid, who = await _google_connected(env, monkeypatch, "ismail.isik@uni.edu.tr", "İsmail Işık")
    assert len(fake.events) == 1  # the Bahar booking reached Google
    result = await _erase(env, who)
    assert fake.events == {} and len(fake.calls("DELETE", "/events/")) == 1
    revoke = fake.calls("POST", "oauth2.googleapis.com/revoke")
    assert len(revoke) == 1 and fake.form(revoke[0])["token"] == "1//0gLkXtestRefreshTokenGoogle"
    assert fake.requests.index(revoke[0]) > fake.requests.index(fake.calls("DELETE", "/events/")[0])
    assert result["counts"]["calendar_connections"] == 1 and result["counts"]["calendar_feed_tokens"] == 1
    assert result["calendar"] == [
        {"provider": "google", "events": 1, "events_removed": 1, "events_failed": 0, "revoke": "done", "errors": []}
    ]
    assert result["failures"] == []
    assert await _rows(uid) == {"connections": 0, "links": 0, "feeds": 0}
    assert (await _erase_audit())["failures"] == []


async def test_provider_failures_are_recorded_and_never_block_the_erasure(env, monkeypatch):  # noqa: F811
    fake, uid, who = await _google_connected(env, monkeypatch, "gokce.sahin@uni.edu.tr", "Gökçe Şahin")
    # Google is down for the event delete and the revoke; the Microsoft grant stored earlier cannot be read any more
    # (APP_SECRET rotated), so nothing can be revoked there
    fake.fail_next += [
        ("DELETE", "/events/", httpx.Response(503, json={"error": {"code": 503, "message": "Backend Error"}})),
        ("POST", "oauth2.googleapis.com/revoke", httpx.Response(503, json={"error": "temporarily_unavailable"})),
    ]
    async with dbmod.get_session_factory()() as s:
        s.add(CalendarConnection(user_id=uid, provider="microsoft", access_token_enc="gAAAAAbozuk-" + "rotated-key"))
        await s.commit()
    result = await _erase(env, who)
    by = {x["provider"]: x for x in result["calendar"]}
    assert by["google"]["events"] == 1 and by["google"]["events_failed"] == 1 and by["google"]["revoke"] == "failed"
    assert by["microsoft"]["revoke"] == "unreadable"
    codes = sorted((f["provider"], f["code"]) for f in result["failures"])
    assert codes == [("google", "events_not_removed"), ("google", "revoke_failed"), ("microsoft", "grant_unreadable")]
    for f in result["failures"]:
        assert f["message_en"] and f["message_tr"] and f["message_tr"] != f["message_en"]
    # the erasure itself went through: no rows, an anonymised account, the audit names the failures
    assert await _rows(uid) == {"connections": 0, "links": 0, "feeds": 0}
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, uid)
        assert u is not None and u.email is None and u.full_name is None and u.is_active is False
    assert len((await _erase_audit())["failures"]) == 3


async def test_a_disconnect_that_raises_is_recorded_and_the_rows_still_go(env, monkeypatch):  # noqa: F811
    from app.services import calendar_connectors

    fake, uid, who = await _google_connected(env, monkeypatch, "ayse.yilmaz@uni.edu.tr", "Ayşe Yılmaz")

    async def broken(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider table missing")

    monkeypatch.setattr(calendar_connectors, "disconnect", broken)
    result = await _erase(env, who)
    assert [(f["provider"], f["code"]) for f in result["failures"]] == [("google", "disconnect_failed")]
    assert "RuntimeError" in result["failures"][0]["error"]
    assert await _rows(uid) == {"connections": 0, "links": 0, "feeds": 0}


# ------------------------------------------------------------------------------- item 3: ai_personal default


async def _excluded() -> list[int]:
    from app.ai.personal import excluded_user_ids

    async with dbmod.get_session_factory()() as s:
        return await excluded_user_ids(s)


async def _privacy(env, who: dict) -> dict:  # type: ignore[type-arg]  # noqa: F811
    r = await env.client.get("/api/v1/me/privacy", headers=who)
    assert r.status_code == 200, r.text
    return r.json()


async def test_ai_personal_default_included_only_a_withdrawal_excludes(env):  # noqa: F811
    never, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    granted, ismail = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    withdrawn, gokce = await env.user("gokce.sahin@uni.edu.tr", full_name="Gökçe Şahin")
    assert (await env.client.post("/api/v1/me/consents/ai_personal", headers=ismail)).status_code == 200
    assert (await env.client.delete("/api/v1/me/consents/ai_personal", headers=gokce)).status_code == 200
    s = (await env.client.get("/api/v1/settings", headers=env.admin)).json()
    assert s["kvkk.ai_personal_default"] == "included"
    assert await _excluded() == [withdrawn]
    p = await _privacy(env, ayse)
    assert p["ai_personal_default"] == "included" and p["ai_excluded"] is False
    assert (await _privacy(env, gokce))["ai_excluded"] is True
    assert never not in await _excluded() and granted not in await _excluded()


async def test_ai_personal_default_excluded_means_not_granted_is_excluded(env):  # noqa: F811
    never, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    granted, ismail = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    withdrawn, gokce = await env.user("gokce.sahin@uni.edu.tr", full_name="Gökçe Şahin")
    assert (await env.client.post("/api/v1/me/consents/ai_personal", headers=ismail)).status_code == 200
    assert (await env.client.delete("/api/v1/me/consents/ai_personal", headers=gokce)).status_code == 200

    async def put(value: object) -> httpx.Response:
        return await env.client.put(
            "/api/v1/settings", json={"extra": {"kvkk.ai_personal_default": value}}, headers=env.admin
        )

    # a wrong value is refused with a field code in both languages and changes nothing
    r = await put("belki")
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert (d["code"], d["field"], d["allowed"]) == (
        "ai_personal_default",
        "kvkk.ai_personal_default",
        ["included", "excluded"],
    )
    assert d["message_tr"] and d["message_tr"] != d["message_en"]
    assert (await env.client.get("/api/v1/settings", headers=env.admin)).json()[
        "kvkk.ai_personal_default"
    ] == "included"
    # Turkish words, capitals and NBSP read as the setting
    r = await put(" HARİÇ ")
    assert r.status_code == 200, r.text
    assert r.json()["kvkk.ai_personal_default"] == "excluded"
    ex = await _excluded()
    assert never in ex and withdrawn in ex and granted not in ex
    async with dbmod.get_session_factory()() as s:
        admin_ids = list((await s.execute(select(User.id).where(User.role == "ADMIN"))).scalars())
    assert set(admin_ids) <= set(ex)  # nobody granted -> nobody is sent
    p = await _privacy(env, ayse)
    assert p["ai_personal_default"] == "excluded" and p["ai_excluded"] is True
    assert (await _privacy(env, ismail))["ai_excluded"] is False
    # the change is in the audit log (settings rows are tracked)
    async with dbmod.get_session_factory()() as s:
        rows = list(
            (await s.execute(select(AuditEvent).where(AuditEvent.entity_id == "kvkk.ai_personal_default"))).scalars()
        )
        assert rows and rows[-1].after and "excluded" in str(rows[-1].after)
    # back to the default
    r = await put("Dahil")
    assert r.status_code == 200 and r.json()["kvkk.ai_personal_default"] == "included"
    assert await _excluded() == [withdrawn]


async def test_excluded_default_keeps_a_never_granted_instructor_out_of_the_prompt(env, monkeypatch):  # noqa: F811
    """A teacher linked to a real Bahar instructor never touched the consent: under ``excluded`` the planner's prompt
    naming that instructor reaches the model as ``[KİŞİ_n]``; granting the consent sends the name again."""
    import json as _json

    import anthropic
    from app.importers import normalize as n
    from app.models import Instructor, Term
    from app.services import settings_service as ss

    from tests.ai.conftest import FakeSDK, empty_selector, proposal, tool

    FakeSDK.instances, FakeSDK.script, FakeSDK.calls = [], [], []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeSDK)
    uid, teacher = await env.user("gokce.sahin@uni.edu.tr", full_name="Gökçe Şahin")
    async with dbmod.get_session_factory()() as s:
        await ss.set_value(s, "anthropic_api_key", "sk-ant-" + "test-key-0000")
        people = list((await s.execute(select(Instructor).order_by(Instructor.id))).scalars())
        inst = next(
            i
            for i in people
            if i.full_name
            and len(n.clean_text(i.canonical_name or "").split(" ")) >= 2
            and set("çğıöşüİ") & set(i.full_name)
        )
        inst.user_id = uid
        bare = " ".join(w for w in (inst.canonical_name or "").split(" ") if w)
        term_id = (await s.execute(select(Term.id).where(Term.code.like("%BAHAR%")))).scalars().first()
        await s.commit()
    words = bare.split(" ")
    typed = f"{n.tr_upper(words[0])} {' '.join(words[1:])} hoca pazartesi ders vermesin"

    async def elicit(who: str) -> str:
        sel = empty_selector(instructor_name=who)
        FakeSDK.script = [
            tool(
                "propose_constraints",
                {
                    "proposals": [proposal("day_window", "soft", selector=sel, nl_text=f"{who} pazartesi yok")],
                    "section_edits": [],
                    "unparsed": [],
                },
            )
        ]
        r = await env.client.post(
            f"/api/v1/terms/{term_id}/elicit", json={"text": typed, "lang": "tr"}, headers=env.planner
        )
        assert r.status_code == 200, r.text
        return n.tr_casefold(_json.dumps(FakeSDK.calls[-1], ensure_ascii=False))

    assert n.tr_casefold(words[-1]) in await elicit(bare)  # included (default): the name is sent as typed
    r = await env.client.put(
        "/api/v1/settings", json={"extra": {"kvkk.ai_personal_default": "excluded"}}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    sent = await elicit("[KİŞİ_1]")
    assert n.tr_casefold(words[-1]) not in sent and n.tr_casefold("[KİŞİ_") in sent
    assert (await env.client.post("/api/v1/me/consents/ai_personal", headers=teacher)).status_code == 200
    assert n.tr_casefold(words[-1]) in await elicit(bare)


async def test_a_slow_provider_finishes_in_the_background_and_the_erasure_answers(env, monkeypatch):  # noqa: F811
    import asyncio

    from app.services import calendar_connectors

    fake, uid, who = await _google_connected(env, monkeypatch, "ismail.isik@uni.edu.tr", "İsmail Işık")
    slow = {"n": 0}
    answer = fake.__call__

    async def slow_delete(req: httpx.Request) -> httpx.Response:
        if req.method == "DELETE" and slow["n"] == 0:
            slow["n"] += 1
            await asyncio.sleep(1.0)
        return await answer(req)

    monkeypatch.setattr(calendar_connectors, "WAIT_CLEANUP_S", 0.2)
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(slow_delete))
    result = await _erase(env, who)  # waits for the background worker too
    assert [(f["provider"], f["code"]) for f in result["failures"]] == [("google", "provider_timeout")]
    assert result["calendar"][0]["revoke"] == "queued"
    assert "Google Calendar zamanında yanıt vermedi" in result["failures"][0]["message_tr"]
    # the background finished the job: the event is gone and the grant revoked
    assert fake.events == {} and len(fake.calls("POST", "oauth2.googleapis.com/revoke")) == 1
    assert await _rows(uid) == {"connections": 0, "links": 0, "feeds": 0}
