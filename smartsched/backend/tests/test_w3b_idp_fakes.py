"""In-process fake identity providers for the wave 3b W3-IDP tests (nothing leaves the process):

* :class:`FakeIssuer` -- a generic OpenID Connect issuer (Keycloak-shaped: ``/realms/uni``) with discovery, JWKS and
  a token endpoint that checks the authorization code, PKCE S256, the redirect URI and ``client_secret_basic``;
* the same class with ``google=True`` -- Google's endpoints (``hd`` / ``email_verified`` claims);
* :func:`idp` -- the fixture: the Entra fake of test_sso_fake_idp.py plus both issuers behind one router transport,
  an administrator and helpers that drive the admin API and the browser round trip.

    from tests.test_w3b_idp_fakes import idp  # noqa: F401  (fixture)

Client ids, secrets and realm names are made-up test values."""

from __future__ import annotations

import base64
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
from tests.test_sso_fake_idp import FakeEntra, new_key, s256

PANEL = "https://rezervasyon.uni.edu.tr"
KC_ISSUER = "https://sso.uni.edu.tr/realms/uni"
KC_CLIENT = "smartsched-panel"
KC_SECRET = "kc-fake-secret-for-tests-only"
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_CLIENT = "1234567890-fake.apps.googleusercontent.com"
GOOGLE_SECRET = "GOCSPX-fake-secret-for-tests"


@dataclass
class FakeIssuer:
    issuer: str = KC_ISSUER
    client_id: str = KC_CLIENT
    client_secret: str = KC_SECRET
    google: bool = False
    key: RSAKey = field(default_factory=lambda: new_key("kc-test-key-1"))
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    token_calls: list[dict[str, str]] = field(default_factory=list)
    #: overrides of the discovery document (tests break it on purpose)
    discovery_over: dict[str, Any] = field(default_factory=dict)
    redirect: str = ""

    @property
    def authorize(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth" if self.google else f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token(self) -> str:
        return "https://oauth2.googleapis.com/token" if self.google else f"{self.issuer}/protocol/openid-connect/token"

    @property
    def jwks(self) -> str:
        return "https://www.googleapis.com/oauth2/v3/certs" if self.google else f"{self.issuer}/protocol/openid-connect/certs"

    def discovery(self) -> dict[str, Any]:
        doc = {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorize,
            "token_endpoint": self.token,
            "jwks_uri": self.jwks,
            "end_session_endpoint": f"{self.issuer}/protocol/openid-connect/logout",
            "response_types_supported": ["code", "id_token", "code id_token"],
            "code_challenge_methods_supported": ["plain", "S256"],
            "id_token_signing_alg_values_supported": ["RS256", "HS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic"]
            if not self.google
            else ["client_secret_post", "client_secret_basic"],
        }
        doc.update(self.discovery_over)
        return doc

    def claims(self, nonce: str, /, **over: Any) -> dict[str, Any]:
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "sub": "f:3c5e:ayse.yilmaz",
            "nonce": nonce,
            "iat": now,
            "exp": now + 300,
            "name": "Ayşe Yılmaz",
            "email": "ayse.yilmaz@uni.edu.tr",
            "email_verified": True,
            "preferred_username": "ayse.yilmaz",
        }
        if self.google:
            base.update(sub="110169484474386276334", hd="uni.edu.tr")
        base.update(over)
        return {k: v for k, v in base.items() if v is not None}

    def handles(self, url: str) -> bool:
        return url.startswith(self.issuer) or url in (self.token, self.jwks) or (
            self.google and url == "https://accounts.google.com/.well-known/openid-configuration"
        )

    async def __call__(self, req: Any) -> Any:
        http = sso_service.http
        url = str(req.url)
        if req.method == "GET" and url.split("?")[0] == self.issuer.rstrip("/") + "/.well-known/openid-configuration":
            return http.Response(200, json=self.discovery())
        if req.method == "GET" and url == self.jwks:
            return http.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if req.method == "POST" and url == self.token:
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            auth = req.headers.get("authorization", "")
            if auth.startswith("Basic "):
                cid, _, sec = base64.b64decode(auth[6:]).decode().partition(":")
            else:
                cid, sec = form.get("client_id", ""), form.get("client_secret", "")
            self.token_calls.append({"auth": "basic" if auth else "post", **form})
            grant = self.codes.pop(form.get("code", ""), None)
            if (
                grant is None
                or cid != self.client_id
                or sec != self.client_secret
                or form.get("redirect_uri") != self.redirect
                or s256(form.get("code_verifier", "")) != grant["challenge"]
            ):
                return http.Response(400, json={"error": "invalid_grant"})
            claims = self.claims(grant["nonce"], **grant["claims"])
            token = jwt.encode({"alg": "RS256", "kid": self.key.kid, "typ": "JWT"}, claims, grant.get("key") or self.key)
            return http.Response(
                200,
                json={"access_token": "fake-access", "refresh_token": "fake-refresh", "id_token": token, "token_type": "Bearer"},
            )
        return http.Response(404, json={"error": "not_found", "url": url})


@dataclass
class IdpEnv:
    client: AsyncClient
    admin: dict[str, str]
    entra: FakeEntra
    kc: FakeIssuer
    google: FakeIssuer

    async def create(self, kind: str, **body: Any) -> dict[str, Any]:
        r = await self.client.post("/api/v1/auth/sso/admin/providers", json={"kind": kind, **body}, headers=self.admin)
        assert r.status_code == 201, r.text
        return r.json()

    async def put(self, pid: int, headers: dict[str, str] | None = None, **body: Any) -> Any:
        return await self.client.put(f"/api/v1/auth/sso/admin/providers/{pid}", json=body, headers=headers or self.admin)

    async def keycloak(self, **extra: Any) -> dict[str, Any]:
        """A configured and enabled Keycloak provider (slug ``keycloak``)."""
        p = await self.create("oidc", preset="keycloak")
        r = await self.put(p["id"], issuer=KC_ISSUER, client_id=KC_CLIENT, client_secret=KC_SECRET, **extra)
        assert r.status_code == 200, r.text
        r = await self.put(p["id"], enabled=True)
        assert r.status_code == 200, r.text
        self.kc.redirect = f"{PANEL}/api/v1/auth/sso/{p['name']}/callback"
        return r.json()

    async def google_ws(self, **extra: Any) -> dict[str, Any]:
        p = await self.create("google_workspace")
        body = {"client_id": GOOGLE_CLIENT, "client_secret": GOOGLE_SECRET, "hosted_domains": ["uni.edu.tr"], **extra}
        r = await self.put(p["id"], **body)
        assert r.status_code == 200, r.text
        r = await self.put(p["id"], enabled=True)
        assert r.status_code == 200, r.text
        self.google.redirect = f"{PANEL}/api/v1/auth/sso/{p['name']}/callback"
        return r.json()

    async def start(self, slug: str, **params: str) -> dict[str, str]:
        r = await self.client.get(f"/api/v1/auth/sso/{slug}/start", params=params)
        assert r.status_code == 302, r.text
        return query_of(r.headers["location"]) | {"_location": r.headers["location"]}

    async def callback(self, slug: str, q: dict[str, str], fake: FakeIssuer, **claims: Any) -> str:
        code = f"code-{uuid.uuid4().hex}"
        fake.codes[code] = {"challenge": q["code_challenge"], "nonce": q["nonce"], "claims": claims}
        r = await self.client.get(f"/api/v1/auth/sso/{slug}/callback", params={"code": code, "state": q["state"]})
        assert r.status_code == 302, r.text
        return r.headers["location"]

    async def sign_in(self, slug: str, fake: FakeIssuer, **claims: Any) -> Any:
        loc = await self.callback(slug, await self.start(slug), fake, **claims)
        q = query_of(loc)
        assert "ticket" in q, loc
        return await self.client.post("/api/v1/auth/sso/exchange", json={"ticket": q["ticket"]})

    async def headers(self, slug: str, fake: FakeIssuer, **claims: Any) -> dict[str, str]:
        r = await self.sign_in(slug, fake, **claims)
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}


def query_of(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


@pytest.fixture
async def idp(client, monkeypatch) -> IdpEnv:
    monkeypatch.setattr(get_settings(), "public_url", PANEL)
    entra, kc = FakeEntra(), FakeIssuer()
    google = FakeIssuer(
        issuer=GOOGLE_ISSUER, client_id=GOOGLE_CLIENT, client_secret=GOOGLE_SECRET, google=True, key=new_key("g-1")
    )

    async def route(req: Any) -> Any:
        url = str(req.url)
        for fake in (google, kc):
            if fake.handles(url):
                return await fake(req)
        return await entra(req)

    monkeypatch.setattr(sso_service, "transport", sso_service.http.MockTransport(route))
    sso_service.clear_jwks_cache()
    env = IdpEnv(client, await login(client), entra, kc, google)
    yield env
    sso_service.clear_jwks_cache()


async def test_fake_issuer_serves_discovery_and_public_keys(idp) -> None:  # noqa: F811
    async with sso_service.http.AsyncClient(transport=sso_service.transport) as c:
        doc = (await c.get(f"{KC_ISSUER}/.well-known/openid-configuration")).json()
        keys = (await c.get(doc["jwks_uri"])).json()["keys"]
    assert doc["issuer"] == KC_ISSUER and "S256" in doc["code_challenge_methods_supported"]
    assert [k["kid"] for k in keys] == ["kc-test-key-1"] and "d" not in keys[0]
