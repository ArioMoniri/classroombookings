"""A4 KVKK follow-ups (backend asks batch 3, ``backend-asks-3-2026-10-16``) on the real Bahar 2026 import
(``tests/crbs_env``; clock Monday 16 Feb 2026 08:00):

* item 3 -- every ``PUT /admin/retention/{data_class}`` 422 names a stable ``code`` and the input ``field`` with
  English and Turkish messages (Turkish input forms: ``1.095`` days, ``365 gün``, ``SİL``, ``evet``);
* item 4 -- ``GET /admin/dsr?status=all`` lists every request; ``open | DONE | REFUSED | ...`` as before;
* item 5 -- what withdrawing the ``photo``, ``calendar_sync`` and ``ai_personal`` consents does (counts + audit).
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent
from app.models.kvkk import RetentionPolicy
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

RET = "/api/v1/admin/retention"


def _bilingual(d: dict) -> None:  # type: ignore[type-arg]
    assert d["message"] and d["message_en"] == d["message"] and d["message_tr"]
    assert d["message_tr"] != d["message_en"], d


async def test_retention_errors_carry_field_codes_in_both_languages(env):  # noqa: F811
    c, admin = env.client, env.admin
    assert (await c.get(RET, headers=admin)).status_code == 200  # the rows exist from the first read

    async def put(cls: str, body: dict) -> dict:  # type: ignore[type-arg]
        r = await c.put(f"{RET}/{cls}", json=body, headers=admin)
        assert r.status_code == 422, (cls, body, r.status_code, r.text)
        d = r.json()["detail"]
        assert isinstance(d, dict), d
        _bilingual(d)
        assert d["errors"] and d["errors"][0]["code"] == d["code"] and d["errors"][0]["field"] == d["field"]
        for e in d["errors"]:
            _bilingual(e)
        return d

    # below the floor the code sets (audit 365 days)
    d = await put("audit", {"retain_days": 100})
    assert (d["code"], d["field"], d["floor_days"]) == ("below_floor", "retain_days", 365)
    assert "365" in d["message_tr"] and "365" in d["message_en"]
    # not a number of days, or absurdly long: the same field, its own code
    for bad in ("abc", "12,5", True, 3.5, 10**9, [], {"g": 1}):
        d = await put("booking", {"retain_days": bad})
        assert (d["code"], d["field"]) == ("retain_days", "retain_days"), bad
    # the action: an unknown word, and delete for bookings (anonymised only)
    d = await put("notification", {"action": "yak"})
    assert (d["code"], d["field"]) == ("action", "action") and d["allowed"] == ["delete", "anonymise"]
    d = await put("booking", {"action": "SİL"})
    assert (d["code"], d["field"], d["allowed"]) == ("action", "action", ["anonymise"])
    assert "anonimleştirilir" in d["message_tr"]
    # switches
    for key in ("enabled", "legal_hold"):
        d = await put("notification", {key: "belki"})
        assert (d["code"], d["field"]) == (key, key)
    # a legal hold without a reason, and a reason that is not text
    d = await put("notification", {"legal_hold": True})
    assert (d["code"], d["field"]) == ("legal_hold_reason", "legal_hold_reason")
    d = await put("notification", {"legal_hold": True, "legal_hold_reason": 42})
    assert (d["code"], d["field"]) == ("legal_hold_reason", "legal_hold_reason")
    # unknown data classes, and classes without a retention policy (kept until the person removes them)
    for cls in ("ufo", "account", "phone"):
        d = await put(cls, {"retain_days": 400})
        assert (d["code"], d["field"]) == ("unknown_class", "data_class")
        assert d["allowed"] == ["booking", "audit", "notification"]
    # several mistakes at once: every one listed, the first on top
    d = await put("booking", {"retain_days": "x", "action": "delete", "enabled": "?"})
    assert [(e["code"], e["field"]) for e in d["errors"]] == [
        ("retain_days", "retain_days"),
        ("action", "action"),
        ("enabled", "enabled"),
    ]
    # nothing was changed by a refused request
    async with dbmod.get_session_factory()() as s:
        rows = {p.data_class: p for p in (await s.execute(select(RetentionPolicy))).scalars()}
        assert rows["booking"].action == "anonymise" and rows["booking"].retain_days == 1095
        assert not rows["notification"].legal_hold and not rows["notification"].enabled
        n_audit = len(
            list((await s.execute(select(AuditEvent).where(AuditEvent.action == "kvkk.retention_policy"))).scalars())
        )
        assert n_audit == 0

    # Turkish input forms are read, not refused: thousands dot, "gün", NBSP, SİL / evet / hayır
    r = await c.put(
        f"{RET}/booking", json={"retain_days": "1.095 gün", "enabled": "Evet", "action": "Anonimleştir"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (r.json()["retain_days"], r.json()["enabled"], r.json()["action"]) == (1095, True, "anonymise")
    r = await c.put(
        f"{RET}/notification", json={"retain_days": " 45 ", "action": "SİL", "enabled": "hayır"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert (r.json()["retain_days"], r.json()["enabled"], r.json()["action"]) == (45, False, "delete")


async def test_dsr_queue_status_all_and_the_allowed_values(env):  # noqa: F811
    c, admin = env.client, env.admin
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    _, ismail = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    _, ali = await env.user("ali.kaya@uni.edu.tr", full_name="Ali Kaya")
    ids = {}
    for who, kind in ((ayse, "rectify"), (ismail, "info"), (ali, "erase"), (ayse, "export")):
        r = await c.post("/api/v1/me/data-requests", json={"kind": kind, "note": "Talep"}, headers=who)
        assert r.status_code == 201, r.text
        ids[kind] = r.json()["id"]
    r = await c.post(f"/api/v1/admin/dsr/{ids['rectify']}/refuse", json={"reason": "Kayıt doğru"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "REFUSED"
    r = await c.post(f"/api/v1/admin/dsr/{ids['info']}/complete", json={"note": "Yanıtlandı"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "DONE", r.text

    async def queue(status: str | None) -> list[int]:
        params = {"status": status} if status is not None else {}
        r = await c.get("/api/v1/admin/dsr", params=params, headers=admin)
        assert r.status_code == 200, (status, r.text)
        return [x["id"] for x in r.json()]

    queued = {ids["rectify"], ids["info"], ids["erase"]}  # exports are self-service, never queued
    assert set(await queue("all")) == queued and len(await queue("all")) == 3
    assert set(await queue("ALL")) == queued
    assert await queue(None) == [ids["erase"]] == await queue("open")
    assert await queue("DONE") == [ids["info"]] == await queue("done")
    assert await queue("REFUSED") == [ids["rectify"]] == await queue("refused")
    assert await queue("OPEN") == [ids["erase"]] and await queue("IN_PROGRESS") == []
    assert await queue("in_progress") == [] and set(await queue(" All ")) == queued
    # an unknown value is a 422 with the allowed values, not an empty list
    r = await c.get("/api/v1/admin/dsr", params={"status": "bitti"}, headers=admin)
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert (d["code"], d["field"]) == ("status", "status") and d["message_tr"] != d["message_en"]
    assert d["allowed"] == ["open", "all", "OPEN", "IN_PROGRESS", "DONE", "REFUSED"]


# ------------------------------------------------------------------------------------------- item 5: consents

ZERO = {"removed_channels": 0, "removed_photo": 0, "revoked_feeds": 0, "disconnected_calendars": 0}


async def _withdraw(env, who: dict, purpose: str) -> dict:  # type: ignore[no-untyped-def,type-arg]  # noqa: F811
    assert (await env.client.post(f"/api/v1/me/consents/{purpose}", headers=who)).status_code == 200
    r = await env.client.delete(f"/api/v1/me/consents/{purpose}", headers=who)
    assert r.status_code == 200, r.text
    out = r.json()
    assert {c["purpose"]: c["granted"] for c in out["consents"]}[purpose] is False
    for e in out["effects"]:
        assert e["code"] and e["message_tr"] and e["message_en"] and e["message_tr"] != e["message_en"]
    return out


async def _last_withdraw_audit(purpose: str) -> dict:  # type: ignore[type-arg]
    async with dbmod.get_session_factory()() as s:
        q = select(AuditEvent).where(AuditEvent.action == "kvkk.consent_withdraw", AuditEvent.entity_id == purpose)
        return list((await s.execute(q.order_by(AuditEvent.id))).scalars())[-1].after


async def test_withdrawing_photo_deletes_the_stored_profile_photo(env):  # noqa: F811
    from app.core.config import get_settings
    from app.services import kvkk

    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    other, _ = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    base = kvkk.profile_photo_dir()
    assert str(base).startswith(get_settings().upload_dir)
    base.mkdir(parents=True, exist_ok=True)
    mine = [base / f"{uid}.jpg", base / f"{uid}.webp"]
    keep = base / f"{other}.jpg"
    for p in (*mine, keep):
        p.write_bytes(b"\xff\xd8\xff")
    # nothing under the uploads mount serves user photos (only room photos are public)
    assert (await env.client.get(f"/uploads/users/{uid}.jpg")).status_code == 404

    out = await _withdraw(env, ayse, "photo")
    assert {k: out[k] for k in ZERO} == {**ZERO, "removed_photo": 2} and out["ai_excluded"] is False
    assert [e["code"] for e in out["effects"]] == ["photo_deleted"]
    assert not any(p.exists() for p in mine) and keep.exists()
    assert (await _last_withdraw_audit("photo"))["removed_photo"] == 2
    # again: nothing left to delete, still a clean answer
    out = await _withdraw(env, ayse, "photo")
    assert out["removed_photo"] == 0 and [e["code"] for e in out["effects"]] == ["photo_none"]


async def test_withdrawing_calendar_sync_revokes_feeds_and_disconnects_push(env, monkeypatch):  # noqa: F811
    from datetime import timedelta

    from app.core.security import encrypt_secret
    from app.models import CalendarConnection, CalendarEventLink, CalendarFeedToken, User
    from app.models.base import utcnow
    from app.models.integrations import OAuthState
    from app.services import calendar_connectors as conn_svc
    from app.services import calendar_feeds as feeds

    detached: list[str] = []
    monkeypatch.setattr(conn_svc.worker, "run_detached", lambda fn, key: detached.append(key))
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    oid, _ = await env.user("ismail.isik@uni.edu.tr", full_name="İsmail Işık")
    async with dbmod.get_session_factory()() as s:
        me, him = await s.get(User, uid), await s.get(User, oid)
        _, token = await feeds.create_token(s, me, "Telefon")
        await feeds.create_token(s, me, "İş bilgisayarı")
        await feeds.create_token(s, him, "Kendi")
        conn = CalendarConnection(
            user_id=uid, provider="google", calendar_id="primary", access_token_enc=encrypt_secret("ya29.fake-access")
        )
        s.add(conn)
        await s.flush()
        s.add(CalendarEventLink(connection_id=conn.id, booking_id=999_999, calendar_id="primary", external_id="ev1"))
        s.add(
            OAuthState(
                state_hash="h" * 64,
                user_id=uid,
                provider="microsoft",
                code_verifier_enc="x",
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )
        await s.commit()
    # sync on, so the feed answers before the withdrawal
    r = await env.client.put("/api/v1/calendar/admin/settings", json={"calendar_sync_enabled": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert (await env.client.get(f"/api/v1/calendar/feeds/{token}/mine.ics")).status_code == 200

    out = await _withdraw(env, ayse, "calendar_sync")
    assert {k: out[k] for k in ZERO} == {**ZERO, "revoked_feeds": 2, "disconnected_calendars": 1}
    assert [e["code"] for e in out["effects"]] == ["feeds_revoked", "calendars_disconnected"]
    assert detached == [f"integrations:revoke:google:{uid}"]  # events removed + grant revoked at the provider
    assert (await env.client.get(f"/api/v1/calendar/feeds/{token}/mine.ics")).status_code == 404
    async with dbmod.get_session_factory()() as s:
        for model in (CalendarFeedToken, CalendarConnection, OAuthState):
            rows = list((await s.execute(select(model).where(model.user_id == uid))).scalars())
            assert rows == [], model
        assert (
            len(list((await s.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == oid))).scalars()))
            == 1
        )
    after = await _last_withdraw_audit("calendar_sync")
    assert after["revoked_feeds"] == 2 and after["disconnected_calendars"] == 1


def _variants(name: str) -> set[str]:
    """Ways a name can reach a prompt: as written, Turkish upper / lower case, ASCII-folded."""
    from app.importers import normalize as n

    fold = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    out = {name, n.tr_upper(name), n.tr_casefold(name)}
    return {v for x in list(out) for v in (x, x.translate(fold), x.translate(fold).lower())}


async def test_withdrawing_ai_personal_keeps_the_person_out_of_every_prompt(env, monkeypatch):  # noqa: F811
    """A teacher linked to a real Bahar instructor withdraws ``ai_personal``: the planner's prompt names that
    instructor (Turkish capitals, NBSP, ASCII-folded), the model only ever sees ``[KİŞİ_1]``, and the server maps the
    token back so the rule still resolves to the instructor."""
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
        # the withdrawal path under an admin's "included" choice (the default is "excluded" since the owner
        # decision 2026-10-17, R1-M-07: tests/test_consent_gates.py covers it)
        await ss.set_value(s, "kvkk.ai_personal_default", "included")
        people = list((await s.execute(select(Instructor).order_by(Instructor.id))).scalars())
        # a real Bahar instructor with a Turkish letter in a two-word (or longer) name
        inst = next(
            i
            for i in people
            if i.full_name
            and len(n.clean_text(i.canonical_name or "").split(" ")) >= 2
            and set("çğıöşüİ") & set(i.full_name)
        )
        inst.user_id = uid
        name = n.clean_text(inst.full_name) or ""
        bare = " ".join(w for w in (inst.canonical_name or "").split(" ") if w)
        term_id = (await s.execute(select(Term.id).where(Term.code.like("%BAHAR%")))).scalars().first()
        await s.commit()
    words = bare.split(" ")
    typed = f"{n.tr_upper(words[0])} {' '.join(words[1:])} hoca pazartesi ders vermesin; gokce.sahin@uni.edu.tr"

    def script(who: str) -> None:
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

    async def elicit() -> dict:  # type: ignore[type-arg]
        r = await env.client.post(
            f"/api/v1/terms/{term_id}/elicit", json={"text": typed, "lang": "tr"}, headers=env.planner
        )
        assert r.status_code == 200, r.text
        return r.json()

    # before: the institution's AI processing (admin sign-off) applies, the name is sent as typed
    script(bare)
    await elicit()
    sent = n.tr_casefold(_json.dumps(FakeSDK.calls[-1], ensure_ascii=False))
    assert n.tr_casefold(words[-1]) in sent

    out = await _withdraw(env, teacher, "ai_personal")
    assert {k: out[k] for k in ZERO} == ZERO and out["ai_excluded"] is True
    assert [e["code"] for e in out["effects"]] == ["ai_excluded"]
    assert (await _last_withdraw_audit("ai_personal"))["ai_excluded"] is True

    script("[KİŞİ_1]")
    res = await elicit()
    blob = _json.dumps(FakeSDK.calls[-1], ensure_ascii=False)
    for v in _variants(bare) | _variants(name) | _variants("Gökçe Şahin") | {"gokce.sahin"}:
        assert v not in blob and v not in n.tr_casefold(blob), v
    assert "[KİŞİ_1]" in blob
    ents = [e for p in res["proposals"] for e in p["entities"] if e["type"] == "instructor"]
    assert ents and ents[0]["resolved_id"] == inst.id, res["proposals"]
    assert res["proposals"][0]["nl_text"].startswith(n.clean_text(inst.full_name) or "")

    # granting again lifts the exclusion
    assert (await env.client.post("/api/v1/me/consents/ai_personal", headers=teacher)).status_code == 200
    script(bare)
    await elicit()
    assert n.tr_casefold(words[-1]) in n.tr_casefold(_json.dumps(FakeSDK.calls[-1], ensure_ascii=False))
