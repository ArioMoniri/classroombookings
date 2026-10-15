"""A local fake of the Microsoft identity platform (v2.0 endpoints of one tenant) for the SSO tests, plus the shared
``sso`` fixture. Nothing leaves the process: the fake signs ID tokens with an RSA key generated here, serves the
JWKS and the token endpoint through an httpx ``MockTransport`` and checks PKCE, the client and the redirect URI the
way Entra ID does. The claim names and shapes follow the Entra ID v2.0 ID token reference (``iss``, ``aud``, ``tid``,
``oid``, ``sub``, ``nonce``, ``preferred_username``, ``email``, ``name``, ``roles``, ``groups``, ``idp``, ``ver``).

    from tests.test_sso_fake_idp import sso  # noqa: F401  (fixture)

The tenant, client id and client secret below are made-up test values, not the university's."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core.config import get_settings
from app.services import sso as sso_service
from httpx import AsyncClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from tests.api_fixtures import login

TENANT = "3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a"
OTHER_TENANT = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
CLIENT_ID = "6b1d9e2f-0c4a-4f8e-9d3b-7a5c2e1f8b0d"
FAKE_SECRET = "fake-client-secret-for-tests-only"
PANEL = "https://rezervasyon.uni.edu.tr"
LOGIN = "https://login.microsoftonline.com"
ISSUER = f"{LOGIN}/{TENANT}/v2.0"
REDIRECT = f"{PANEL}/api/v1/auth/sso/entra/callback"


def s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def new_key(kid: str) -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid, "use": "sig", "alg": "RS256"}, private=True)


@dataclass
class FakeEntra:
    tenant: str = TENANT
    key: RSAKey = field(default_factory=lambda: new_key("entra-test-key-1"))
    #: code -> what the authorize step remembered (PKCE challenge, nonce) and the claims to put in the ID token
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[Any] = field(default_factory=list)
    jwks_calls: int = 0
    #: keys published in the JWKS (rotation tests replace it)
    published: list[RSAKey] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.published = [self.key]

    def claims(self, sent_nonce: str, /, **over: Any) -> dict[str, Any]:
        now = int(time.time())
        base: dict[str, Any] = {
            "ver": "2.0",
            "iss": f"{LOGIN}/{self.tenant}/v2.0",
            "aud": CLIENT_ID,
            "tid": self.tenant,
            "oid": "00000000-0000-0000-66f3-3332eca7ea81",
            "sub": "AAAAAAAAAAAAAAAAAAAAAIkzqFVrSaSaFHy782bbtaQ",
            "nonce": sent_nonce,
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
            "name": "Ayşe Yılmaz",
            "preferred_username": "ayse.yilmaz@uni.edu.tr",
            "email": "ayse.yilmaz@uni.edu.tr",
        }
        base.update(over)
        return {k: v for k, v in base.items() if v is not None}

    def id_token(self, claims: dict[str, Any], key: RSAKey | None = None) -> str:
        k = key or self.key
        return jwt.encode({"typ": "JWT", "alg": "RS256", "kid": k.kid}, claims, k)

    async def __call__(self, req: Any) -> Any:
        http = sso_service.http
        self.requests.append(req)
        url = str(req.url)
        if req.method == "GET" and url == f"{LOGIN}/{self.tenant}/discovery/v2.0/keys":
            self.jwks_calls += 1
            return http.Response(200, json={"keys": [k.as_dict(private=False) for k in self.published]})
        if req.method == "POST" and url == f"{LOGIN}/{self.tenant}/oauth2/v2.0/token":
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            grant = self.codes.pop(form.get("code", ""), None)  # a code is single use
            if (
                grant is None
                or form.get("grant_type") != "authorization_code"
                or form.get("client_id") != CLIENT_ID
                or form.get("client_secret") != FAKE_SECRET
                or form.get("redirect_uri") != REDIRECT
                or s256(form.get("code_verifier", "")) != grant["challenge"]
            ):
                return http.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "AADSTS70008: The provided authorization code or refresh token has "
                        "expired due to inactivity.",
                        "error_codes": [70008],
                    },
                )
            body = {
                "token_type": "Bearer",
                "scope": "openid profile email",
                "expires_in": 4523,
                "access_token": "eyJ0eXAiOiJKV1QiLCJub25jZSI6ImZha2UtYWNjZXNzLXRva2VuIn0.fake.access",
                "refresh_token": "0.ARoAv4j5cvGGr0GRqy180BHbR-fake-refresh-token",
                "id_token": grant["id_token"]
                or self.id_token(self.claims(grant["nonce"], **grant["claims"]), grant.get("key")),
            }
            return http.Response(200, json=body)
        return http.Response(404, json={"error": "not_found", "url": url})


@dataclass
class SsoEnv:
    client: AsyncClient
    admin: dict[str, str]
    fake: FakeEntra

    async def start(self, return_path: str | None = "/bookings") -> dict[str, str]:
        params = {"return_path": return_path} if return_path else {}
        r = await self.client.get("/api/v1/auth/sso/entra/start", params=params)
        assert r.status_code == 302, r.text
        loc = r.headers["location"]
        assert loc.startswith(f"{LOGIN}/{TENANT}/oauth2/v2.0/authorize?"), loc
        return {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}

    async def callback(
        self,
        q: dict[str, str],
        *,
        code: str | None = None,
        id_token: str | None = None,
        key: RSAKey | None = None,
        **claims: Any,
    ) -> str:
        """The browser comes back from Entra; returns the panel URL SmartSched redirects to."""
        code = code or f"0.ARoA-{uuid.uuid4().hex}"
        self.fake.codes[code] = {
            "challenge": q["code_challenge"],
            "nonce": q["nonce"],
            "claims": claims,
            "id_token": id_token,
            "key": key,
        }
        r = await self.client.get(
            "/api/v1/auth/sso/entra/callback",
            params={"code": code, "state": q["state"], "session_state": "fake-session-state"},
        )
        assert r.status_code == 302, r.text
        return r.headers["location"]

    async def sign_in(self, **claims: Any) -> Any:
        """Full login: start, Entra, callback, exchange of the one-time ticket. Returns the exchange response."""
        loc = await self.callback(await self.start(), **claims)
        q = {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}
        assert "ticket" in q, loc
        return await self.client.post("/api/v1/auth/sso/exchange", json={"ticket": q["ticket"]})

    async def headers(self, **claims: Any) -> dict[str, str]:
        r = await self.sign_in(**claims)
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def configure(self, **values: Any) -> Any:
        return await self.client.put("/api/v1/auth/sso/admin/entra", json=values, headers=self.admin)


def error_of(location: str) -> str | None:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}.get("sso_error")


@pytest.fixture
async def sso(client, monkeypatch) -> SsoEnv:
    monkeypatch.setattr(get_settings(), "public_url", PANEL)
    fake = FakeEntra()
    monkeypatch.setattr(sso_service, "transport", sso_service.http.MockTransport(fake))
    sso_service.clear_jwks_cache()
    admin = await login(client)
    env = SsoEnv(client, admin, fake)
    r = await env.configure(tenant_id=TENANT, client_id=CLIENT_ID, client_secret=FAKE_SECRET, enabled=True)
    assert r.status_code == 200, r.text
    yield env
    sso_service.clear_jwks_cache()


# --------------------------------------------------------------------------------------------------
# the fake itself
# --------------------------------------------------------------------------------------------------


async def test_fake_publishes_public_keys_only(sso) -> None:  # noqa: F811
    async with sso_service.http.AsyncClient(transport=sso_service.transport) as c:
        r = await c.get(f"{LOGIN}/{TENANT}/discovery/v2.0/keys")
    keys = r.json()["keys"]
    assert [k["kid"] for k in keys] == ["entra-test-key-1"]
    assert "d" not in keys[0] and "p" not in keys[0]  # no private parts in the JWKS
    assert json.dumps(keys).count('"kty": "RSA"') == 1
