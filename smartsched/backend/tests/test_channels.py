"""Notification channels ("Bildirim kanalları"): admin configuration, KVKK gate, user linking, SSRF, secrets.

Owner decision 2026-10-15 (docs/product/2026-10-15-integrations-options.md): the institution owns one sender per
service, users link only an address, nothing is sent before an administrator configured the channel and the KVKK
officer signed it off. Every network boundary is faked (tests/test_channels_support.py).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from app.core import db as dbmod
from app.models import ChannelDelivery, ChannelLinkCode, NotifyChannelConfig, Program, UserChannel
from sqlalchemy import select, update

from tests.api_fixtures import client, login  # noqa: F401
from tests.crbs_support import make_user
from tests.test_channels_support import (
    BOT_TOKEN,
    LEGAL,
    OFFICER,
    SLACK_URL,
    TEAMS_URL,
    TWILIO_SID,
    TWILIO_TOKEN,
    WA_TOKEN,
    drain,
    enable,
    enable_telegram,
    link_telegram,
    net,  # noqa: F401
)

ADMIN = "/api/v1/channels/admin"
ME = "/api/v1/me/channels"
FCM = "https://fcm.googleapis.com/fcm/send/dXk3ZC1hYmM6QVBBOTFiRjQ"
# a real P-256 public key and auth secret shape (base64url), as PushManager.subscribe() returns them
P256DH = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
AUTH = "tBHItJI5svbpez7KI4CCXg"


async def _teacher(client, admin, email="ayse.yilmaz@uni.edu.tr", **extra):  # type: ignore[no-untyped-def]  # noqa: F811
    return await make_user(client, admin, email, firstname="Ayşe", lastname="Yılmaz", **extra)


async def _rows(model, **where):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        q = select(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return list((await s.execute(q)).scalars())


def _channel(listing: dict, kind: str) -> dict:  # type: ignore[type-arg]
    return next(c for c in listing["channels"] if c["kind"] == kind)


# --------------------------------------------------------------------------------------------------
# admin configuration and the KVKK gate
# --------------------------------------------------------------------------------------------------


async def test_every_channel_is_off_until_an_admin_configures_it_and_the_kvkk_officer_signs_off(client, net):  # noqa: F811
    admin = await login(client)
    _, ayse = await _teacher(client, admin)
    listing = (await client.get(ADMIN, headers=admin)).json()
    assert {c["kind"] for c in listing["channels"]} == {
        "webpush",
        "telegram",
        "whatsapp",
        "whatsapp_web",
        "sms",
        "teams",
        "slack",
    }
    assert all(c["enabled"] is False and c["configured"] is False for c in listing["channels"])
    assert all(c["content_mode"] == "link_only" for c in listing["channels"])  # strictest default
    assert (await client.get(ADMIN, headers=ayse)).status_code == 403
    assert (await client.get(ME, headers=ayse)).json()["available"] == []
    r = await client.post(f"{ME}/telegram/link", headers=ayse)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "channel_off", r.text

    # credentials and the switch without a sign-off: still off
    out = await enable_telegram(client, admin, sign=False)
    assert out["configured"] is True and out["enabled_requested"] is True
    assert out["enabled"] is False and "kvkk_signoff" in out["missing"]
    assert (await client.post(f"{ME}/telegram/link", headers=ayse)).status_code == 409
    # a sign-off needs the legal basis
    bad = await client.put(
        f"{ADMIN}/telegram", json={"kvkk_signoff": {"signed": True, "officer": OFFICER}}, headers=admin
    )
    assert bad.status_code == 422, bad.text
    out = await enable_telegram(client, admin)
    assert out["enabled"] is True and out["missing"] == []
    signoff = out["kvkk_signoff"]
    assert signoff["by"] and signoff["by_user_id"] and signoff["at"] and signoff["legal_basis"] == LEGAL
    assert signoff["officer"] == OFFICER and signoff["channel"] == "telegram"
    assert [c["kind"] for c in (await client.get(ME, headers=ayse)).json()["available"]] == ["telegram"]
    # withdrawing the sign-off switches the channel off again
    r = await client.put(f"{ADMIN}/telegram", json={"kvkk_signoff": {"signed": False}}, headers=admin)
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert (await client.post(f"{ME}/telegram/link", headers=ayse)).status_code == 409
    # an unknown channel, an unknown secret name and a bad content mode are 422 / 404
    assert (await client.put(f"{ADMIN}/signal", json={"enabled": True}, headers=admin)).status_code == 404
    r = await client.put(f"{ADMIN}/telegram", json={"secrets": {"password": "x"}}, headers=admin)
    assert r.status_code == 422
    r = await client.put(f"{ADMIN}/telegram", json={"content_mode": "hepsi"}, headers=admin)
    assert r.status_code == 422
    # Turkish keyboard / NBSP input of a code is normalised (ASCII codes are never Turkish-lower-cased: I -> ı)
    r = await client.put(f"{ADMIN}/telegram", json={"content_mode": "LINK_ONLY "}, headers=admin)
    assert r.status_code == 200 and r.json()["content_mode"] == "link_only", r.text


async def test_secrets_are_encrypted_never_returned_and_never_logged(client, net, caplog):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    out = await enable_telegram(client, admin)
    assert out["secrets"] == {"bot_token": True, "webhook_secret": True}
    listing = await client.get(ADMIN, headers=admin)
    assert BOT_TOKEN not in listing.text and BOT_TOKEN[:12] not in listing.text
    (row,) = await _rows(NotifyChannelConfig, kind="telegram")
    assert row.secrets_enc and BOT_TOKEN not in row.secrets_enc and BOT_TOKEN not in str(row.options)
    # a failing send: Apprise logs the URL with the token; neither the log nor the delivery log keeps it
    await link_telegram(client, net, ayse)
    net.apprise_ok = False
    caplog.set_level(logging.DEBUG)
    r = await client.post(f"{ME}/{(await client.get(ME, headers=ayse)).json()['linked'][0]['id']}/test", headers=ayse)
    assert r.status_code == 202, r.text
    await drain()
    assert net.sent and BOT_TOKEN.split(":")[1] in net.sent[-1][0]  # the real token reached the transport
    assert BOT_TOKEN not in caplog.text and BOT_TOKEN.split(":")[1] not in caplog.text
    (dl,) = await _rows(ChannelDelivery, user_id=aid, event="channel.test")
    assert dl.status == "PENDING" and dl.attempts == 1 and dl.last_error  # retried later
    assert BOT_TOKEN not in dl.last_error and BOT_TOKEN.split(":")[1] not in dl.last_error
    log = await client.get(f"{ADMIN}/deliveries", headers=admin)
    assert log.status_code == 200 and BOT_TOKEN not in log.text and "5550001" not in log.text


# --------------------------------------------------------------------------------------------------
# Telegram: one-time deep link
# --------------------------------------------------------------------------------------------------


async def test_telegram_deep_link_nonce_links_the_chat_once_and_expires(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    bid, burak = await make_user(client, admin, "burak.celik@uni.edu.tr", firstname="Burak", lastname="Çelik")
    await enable_telegram(client, admin)
    r = await client.post(f"{ME}/telegram/link", headers=ayse)
    assert r.status_code == 201, r.text
    link = r.json()["deep_link"]
    m = re.fullmatch(r"https://t\.me/SmartSchedUniBot\?start=([A-Za-z0-9_-]{16,64})", link)
    assert m, link
    code = m.group(1)
    (row,) = await _rows(ChannelLinkCode, user_id=aid)
    assert row.code_hash != code and code not in row.code_hash  # stored as an HMAC only
    async with dbmod.get_session_factory()() as s:
        from app.services.channels import config

        secret = (await config.load(s, "telegram")).secrets["webhook_secret"]
    hook = "/api/v1/channels/telegram/webhook"

    def upd(text: str, chat: int = 5550001, kind: str = "private") -> dict:  # type: ignore[type-arg]
        return {"update_id": 9, "message": {"message_id": 3, "chat": {"id": chat, "type": kind}, "text": text}}

    # Telegram's secret header is required
    assert (await client.post(hook, json=upd(f"/start {code}"))).status_code == 401
    r = await client.post(
        hook, json=upd(f"/start {code}"), headers={"X-Telegram-Bot-Api-Secret-Token": "yanlis-gizli-anahtar"}
    )
    assert r.status_code == 401
    ok = {"X-Telegram-Bot-Api-Secret-Token": secret}
    # a group chat cannot be linked as a person's address
    r = await client.post(hook, json=upd(f"/start {code}", chat=-100200, kind="group"), headers=ok)
    assert r.status_code == 200 and await _rows(UserChannel, user_id=aid) == []
    r = await client.post(hook, json=upd(f"/start@SmartSchedUniBot {code}"), headers=ok)
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "sendMessage" and "Bağlandı" in r.json()["text"]  # replied in the webhook response
    (ch,) = await _rows(UserChannel, user_id=aid)
    assert ch.kind == "telegram" and ch.status == "active" and "5550001" not in ch.address_enc
    mine = (await client.get(ME, headers=ayse)).json()["linked"]
    assert [(x["kind"], x["status"]) for x in mine] == [("telegram", "active")] and "5550001" not in str(mine)
    # the nonce is single use: replayed for another chat it links nothing
    r = await client.post(hook, json=upd(f"/start {code}", chat=5550002), headers=ok)
    assert r.status_code == 200 and "geçersiz" in r.json()["text"].lower()
    assert len(await _rows(UserChannel, kind="telegram")) == 1
    # an expired nonce links nothing
    r = await client.post(f"{ME}/telegram/link", headers=burak)
    code2 = r.json()["deep_link"].split("start=")[1]
    async with dbmod.get_session_factory()() as s:
        await s.execute(
            update(ChannelLinkCode).where(ChannelLinkCode.user_id == bid).values(expires_at=datetime(2020, 1, 1))
        )
        await s.commit()
    await client.post(hook, json=upd(f"/start {code2}", chat=5550003), headers=ok)
    assert await _rows(UserChannel, user_id=bid) == []
    # /stop marks the address blocked (nothing is sent to it any more)
    await client.post(hook, json=upd("/stop"), headers=ok)
    (ch,) = await _rows(UserChannel, user_id=aid)
    assert ch.status == "blocked"


async def test_telegram_long_poll_mode_completes_the_link_without_an_inbound_webhook(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    await enable_telegram(client, admin)
    r = await client.put(f"{ADMIN}/telegram", json={"options": {"update_mode": "poll"}}, headers=admin)
    assert r.status_code == 200 and r.json()["options"]["update_mode"] == "poll"
    setup = await client.post(f"{ADMIN}/telegram/setup", headers=admin)
    assert setup.status_code == 200 and setup.json()["bot_username"] == "SmartSchedUniBot", setup.text
    assert setup.json()["webhook_set"] is False and net.telegram_calls("setWebhook") == []
    code = (await client.post(f"{ME}/telegram/link", headers=ayse)).json()["deep_link"].split("start=")[1]
    assert (await client.post(f"{ME}/telegram/check", headers=ayse)).json()["linked"] is False
    net.telegram_updates = [
        {
            "update_id": 41,
            "message": {"message_id": 1, "chat": {"id": 5550009, "type": "private"}, "text": f"/start {code}"},
        }
    ]
    r = await client.post(f"{ME}/telegram/check", headers=ayse)
    assert r.status_code == 200 and r.json()["linked"] is True, r.text
    assert net.telegram_calls("getUpdates")[-1]["offset"] == 0
    await client.post(f"{ME}/telegram/check", headers=ayse)
    assert net.telegram_calls("getUpdates")[-1]["offset"] == 42  # confirmed updates are not fetched again
    # webhook mode: setup registers the webhook with Telegram's secret header
    await client.put(f"{ADMIN}/telegram", json={"options": {"update_mode": "webhook"}}, headers=admin)
    await client.put(
        "/api/v1/calendar/admin/settings", json={"public_url": "https://smartsched.uni.edu.tr"}, headers=admin
    )
    setup = await client.post(f"{ADMIN}/telegram/setup", headers=admin)
    assert setup.json()["webhook_set"] is True, setup.text
    (call,) = net.telegram_calls("setWebhook")
    assert call["url"] == "https://smartsched.uni.edu.tr/api/v1/channels/telegram/webhook"
    assert len(call["secret_token"]) >= 32 and call["secret_token"] not in setup.text
    assert BOT_TOKEN not in setup.text


# --------------------------------------------------------------------------------------------------
# SMS / WhatsApp: phone verified by a one-time code sent through the channel
# --------------------------------------------------------------------------------------------------


async def test_sms_phone_is_verified_by_a_code_sent_through_the_channel(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    await enable(
        client,
        admin,
        "sms",
        secrets={"account_sid": TWILIO_SID, "auth_token": TWILIO_TOKEN},
        options={"provider": "twilio", "from_number": "+1 555 123 4567"},
    )
    for bad in ("12", "0532 111 22", "+90 532 111 22 33 44 55 66", "telefonum"):
        r = await client.post(f"{ME}/sms/link", json={"phone": bad}, headers=ayse)
        assert r.status_code == 422, (bad, r.text)
    # Turkish spelling of a mobile number: leading 0, spaces, NBSP, parentheses
    r = await client.post(f"{ME}/sms/link", json={"phone": "0 (532) 111 22 33"}, headers=ayse)
    assert r.status_code == 201, r.text
    assert r.json()["display_hint"] == "+90 5•• ••• •• 33"
    assert await _rows(UserChannel, user_id=aid) == []  # nothing linked before the code comes back
    assert await drain() == 1
    ((url, _title, body),) = net.sent
    assert url.startswith("twilio://") and "%2B905321112233" in url
    code = re.search(r"\b(\d{6})\b", body).group(1)  # type: ignore[union-attr]
    assert "SmartSched" in body
    (dl,) = await _rows(ChannelDelivery, user_id=aid)
    assert code not in str(dl.payload)  # the code is encrypted in the outbox
    # wrong code, then the right one typed with a space and an NBSP
    wrong = "000000" if code != "000000" else "111111"
    r = await client.post(f"{ME}/sms/verify", json={"code": wrong}, headers=ayse)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "code_invalid"
    r = await client.post(f"{ME}/sms/verify", json={"code": f" {code[:3]} {code[3:]} "}, headers=ayse)
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "sms" and r.json()["display_hint"] == "+90 5•• ••• •• 33"
    (ch,) = await _rows(UserChannel, user_id=aid)
    assert "5321112233" not in ch.address_enc and ch.verified_at is not None
    # the code is single use
    r = await client.post(f"{ME}/sms/verify", json={"code": code}, headers=ayse)
    assert r.status_code == 422


async def test_phone_code_is_burned_after_five_wrong_attempts(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    await enable(
        client,
        admin,
        "sms",
        secrets={"account_sid": TWILIO_SID, "auth_token": TWILIO_TOKEN},
        options={"provider": "twilio", "from_number": "+15551234567"},
    )
    await client.post(f"{ME}/sms/link", json={"phone": "+90 532 111 22 33"}, headers=ayse)
    await drain()
    code = re.search(r"\b(\d{6})\b", net.sent[-1][2]).group(1)  # type: ignore[union-attr]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (await client.post(f"{ME}/sms/verify", json={"code": wrong}, headers=ayse)).status_code == 422
    r = await client.post(f"{ME}/sms/verify", json={"code": code}, headers=ayse)
    assert r.status_code == 422 and r.json()["detail"]["code"] in ("code_expired", "code_invalid")
    assert await _rows(UserChannel, user_id=aid) == []


async def test_whatsapp_link_needs_the_opt_in_and_sends_the_code_with_the_approved_template(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    await enable(
        client,
        admin,
        "whatsapp",
        secrets={"access_token": WA_TOKEN},
        options={
            "phone_number_id": "123456789012345",
            "template_notice": "smartsched_notice",
            "template_code": "smartsched_code",
        },
    )
    avail = (await client.get(ME, headers=ayse)).json()["available"]
    wa = next(a for a in avail if a["kind"] == "whatsapp")
    assert wa["link"] == "phone_code" and "WhatsApp" in wa["opt_in_tr"] and wa["opt_in_en"]
    r = await client.post(f"{ME}/whatsapp/link", json={"phone": "0532 111 22 33"}, headers=ayse)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "consent_required"
    r = await client.post(f"{ME}/whatsapp/link", json={"phone": "0532 111 22 33", "consent": True}, headers=ayse)
    assert r.status_code == 201, r.text
    await drain()
    ((url, _t, body),) = net.sent
    assert url.startswith("whatsapp://smartsched_code:") and "lang=tr" in url and "905321112233" in url
    code = re.search(r"\b(\d{6})\b", body).group(1)  # type: ignore[union-attr]
    r = await client.post(f"{ME}/whatsapp/verify", json={"code": code}, headers=ayse)
    assert r.status_code == 200 and r.json()["kind"] == "whatsapp", r.text


# --------------------------------------------------------------------------------------------------
# Web Push: VAPID generated once on the server, browser subscription stored
# --------------------------------------------------------------------------------------------------


async def test_webpush_vapid_is_generated_once_and_push_goes_encrypted_to_an_allowlisted_service(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    r = await client.post(f"{ADMIN}/webpush/vapid", json={}, headers=admin)
    assert r.status_code == 200, r.text
    public = r.json()["options"]["vapid_public_key"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{86,88}", public) and r.json()["secrets"] == {"vapid_private_key": True}
    again = await client.post(f"{ADMIN}/webpush/vapid", json={}, headers=admin)
    assert again.json()["options"]["vapid_public_key"] == public  # generated once
    assert "PRIVATE" not in again.text
    out = await enable(client, admin, "webpush", options={"contact": "bilgi-islem@uni.edu.tr"})
    assert out["enabled"] is True and out["options"]["contact"] == "mailto:bilgi-islem@uni.edu.tr"
    avail = (await client.get(ME, headers=ayse)).json()["available"]
    assert avail == [{**avail[0], "kind": "webpush", "link": "webpush", "vapid_public_key": public}]
    sub = {"endpoint": FCM, "keys": {"p256dh": P256DH, "auth": AUTH}}
    # forged endpoints: not a push service, a private address, plain http, metadata
    for endpoint in (
        "https://evil.example.com/push/1",
        "https://10.0.0.7/push",
        "http://fcm.googleapis.com/fcm/send/x",
        "https://169.254.169.254/latest",
        "https://fcm.googleapis.com.evil.example.com/x",
    ):
        r = await client.post(ME + "/webpush", json={"subscription": {**sub, "endpoint": endpoint}}, headers=ayse)
        assert r.status_code == 422, (endpoint, r.text)
    net.dns["updates.push.services.mozilla.com"] = ["10.1.2.3"]  # an allowlisted name resolving inside the pod
    r = await client.post(
        ME + "/webpush",
        json={"subscription": {**sub, "endpoint": "https://updates.push.services.mozilla.com/wpush/v2/x"}},
        headers=ayse,
    )
    assert r.status_code == 422, r.text
    r = await client.post(
        ME + "/webpush", json={"subscription": {**sub, "keys": {"p256dh": "kısa", "auth": AUTH}}}, headers=ayse
    )
    assert r.status_code == 422
    r = await client.post(ME + "/webpush", json={"subscription": sub, "label": "Telefonum"}, headers=ayse)
    assert r.status_code == 201 and r.json()["display_hint"] == "fcm.googleapis.com", r.text
    # the same browser again: still one address
    r2 = await client.post(ME + "/webpush", json={"subscription": sub}, headers=ayse)
    assert r2.status_code == 201 and r2.json()["id"] == r.json()["id"]
    await client.post(f"{ME}/{r.json()['id']}/test", headers=ayse)
    await drain()
    (req,) = [q for q in net.requests if q.url.host == "fcm.googleapis.com"]
    assert req.headers["content-encoding"] == "aes128gcm" and req.headers["authorization"].startswith("vapid t=")
    assert f"k={public}" in req.headers["authorization"] and int(req.headers["ttl"]) > 0
    assert b"SmartSched" not in req.content  # end-to-end encrypted (RFC 8291)
    # the push service says the subscription is gone: the address is deleted
    net.push_status = 410
    await client.post(f"{ME}/{r.json()['id']}/test", headers=ayse)
    await drain()
    assert await _rows(UserChannel, user_id=aid) == []


# --------------------------------------------------------------------------------------------------
# unlink
# --------------------------------------------------------------------------------------------------


async def test_unlink_deletes_the_address_and_what_was_waiting_for_it(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    _, burak = await make_user(client, admin, "burak.celik@uni.edu.tr")
    await enable_telegram(client, admin)
    await link_telegram(client, net, ayse)
    (linked,) = (await client.get(ME, headers=ayse)).json()["linked"]
    assert (await client.post(f"{ME}/{linked['id']}/test", headers=ayse)).status_code == 202
    assert len(await _rows(ChannelDelivery, user_id=aid)) == 1
    # someone else's channel is not theirs to remove
    assert (await client.delete(f"{ME}/{linked['id']}", headers=burak)).status_code == 404
    r = await client.delete(f"{ME}/{linked['id']}", headers=ayse)
    assert r.status_code == 204
    assert await _rows(UserChannel, user_id=aid) == []
    assert await _rows(ChannelDelivery, user_id=aid) == []  # the queued test went with the address
    assert await drain() == 0 and net.sent == []
    assert (await client.get(ME, headers=ayse)).json()["linked"] == []
    from app.models import AuditEvent

    actions = [e.action for e in await _rows(AuditEvent) if e.action.startswith("channel.")]
    assert "channel.link" in actions and "channel.unlink" in actions


# --------------------------------------------------------------------------------------------------
# Teams / Slack: department channel webhooks through the SSRF guard and the vendor allowlist
# --------------------------------------------------------------------------------------------------


async def test_department_webhooks_refuse_urls_outside_the_vendor_allowlist_and_private_addresses(client, net):  # noqa: F811
    admin = await login(client)
    async with dbmod.get_session_factory()() as s:
        dept = Program(name="Psikoloji", canonical_name="psikoloji")
        s.add(dept)
        await s.commit()
        dept_id = dept.id
    await enable(client, admin, "teams")
    await enable(client, admin, "slack")
    url = f"{ADMIN}/teams/departments/{dept_id}"
    refused = (
        "https://evil.example.com/workflows/abc/triggers/manual/paths/invoke?sig=x",  # not a Workflows host
        "http://prod-12.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sig=x",  # plain http
        "https://127.0.0.1/workflows/abc/triggers/manual/paths/invoke?sig=x",
        "https://logic.azure.com.evil.example.com/workflows/abc/triggers/manual/paths/invoke?sig=x",
        "https://user:pw@prod-1.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sig=x",
        SLACK_URL,  # a Slack URL is not a Teams target
    )
    for bad in refused:
        r = await client.put(url, json={"url": bad}, headers=admin)
        assert r.status_code == 422, (bad, r.text)
    net.dns["prod-66.westeurope.logic.azure.com"] = ["169.254.169.254"]  # allowlisted name, metadata address
    r = await client.put(url, json={"url": TEAMS_URL.replace("prod-12", "prod-66")}, headers=admin)
    assert r.status_code == 422 and "blocked" in r.text.lower()
    r = await client.put(url, json={"url": " " + TEAMS_URL + " "}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["host"] == "prod-12.westeurope.logic.azure.com" and "sig=" not in r.text
    for bad in (
        "https://hooks.slack.com.evil.example.com/services/T/B/C",
        "https://slack.com/api/chat.postMessage",
        "https://hooks.slack.com/services/T0123ABCD",  # not an incoming-webhook URL Apprise can use
    ):
        r = await client.put(f"{ADMIN}/slack/departments/{dept_id}", json={"url": bad}, headers=admin)
        assert r.status_code == 422, (bad, r.text)
    r = await client.put(f"{ADMIN}/slack/departments/{dept_id}", json={"url": SLACK_URL}, headers=admin)
    assert r.status_code == 200, r.text
    listing = await client.get(f"{ADMIN}/departments", headers=admin)
    assert {(t["kind"], t["department"]) for t in listing.json()} == {("teams", "Psikoloji"), ("slack", "Psikoloji")}
    assert "fakeSlackHookPart" not in listing.text and "fakeSignature" not in listing.text
    (row,) = [
        t for t in await _rows(__import__("app.models", fromlist=["x"]).ChannelDepartmentTarget) if t.kind == "slack"
    ]
    assert "fakeSlackHookPart" not in row.url_enc
    assert (await client.delete(f"{ADMIN}/slack/departments/{dept_id}", headers=admin)).status_code == 204


# --------------------------------------------------------------------------------------------------
# WhatsApp Web bridge (optional, unofficial protocol): off by default, explicit risk acknowledgement
# --------------------------------------------------------------------------------------------------


async def test_whatsapp_web_bridge_needs_the_risk_acknowledgement_and_an_admin_qr_link(client, net):  # noqa: F811
    admin = await login(client)
    aid, ayse = await _teacher(client, admin)
    out = await enable(client, admin, "whatsapp_web", secrets={"user_token": "bridge-user-token-0123456789"})
    assert out["enabled"] is False and "risk_ack" in out["missing"], out
    assert "ban" in out["risk_tr"].lower() or "yasak" in out["risk_tr"].lower()
    r = await client.put(f"{ADMIN}/whatsapp_web", json={"risk_ack": True}, headers=admin)
    assert r.status_code == 200 and r.json()["risk_ack"]["by_user_id"]
    assert r.json()["enabled"] is False and r.json()["missing"] == ["bridge_session"]
    qr = await client.post(f"{ADMIN}/whatsapp_web/connect", headers=admin)
    assert qr.status_code == 200 and qr.json()["qr"].startswith("data:image/png;base64,"), qr.text
    assert qr.json()["logged_in"] is False
    net.bridge_logged_in = True
    st = await client.get(f"{ADMIN}/whatsapp_web/status", headers=admin)
    assert st.json() == {"reachable": True, "connected": True, "logged_in": True}
    assert (await client.get(ADMIN, headers=admin)).json()["channels"][3]["kind"] == "whatsapp_web"
    out = _channel((await client.get(ADMIN, headers=admin)).json(), "whatsapp_web")
    assert out["enabled"] is True and out["missing"] == []
    # users link "WhatsApp" once; the code goes through the bridge when the Cloud API is not configured
    r = await client.post(f"{ME}/whatsapp/link", json={"phone": "+90 532 111 22 33", "consent": True}, headers=ayse)
    assert r.status_code == 201, r.text
    await drain()
    (send,) = [q for q in net.requests if q.url.path == "/chat/send/text"]
    assert send.headers["token"] == "bridge-user-token-0123456789"
    import json as _json

    payload = _json.loads(send.content)
    assert payload["Phone"] == "905321112233" and re.search(r"\b\d{6}\b", payload["Body"])
    assert re.fullmatch(r"[0-9A-F]{32}", payload["Id"])  # deterministic: a retry reuses the message id
    assert net.sent == []  # Apprise not involved
    _ = aid
