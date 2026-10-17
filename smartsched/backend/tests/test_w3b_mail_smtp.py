"""W3-MAIL SMTP setup: presets, settings shared by every admin (write-only secrets, audited, "Son değişiklik"),
the test e-mail against a local sink on port 2721 (STARTTLS, AUTH PLAIN / XOAUTH2) with a transcript excerpt that
never carries a secret, plain Turkish hints, template overrides / preview / test send, and permissions."""

from __future__ import annotations

import ssl
from collections.abc import Iterator

import pytest
from app.models import AuditEvent, NotificationOutbox
from app.services import mail_oauth, mail_presets
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401
from tests.crbs_support import make_user
from tests.w3b_mail_sink import PORT, Sink, make_cert

SECRET = "smtp-gizli"


@pytest.fixture
def sink(tmp_path, monkeypatch) -> Iterator[Sink]:  # type: ignore[no-untyped-def]
    cert, key = make_cert(tmp_path)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert, key)
    real = ssl.create_default_context

    def trusting(*a, **kw):  # type: ignore[no-untyped-def]
        ctx = real(*a, **kw)
        ctx.load_verify_locations(cafile=str(cert))
        return ctx

    from app.services import mail

    monkeypatch.setattr(mail.ssl, "create_default_context", trusting)
    s = Sink(tls=server_ctx).start()
    yield s
    s.stop()


async def _admin(c) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return await login(c)


async def _configure(c, h, **extra):  # type: ignore[no-untyped-def]
    body = {
        "provider": "custom",
        "host": "localhost",
        "port": PORT,
        "security": "starttls",
        "auth_mode": "password",
        "username": "bildirim@uni.edu.tr",
        "password": SECRET,
        "from_address": "Bildirim@Uni.edu.tr",
        "from_name": "Örnek Üniversitesi Planlama",
        "reply_to": "planlama@uni.edu.tr",
        **extra,
    }
    r = await c.put("/api/v1/mail/settings", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_presets_fill_host_port_tls_and_console_steps() -> None:
    by = {p["id"]: p for p in mail_presets.presets_out()}
    assert {
        "google_app_password",
        "google_oauth2",
        "microsoft365_oauth2",
        "amazon_ses",
        "sendgrid",
        "mailgun",
        "postmark",
        "brevo",
        "yandex",
        "custom",
    } <= set(by)
    assert (by["google_app_password"]["host"], by["google_app_password"]["port"]) == ("smtp.gmail.com", 587)
    ms = by["microsoft365_oauth2"]
    assert ms["auth_mode"] == "xoauth2" and ms["oauth_provider"] == "microsoft" and ms["security"] == "starttls"
    assert any(s["copy"] == "SMTP.SendAsApp" for s in ms["steps"]) and "Basic auth" in ms["notes_tr"]
    assert by["yandex"]["port"] == 465 and by["yandex"]["security"] == "ssl"
    assert by["sendgrid"]["extra"]["username"] == "apikey"
    assert len(by["amazon_ses"]["hosts"]) >= 3
    for p in by.values():
        assert p["steps"] and all(s["tr"] and s["en"] for s in p["steps"]), p["id"]


async def test_settings_are_shared_masked_audited_with_last_change(client) -> None:  # noqa: F811
    h = await _admin(client)
    out = await _configure(client, h)
    assert out["password"] == {"set": True, "masked": "smtp********izli"} and SECRET not in str(out)
    assert out["from_address"] == "bildirim@uni.edu.tr" and out["configured"] is True
    assert out["last_change"]["by"] and out["last_change"]["at"]
    # a second administrator sees the same settings (organisation rows, not per browser / user)
    _, other = await make_user(client, h, "gozde.ayrancigil@uni.edu.tr", role="ADMIN")
    seen = (await client.get("/api/v1/mail/settings", headers=other)).json()
    assert seen["host"] == "localhost" and seen["password"]["set"] is True
    # null keeps the secret; the audit log records the change without the value
    r = await client.put("/api/v1/mail/settings", json={"password": None, "from_name": "Planlama"}, headers=other)
    assert r.status_code == 200 and r.json()["password"]["set"] is True
    from app.core import db as dbmod

    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(AuditEvent).where(AuditEvent.entity_id == "smtp.password"))).scalars())
    assert rows and all(SECRET not in str(r.after) for r in rows)
    last = (await client.get("/api/v1/mail/settings", headers=h)).json()["last_change"]
    assert last["key"] == "from_name" and "gozde" in (last["by"] or "").lower() or last["by"]
    # "" clears
    r = await client.put("/api/v1/mail/settings", json={"password": ""}, headers=h)
    assert r.json()["password"]["set"] is False


async def test_settings_validation(client) -> None:  # noqa: F811
    h = await _admin(client)
    bad = await client.put("/api/v1/mail/settings", json={"from_address": "not an address"}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["message_tr"]
    plain = await client.put(
        "/api/v1/mail/settings",
        json={"host": "smtp.uni.edu.tr", "security": "none", "username": "u", "password": "p"},
        headers=h,
    )
    assert plain.status_code == 422 and plain.json()["detail"]["code"] == "plaintext_auth"
    assert "şifrelenmemiş" in plain.json()["detail"]["message_tr"]
    host = await client.put("/api/v1/mail/settings", json={"host": "smtp uni; rm"}, headers=h)
    assert host.status_code == 422
    preset = await client.put("/api/v1/mail/settings", json={"provider": "nope"}, headers=h)
    assert preset.status_code == 422


async def test_teachers_cannot_read_or_change_mail_settings(client) -> None:  # noqa: F811
    h = await _admin(client)
    _, teacher = await make_user(client, h, "ayse.yilmaz@uni.edu.tr")
    for method, path, body in (
        ("get", "/api/v1/mail/settings", None),
        ("put", "/api/v1/mail/settings", {"host": "evil.example"}),
        ("get", "/api/v1/mail/presets", None),
        ("post", "/api/v1/mail/test", {"to": "x@uni.edu.tr"}),
        ("post", "/api/v1/mail/dns-check", {"domain": "uni.edu.tr"}),
        ("get", "/api/v1/mail/templates", None),
        ("put", "/api/v1/mail/templates/approval_rejected", {"locale": "tr", "subject": "x"}),
        ("post", "/api/v1/mail/templates/approval_rejected/preview", {"locale": "tr"}),
    ):
        r = await getattr(client, method)(path, headers=teacher, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (path, r.status_code)
    assert (await client.get("/api/v1/mail/settings")).status_code == 401


async def test_test_email_reaches_the_sink_with_a_safe_transcript(client, sink) -> None:  # noqa: F811
    h = await _admin(client)
    await _configure(client, h)
    r = await client.post("/api/v1/mail/test", json={"to": "Hoca@Uni.edu.tr", "locale": "tr"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["status"] == "SENT", out
    (got,) = sink.messages
    assert got.rcpts == ["hoca@uni.edu.tr"] and got.mail_from == "bildirim@uni.edu.tr"
    msg = got.message
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["Reply-To"] == "planlama@uni.edu.tr" and msg["Auto-Submitted"] == "auto-generated"
    assert "Örnek Üniversitesi Planlama" in str(msg["From"])
    plain = msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "deneme iletisi" in plain and "<table" in html and "cid:logo@smartsched" in html
    related = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert related and related[0]["Content-ID"] == "<logo@smartsched>"
    lines = out["transcript"]
    assert any(line.startswith("S: 220") for line in lines) and any("STARTTLS" in line for line in lines)
    assert any(line.startswith("* TLS") for line in lines) and "C: AUTH PLAIN ********" in lines
    assert any(line.startswith("S: 235") for line in lines)
    blob = "\n".join(lines)
    import base64

    assert SECRET not in blob and base64.b64encode(f"\x00bildirim@uni.edu.tr\x00{SECRET}".encode()).decode() not in blob
    assert "deneme iletisi" not in blob  # the body is summarised, never copied
    st = (await client.get("/api/v1/mail/status", headers=h)).json()
    assert st["state"] == "connected" and st["last_check"]["ok"] is True


async def test_wrong_password_is_explained_in_turkish(client, sink) -> None:  # noqa: F811
    h = await _admin(client)
    await _configure(client, h, password="yanlis", provider="google_app_password")
    out = (await client.post("/api/v1/mail/test", json={"to": "hoca@uni.edu.tr"}, headers=h)).json()
    assert out["ok"] is False and out["status"] == "FAILED"
    assert "uygulama şifresi" in out["hint_tr"] and "app password" in out["hint_en"]
    assert "yanlis" not in str(out)
    assert (await client.get("/api/v1/mail/status", headers=h)).json()["state"] == "error"


async def test_unreachable_port_is_explained(client) -> None:  # noqa: F811
    h = await _admin(client)
    await _configure(client, h, port=1, security="ssl")
    out = (await client.post("/api/v1/mail/test", json={"to": "hoca@uni.edu.tr"}, headers=h)).json()
    assert out["ok"] is False and out["hint_tr"]


async def test_microsoft_365_xoauth2_against_the_sink(client, sink, monkeypatch) -> None:  # noqa: F811
    token = "eyJ0eXAi" + "OiJKV1QiLCJub25jZSI6InczYi1tYWlsIn0"
    sink.bearer = token
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_post(url, data, timeout):  # type: ignore[no-untyped-def]
        calls.append((url, data))
        return {"access_token": token, "expires_in": 3599}

    monkeypatch.setattr(mail_oauth, "_post", fake_post)
    mail_oauth.clear_cache()
    h = await _admin(client)
    await _configure(
        client,
        h,
        provider="microsoft365_oauth2",
        auth_mode="xoauth2",
        oauth_provider="microsoft",
        oauth_tenant="3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a",
        oauth_client_id="6b1d9e2f-0c4a-4f8e-9d3b-7a5c2e1f8b0d",
        oauth_client_secret="ms-" + "client-secret-value",
        password="",
    )
    out = (await client.post("/api/v1/mail/test", json={"to": "hoca@uni.edu.tr"}, headers=h)).json()
    assert out["ok"] is True, out
    assert sink.auth_seen == ["XOAUTH2"] and "C: AUTH XOAUTH2 ********" in out["transcript"]
    url, data = calls[0]
    assert url.startswith("https://login.microsoftonline.com/3f2a8c1e-") and data["grant_type"] == "client_credentials"
    assert data["scope"] == "https://outlook.office365.com/.default"
    assert token not in str(out) and "client-secret-value" not in str(out)
    settings = (await client.get("/api/v1/mail/settings", headers=h)).json()
    assert settings["oauth_client_secret"]["set"] is True and "client-secret-value" not in str(settings)


async def test_unconfigured_test_answers_unsent(client) -> None:  # noqa: F811
    h = await _admin(client)
    out = (await client.post("/api/v1/mail/test", json={"to": "hoca@uni.edu.tr"}, headers=h)).json()
    assert out["status"] == "UNSENT" and "SMTP" in out["hint_tr"]
    assert (await client.get("/api/v1/mail/status", headers=h)).json()["state"] == "not_configured"


async def test_template_overrides_preview_and_test_send(client, sink) -> None:  # noqa: F811
    h = await _admin(client)
    await _configure(client, h)
    lst = (await client.get("/api/v1/mail/templates", headers=h)).json()
    rej = next(t for t in lst if t["kind"] == "approval_rejected")
    assert (
        rej["shipped"]["tr"]["subject"].startswith("Oda talebiniz reddedildi")
        and rej["overrides"]["tr"]["subject"] is None
    )
    assert "reason" in rej["placeholders"]
    # preview with an unsaved draft
    p = await client.post(
        "/api/v1/mail/templates/approval_rejected/preview",
        json={"locale": "tr", "subject": "Talebiniz\xa0uygun değil: {what}"},
        headers=h,
    )
    assert p.status_code == 200 and p.json()["subject"].startswith("Talebiniz uygun değil: A 201")
    assert "<table" in p.json()["html"] and p.json()["text"]
    bad = await client.post(
        "/api/v1/mail/templates/approval_rejected/preview", json={"locale": "tr", "subject": "{nope}"}, headers=h
    )
    assert bad.status_code == 422 and "nope" in bad.json()["detail"]["message_tr"]
    # save, read back, it is a translations row (the CRBS override mechanism) and reaches /org/i18n
    s = await client.put(
        "/api/v1/mail/templates/approval_rejected", json={"locale": "tr", "subject": "Reddedildi: {what}"}, headers=h
    )
    assert s.status_code == 200 and s.json()["overrides"]["tr"]["subject"] == "Reddedildi: {what}"
    tr = (await client.get("/api/v1/org/translations", params={"language": "tr"}, headers=h)).json()
    assert any(t["key"] == "approval_rejected.subject" and t["set"] == "email" for t in tr)
    # test send of the template with sample data
    t = (
        await client.post(
            "/api/v1/mail/templates/approval_rejected/test", json={"locale": "en", "to": "hoca@uni.edu.tr"}, headers=h
        )
    ).json()
    assert t["ok"] is True
    got = sink.messages[-1].message
    assert str(got["Subject"]).startswith("[Deneme / Test] Your room request was declined")
    assert "Not enough seats" in got.get_body(preferencelist=("plain",)).get_content()
    # "" restores the shipped text
    s = await client.put("/api/v1/mail/templates/approval_rejected", json={"locale": "tr", "subject": ""}, headers=h)
    assert s.json()["overrides"]["tr"]["subject"] is None
    assert (await client.get("/api/v1/mail/templates/x", headers=h)).status_code in (404, 405)
    assert (
        await client.post("/api/v1/mail/templates/nope/preview", json={"locale": "tr"}, headers=h)
    ).status_code == 404


async def test_test_row_is_in_the_outbox(client, sink) -> None:  # noqa: F811
    h = await _admin(client)
    await _configure(client, h)
    await client.post("/api/v1/mail/test", json={"to": "hoca@uni.edu.tr"}, headers=h)
    from app.core import db as dbmod

    async with dbmod.get_session_factory()() as s:
        row = (await s.execute(select(NotificationOutbox).where(NotificationOutbox.kind == "smtp_test"))).scalar_one()
    assert row.status == "SENT" and row.to_email == "hoca@uni.edu.tr" and row.locale == "tr"


async def test_hub_card(client, sink) -> None:  # noqa: F811
    from app.core import db as dbmod
    from app.services.mail_status import integration_status

    h = await _admin(client)
    async with dbmod.get_session_factory()() as s:
        (card,) = await integration_status(s)
    assert card["status"] == "not_configured" and card["key"] == "email.smtp"
    await _configure(client, h)
    async with dbmod.get_session_factory()() as s:
        (card,) = await integration_status(s)
    assert card["status"] == "connected" and "Henüz deneme" in card["detail_tr"] and card["changed_at"]
    r = (await client.get("/api/v1/integrations/status", headers=h)).json()
    email = next(a for a in r["areas"] if a["key"] == "email")
    assert email["cards"][0]["source"] == "contract" and email["cards"][0]["status"] == "connected"


async def test_providers_abroad_need_the_kvkk_acknowledgement(client) -> None:  # noqa: F811
    h = await _admin(client)
    body = {"provider": "amazon_ses", "host": "email-smtp.eu-central-1.amazonaws.com", "from_address": "b@uni.edu.tr"}
    r = await client.put("/api/v1/mail/settings", json=body, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "abroad_ack_required"
    assert "KVKK md. 9" in r.json()["detail"]["message_tr"]
    r = await client.put("/api/v1/mail/settings", json={**body, "abroad_ack": True}, headers=h)
    assert r.status_code == 200, r.text
    ack = r.json()["abroad_ack"]
    assert ack["provider"] == "amazon_ses" and ack["by"] and ack["at"]
    # kept: a later edit of the same provider needs no new tick; another provider abroad does
    assert (await client.put("/api/v1/mail/settings", json={"from_name": "X"}, headers=h)).status_code == 200
    r = await client.put("/api/v1/mail/settings", json={"provider": "postmark"}, headers=h)
    assert r.status_code == 422
    presets = {p["id"]: p for p in (await client.get("/api/v1/mail/presets", headers=h)).json()}
    assert presets["resend"]["abroad"] and presets["brevo"]["abroad"] and not presets["yandex"]["abroad"]
    assert presets["google_relay"]["host"] == "smtp-relay.gmail.com"
    assert "MC786329" in presets["microsoft365_oauth2"]["notes_tr"]


async def test_waiting_mail_can_be_sent_after_setup(client, sink) -> None:  # noqa: F811
    from app.core import db as dbmod
    from app.services import bookings_notify

    h = await _admin(client)
    async with dbmod.get_session_factory()() as s:
        await bookings_notify.notify(s, kind="booking_created", to_email="hoca@uni.edu.tr", subject="S", body="B")
        await bookings_notify.notify(s, kind="password_reset", to_email="hoca@uni.edu.tr", subject="S", body="x")
        await s.commit()
    await _configure(client, h)
    st = (await client.get("/api/v1/mail/settings", headers=h)).json()
    assert st["unsent"] == 1  # the reset code is never re-sent
    r = (await client.post("/api/v1/mail/outbox/requeue", json={}, headers=h)).json()
    assert r["queued"] == 1 and r["unsent"] == 0
    from app.workers import integrations as worker

    await worker.wait_idle()
    await worker.shutdown()
    assert [m.rcpts for m in sink.messages] == [["hoca@uni.edu.tr"]]


def test_microsoft_basic_auth_refusal_is_translated() -> None:
    import smtplib

    from app.services import mail

    exc = smtplib.SMTPAuthenticationError(535, b"5.7.139 Authentication unsuccessful, basic authentication is disabled")
    tr, en = mail.explain(exc, {"provider": "microsoft365_oauth2"})
    assert "OAuth 2.0" in tr and "OAuth 2.0" in en
    tr, _ = mail.explain(
        smtplib.SMTPDataError(550, b"5.7.60 SMTP; Client does not have permissions to send as this sender"),
        {"from_address": "b@uni.edu.tr"},
    )
    assert "b@uni.edu.tr adresiyle gönderemiyor" in tr


async def test_send_kind_is_the_entry_point_for_other_lanes(client, sink) -> None:  # noqa: F811
    """W3-IDP / W3-SEC send their kinds with one call; the queued mail keeps the words, the HTML is themed."""
    from app.core import db as dbmod
    from app.models import User
    from app.services import mail
    from app.workers import integrations as worker

    h = await _admin(client)
    await _configure(client, h)
    async with dbmod.get_session_factory()() as s:
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        row = await mail.send_kind(
            s,
            "invitation",
            to_email="yeni.hoca@uni.edu.tr",
            user=None,
            locale="tr",
            link="/login?invite=abc",
            inviter=admin.full_name or "Yönetici",
            provider="microsoft",
            expires="16 Kasım 2026",
        )
        await s.commit()
    assert (
        row.kind == "invitation"
        and "davet etti" in row.body
        and "--" not in row.body
        and row.link == "/login?invite=abc"
    )
    await worker.wait_idle()
    await worker.shutdown()
    msg = sink.messages[-1].message
    assert str(msg["Subject"]).endswith("sizi SmartSched'e davet etti")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "davet etti" in html and '<html lang="tr"' in html and 'data-role="preheader"' in html
