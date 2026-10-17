"""Security follow-up (wave3-sec2, owner request): the RFC 9116 security.txt is set per institution in the admin panel.

Settings ``security.contact_email`` (required once set, an e-mail), ``security.contact_url`` / ``security.policy_url``
(optional, https) and ``security.preferred_languages`` (default "tr, en"), written only by administrators through
``PUT /api/v1/admin/security-contact`` and audited. The backend serves ``/.well-known/security.txt`` and
``/security.txt`` from them: Contact, Expires one year ahead (regenerated on every request), Preferred-Languages,
Canonical with the request host, Policy if set. While unset it falls back to ``security@<host>`` and the admin card
warns "Güvenlik iletişim adresi ayarlanmadı".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core import db as dbmod
from app.models import AuditEvent
from app.services import settings_service as ss
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent
NGINX = (BACKEND.parent / "deploy/nginx/default.conf").read_text(encoding="utf-8")
URL = "/api/v1/admin/security-contact"


def _fields(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition(": ")
            out.setdefault(k, []).append(v)
    return out


def test_settings_keys_are_registered() -> None:
    for key in ("security.contact_email", "security.contact_url", "security.policy_url"):
        assert key in ss.SPECS
    assert ss.SPECS["security.preferred_languages"].default == "tr, en"


async def test_unset_falls_back_to_the_host_and_warns_the_admin(client):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await client.get("/.well-known/security.txt", headers={"host": "planlama.uni.edu.tr"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    f = _fields(r.text)
    assert f["Contact"] == ["mailto:security@planlama.uni.edu.tr"]
    assert f["Preferred-Languages"] == ["tr, en"]
    assert f["Canonical"] == ["http://planlama.uni.edu.tr/.well-known/security.txt"]
    assert "Policy" not in f
    expires = datetime.fromisoformat(f["Expires"][0].replace("Z", "+00:00"))
    assert timedelta(days=360) < expires - datetime.now(UTC) <= timedelta(days=366)
    # /security.txt answers the same file
    r2 = await client.get("/security.txt", headers={"host": "planlama.uni.edu.tr"})
    assert r2.status_code == 200 and _fields(r2.text)["Contact"] == f["Contact"]
    # a hostile Host header cannot inject lines
    r3 = await client.get("/.well-known/security.txt", headers={"host": "evil.example\r\nPolicy: x"})
    assert "Policy" not in _fields(r3.text)

    h = await login(client)
    view = (await client.get(URL, headers=h)).json()
    assert view["configured"] is False
    assert view["warning"]["message_tr"] == "Güvenlik iletişim adresi ayarlanmadı"
    assert view["preferred_languages"] == "tr, en" and view["last_change"] is None


async def test_admin_sets_the_contact_and_it_is_served_and_audited(client):  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    body = {
        "contact_email": "bilgi-guvenligi@uni.edu.tr",
        "contact_url": "https://uni.edu.tr/guvenlik",
        "policy_url": "https://uni.edu.tr/guvenlik/politika",
        "preferred_languages": "tr, en",
    }
    r = await client.put(URL, json=body, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["configured"] is True and out["warning"] is None
    assert out["last_change"]["actor"] and out["last_change"]["at"]
    f = _fields((await client.get("/.well-known/security.txt", headers={"host": "planlama.uni.edu.tr"})).text)
    assert f["Contact"] == ["mailto:bilgi-guvenligi@uni.edu.tr", "https://uni.edu.tr/guvenlik"]
    assert f["Policy"] == ["https://uni.edu.tr/guvenlik/politika"]
    async with dbmod.get_session_factory()() as s:
        events = list((await s.execute(select(AuditEvent).where(AuditEvent.action == "security.contact"))).scalars())
        assert events and events[-1].after["contact_email"] == "bilgi-guvenligi@uni.edu.tr"
    # clearing an optional field removes the line
    r = await client.put(URL, json={**body, "policy_url": ""}, headers=h)
    assert r.status_code == 200 and r.json()["policy_url"] in (None, "")
    assert "Policy" not in _fields((await client.get("/security.txt")).text)


async def test_invalid_values_are_refused_in_both_languages(client):  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    for body, field in (
        ({"contact_email": ""}, "contact_email"),
        ({"contact_email": "not-an-email"}, "contact_email"),
        ({"contact_email": "a@uni.edu.tr\nPolicy: x"}, "contact_email"),
        ({"contact_email": "a@uni.edu.tr", "contact_url": "http://uni.edu.tr/x"}, "contact_url"),
        ({"contact_email": "a@uni.edu.tr", "policy_url": "javascript:alert(1)"}, "policy_url"),
        ({"contact_email": "a@uni.edu.tr", "preferred_languages": "tr; drop"}, "preferred_languages"),
    ):
        r = await client.put(URL, json=body, headers=h)
        assert r.status_code == 422, (body, r.text)
        d = r.json()["detail"]
        assert d["field"] == field and d["message_tr"] and d["message_en"]
    # the generic settings route cannot bypass the validation
    r = await client.put("/api/v1/settings", json={"extra": {"security.contact_email": "x"}}, headers=h)
    assert r.status_code == 422


async def test_only_admins_read_or_write_the_contact(client):  # type: ignore[no-untyped-def]  # noqa: F811
    assert (await client.get(URL)).status_code == 401
    assert (await client.put(URL, json={"contact_email": "a@uni.edu.tr"})).status_code == 401
    admin = await login(client)
    r = await client.post(
        "/api/v1/users",
        json={"email": "ogretmen@uni.edu.tr", "full_name": "Öğretmen", "password": "Parola-2026!", "role": "TEACHER"},
        headers=admin,
    )
    assert r.status_code in (200, 201), r.text
    teacher = await login(client, "ogretmen@uni.edu.tr", "Parola-2026!")
    assert (await client.get(URL, headers=teacher)).status_code == 403
    assert (await client.put(URL, json={"contact_email": "a@uni.edu.tr"}, headers=teacher)).status_code == 403


def test_nginx_proxies_security_txt_to_the_backend() -> None:
    block = NGINX[NGINX.index("location = /.well-known/security.txt") :]
    block = block[: block.index("}") + 1]
    assert "proxy_pass http://smartsched_backend;" in block and "return 200" not in block
    assert "X-Content-Type-Options nosniff" in block
    assert "location = /security.txt" in NGINX
    tail = NGINX[NGINX.index("location = /security.txt") :]
    assert "proxy_pass http://smartsched_backend;" in tail[: tail.index("}")]
