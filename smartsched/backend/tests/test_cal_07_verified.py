"""CAL-07 verified accounts for push (owner decision 2026-10-17 (3)), on the real Bahar 2026 import with mocked
providers: with ``integrations.push_verified_only`` (default on) a provider account is accepted when its subject is
one of the person's sign-in identities (``user_identities``, W3-IDP, read only), its Google ``hd`` is the Workspace
sign-in provider's hosted domain, its Entra ``tid`` is the sign-in tenant, it is the person's own sign-in e-mail, or
its e-mail domain is one the admin allows / the institution domain of the person's e-mail. A gmail.com account is
refused ("Bu hesap kurumunuzun doğrulanmış hesabı değil. … uzantılı hesabınızla bağlanın."), nothing is stored and
the grant is given back. With the setting off the account is accepted and the connection records ``none``. The
optional ``calendar_client_source = identity`` reuses the sign-in provider's OAuth client."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from app.core import db as dbmod
from app.core.security import encrypt_secret
from app.models import AuditEvent, CalendarConnection
from app.models.sso import SsoProvider, UserIdentity
from app.services import calendar_connectors
from app.workers import integrations as worker
from sqlalchemy import select

from tests.cal_fakes import APP_CREATED, FakeGoogleCal, FakeGraphCal
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, client_factory, kvkk_sign_off

PANEL = "https://rezervasyon.uni.edu.tr"
TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def configure(env, provider: str, own_client: bool = True) -> None:  # noqa: F811
    body: dict = {"public_url": PANEL}
    if own_client:
        body |= {f"{provider}_client_id": f"{provider}-client-id-uni", f"{provider}_client_secret": "s3cret-uni"}
    r = await env.client.put("/api/v1/calendar/admin/settings", json=body, headers=env.admin)
    assert r.status_code == 200, r.text


async def idp(kind: str, **extra) -> None:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        s.add(SsoProvider(name=kind.replace("_", "-"), kind=kind, enabled=True, **extra))
        await s.commit()


async def connect(env, fake, headers, provider: str, scopes=("my_bookings",)) -> str:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(
        f"/api/v1/calendar/connectors/{provider}/connect",
        json={"return_path": "/profile/calendar", "scopes": list(scopes)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    fake.codes["4/0Ae-verify"] = q["code_challenge"]
    cb = await env.client.get(
        f"/api/v1/calendar/connectors/{provider}/callback", params={"code": "4/0Ae-verify", "state": q["state"]}
    )
    assert cb.status_code == 302, cb.text
    await worker.wait_idle()
    return cb.headers["location"]


async def connection(provider: str) -> CalendarConnection | None:
    async with dbmod.get_session_factory()() as s:
        q = select(CalendarConnection).where(CalendarConnection.provider == provider)
        return (await s.execute(q)).scalar_one_or_none()


async def audits(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(AuditEvent).where(AuditEvent.action == action))).scalars())


async def test_cal_07_gmail_is_refused_then_allowed_with_the_setting_off(env, monkeypatch):  # noqa: F811
    fake = FakeGoogleCal(email="ayse.kisisel@gmail.com", grant_scope=f"openid {APP_CREATED}")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await calendar_consent(env.client, ayse)
    opts = (await env.client.get("/api/v1/calendar/export/options", headers=ayse)).json()
    hint = opts["channels"]["push"]["verification"]
    assert hint["required"] is True and hint["domain"] == "uni.edu.tr"
    location = await connect(env, fake, ayse, "google")
    q = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
    assert q == {"calendar": "error", "provider": "google", "reason": "account_not_verified", "domain": "uni.edu.tr"}
    assert await connection("google") is None  # nothing stored
    assert fake.calls("POST", "oauth2.googleapis.com/revoke")  # the grant is given back
    refused = await audits("calendar.push_refused")
    assert refused and refused[0].after["reason"] == "account_not_verified"
    detail = calendar_connectors.not_verified_detail("uni.edu.tr")
    assert detail["message_tr"] == (
        "Bu hesap kurumunuzun doğrulanmış hesabı değil. uni.edu.tr uzantılı hesabınızla bağlanın."
    )
    # the administrator turns the rule off (audited): the same account connects and is recorded as unverified
    r = await env.client.put(
        "/api/v1/calendar/admin/export-settings", json={"push_verified_only": False}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["push_verified_only"] is False
    assert (await audits("integrations.calendar_export"))[-1].after == {"push_verified_only": False}
    location = await connect(env, fake, ayse, "google")
    assert location.endswith("calendar=connected&provider=google")
    conn = await connection("google")
    assert conn is not None and conn.account_verified == "none"
    connected = await audits("calendar.push_connect")
    assert connected[-1].after["account_verified"] == "none" and connected[-1].after["verified_only"] is False
    # personal mailbox domains cannot be allowed
    r = await env.client.put(
        "/api/v1/calendar/admin/export-settings", json={"push_allowed_domains": ["gmail.com"]}, headers=env.admin
    )
    assert r.status_code == 422


async def test_cal_07_identity_subject_and_workspace_hd_and_allowed_domain(env, monkeypatch):  # noqa: F811
    fake = FakeGoogleCal(email="ayse@uni.edu.tr", sub="1098765", hd="uni.edu.tr", grant_scope=f"openid {APP_CREATED}")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    # her SmartSched e-mail is on another domain, so only the Workspace hd can vouch for the account
    uid, ayse = await env.user("ayse@personel-uni.edu.tr", full_name="Ayşe Yılmaz")
    await calendar_consent(env.client, ayse)
    assert "account_not_verified" in await connect(env, fake, ayse, "google")
    await idp("google_workspace", options={"hosted_domains": ["uni.edu.tr"]})
    assert (await connect(env, fake, ayse, "google")).endswith("calendar=connected&provider=google")
    conn = await connection("google")
    assert conn is not None and conn.account_verified == "domain"
    assert (await env.client.delete("/api/v1/calendar/connectors/google", headers=ayse)).status_code == 204
    # the person's own sign-in identity (W3-IDP) matches the account's subject
    async with dbmod.get_session_factory()() as s:
        s.add(UserIdentity(user_id=uid, provider="google-workspace", issuer="https://accounts.google.com",
                           tenant_id="google", subject="1098765"))  # fmt: skip
        await s.commit()
    assert (await connect(env, fake, ayse, "google")).endswith("calendar=connected&provider=google")
    conn = await connection("google")
    assert conn is not None and conn.account_verified == "sso_identity"
    assert (await env.client.delete("/api/v1/calendar/connectors/google", headers=ayse)).status_code == 204
    # an admin-allowed extra domain
    fake.email, fake.hd, fake.sub = "ayse@vakif.org.tr", None, "555"
    assert "account_not_verified" in await connect(env, fake, ayse, "google")
    r = await env.client.put(
        "/api/v1/calendar/admin/export-settings",
        json={"push_allowed_domains": [" @Vakif.org.tr "]},
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()["push_allowed_domains"] == ["vakif.org.tr"]
    assert (await connect(env, fake, ayse, "google")).endswith("calendar=connected&provider=google")


async def test_cal_07_entra_tenant_and_identity_client_source(env, monkeypatch):  # noqa: F811
    fake = FakeGraphCal(tenant=TENANT, upn="mehmet.kaya@uni.edu.tr")
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "microsoft", own_client=False)
    _, mehmet = await env.user("mehmet@personel-uni.edu.tr", full_name="Mehmet Kaya")
    await calendar_consent(env.client, mehmet)
    # no own client and the source "own": not configured
    out = (await env.client.get("/api/v1/calendar/connectors", headers=mehmet)).json()
    assert next(c for c in out if c["provider"] == "microsoft")["configured"] is False
    await idp("entra", tenant_id=TENANT, client_id="entra-app-id", client_secret_enc=encrypt_secret("entra-secret"))
    r = await env.client.put(
        "/api/v1/calendar/admin/export-settings", json={"calendar_client_source": "identity"}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["identity_clients"]["microsoft"] is True
    r = await env.client.post("/api/v1/calendar/connectors/microsoft/connect", json={"scopes": ["my_bookings"]},
                              headers=mehmet)  # fmt: skip
    assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    assert q["client_id"] == "entra-app-id" and f"/{TENANT}/" in r.json()["authorize_url"]
    # the account's tenant is the sign-in tenant
    location = await connect(env, fake, mehmet, "microsoft")
    assert location.endswith("calendar=connected&provider=microsoft"), location
    conn = await connection("microsoft")
    assert conn is not None and conn.account_verified == "tenant"
    token_call = fake.calls("POST", "/oauth2/v2.0/token")[0]
    assert fake.form(token_call)["client_id"] == "entra-app-id"
