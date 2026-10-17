"""The OpenID Connect client contract shared by every OIDC kind (``entra``, ``google_workspace``, ``oidc``) and the
discovery fetch of the guided setup (wave 3b W3-IDP).

:class:`OidcClient` is a frozen dataclass: the flow code in app/services/sso.py only reads it. Discovery
(``/.well-known/openid-configuration``) is validated before a provider may be enabled: the document's ``issuer``
must equal the configured issuer (a trailing ``/`` is the only tolerated difference and the document's form is
adopted), the endpoints must be HTTPS (``http://localhost`` is accepted for a developer's Keycloak), the provider
must support the authorization code flow and, when it lists its PKCE methods, ``S256``.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.models.base import utcnow
from app.services.identity import kinds

#: signature algorithms accepted on an ID token (symmetric HS* never: the client secret is not a signing key)
ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ENDPOINTS = {
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}
_INVISIBLE = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF), None)
_CLAIM_RX = re.compile(r"^[^\s\x00-\x1f\x7f]{1,120}$")


@dataclass(frozen=True)
class OidcClient:
    slug: str
    kind: str
    issuer: str
    authorize_endpoint: str
    token_endpoint: str
    jwks_uri: str
    client_id: str
    client_secret: str
    redirect_uri: str
    #: the identity namespace stored in ``user_identities.tenant_id``: Entra ``tid``; else a digest of the issuer
    tenant_id: str
    scopes: str = "openid profile email"
    #: Google Workspace: the pinned ``hd`` values
    hosted_domains: tuple[str, ...] = ()
    algorithms: tuple[str, ...] = ("RS256",)
    #: ``client_secret_post`` | ``client_secret_basic``
    auth_method: str = "client_secret_post"
    groups_claim: str = "groups"
    roles_claim: str = "roles"
    #: accept ``email`` without ``email_verified`` (ADFS sends none); off by default
    trust_email: bool = False
    end_session_endpoint: str | None = None
    extra_authorize: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def authority(self) -> str:
        return self.issuer


def plain(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_INVISIBLE).replace("\xa0", " ").strip()


def namespace(issuer: str) -> str:
    """``user_identities.tenant_id`` of a non-Entra identity: 32 hex characters of the issuer's SHA-256, so the same
    ``sub`` of another issuer can never match (and a changed issuer starts new identities)."""
    return hashlib.sha256(issuer.encode("utf-8")).hexdigest()[:32]


def secure_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    if not parts.netloc or "@" in parts.netloc:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and (parts.hostname or "") in ("localhost", "127.0.0.1")


def clean_issuer(value: str) -> str:
    """An issuer as the administrator pasted it: NBSP / zero-width removed, the host lower-cased (``İ`` folds), no
    query or fragment; ``/.well-known/openid-configuration`` pasted by mistake is cut off."""
    text = plain(value)
    for tail in ("/.well-known/openid-configuration", "/.well-known/openid-configuration/"):
        if text.endswith(tail):
            text = text[: -len(tail)]
    if not secure_url(text):
        raise ValueError("issuer must be an https:// URL (http://localhost only for development)")
    parts = urlsplit(text)
    if parts.query or parts.fragment:
        raise ValueError("issuer must not carry a query or a fragment")
    host = parts.netloc.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    return f"{parts.scheme}://{host}{parts.path}"


def clean_claim_name(value: str | None, default: str) -> str:
    if value is None:
        return default
    text = plain(value)
    if not text:
        return default
    if not _CLAIM_RX.match(text):
        raise ValueError("a claim name has 1..120 characters and no spaces")
    return text


def discovery_url(issuer: str) -> str:
    return issuer.rstrip("/") + "/.well-known/openid-configuration"


def _check(key: str, ok: bool, tr: str, en: str) -> dict[str, Any]:
    return {"key": key, "ok": ok, "tr": tr, "en": en}


def validate_discovery(issuer: str, doc: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(endpoints to store, checks). ``None`` when a blocking check failed."""
    checks: list[dict[str, Any]] = []
    if not isinstance(doc, dict):
        return None, [_check("json", False, "Keşif belgesi JSON değil.", "The discovery document is not JSON.")]
    got = str(doc.get("issuer") or "")
    same = got == issuer or got.rstrip("/") == issuer.rstrip("/")
    checks.append(
        _check(
            "issuer",
            same,
            "Issuer eşleşiyor." if same else f"Issuer eşleşmiyor: belge {got[:120]!r} diyor.",
            "The issuer matches." if same else f"The issuer does not match: the document says {got[:120]!r}.",
        )
    )
    endpoints: dict[str, Any] = {}
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        url = doc.get(key)
        ok = isinstance(url, str) and secure_url(url)
        checks.append(
            _check(
                key,
                ok,
                f"{key} HTTPS." if ok else f"{key} eksik ya da HTTPS değil.",
                f"{key} is HTTPS." if ok else f"{key} is missing or not HTTPS.",
            )
        )
        if ok:
            endpoints[key] = url
    end = doc.get("end_session_endpoint")
    if isinstance(end, str) and secure_url(end):
        endpoints["end_session_endpoint"] = end
    types = doc.get("response_types_supported")
    code_ok = not isinstance(types, list) or "code" in types
    checks.append(
        _check(
            "code_flow",
            code_ok,
            "Yetkilendirme kodu akışı destekleniyor." if code_ok else "Sağlayıcı yetkilendirme kodu akışını sunmuyor.",
            "The authorization code flow is supported." if code_ok else "The provider does not offer the code flow.",
        )
    )
    pkce = doc.get("code_challenge_methods_supported")
    pkce_ok = not isinstance(pkce, list) or "S256" in pkce
    checks.append(
        _check(
            "pkce",
            pkce_ok,
            "PKCE (S256) destekleniyor." if pkce_ok else "Sağlayıcı PKCE S256 desteklemiyor.",
            "PKCE (S256) is supported." if pkce_ok else "The provider does not support PKCE S256.",
        )
    )
    algs = doc.get("id_token_signing_alg_values_supported")
    usable = [a for a in algs if a in ALGORITHMS] if isinstance(algs, list) else ["RS256"]
    checks.append(
        _check(
            "algorithms",
            bool(usable),
            "İmza algoritması uygun." if usable else "ID token yalnızca desteklenmeyen algoritmalarla imzalanıyor.",
            "The signing algorithm is usable." if usable else "ID tokens are signed only with unsupported algorithms.",
        )
    )
    methods = doc.get("token_endpoint_auth_methods_supported")
    if isinstance(methods, list) and "client_secret_post" in methods:
        auth = "client_secret_post"
    else:
        auth = "client_secret_basic"
    if not all(c["ok"] for c in checks):
        return None, checks
    endpoints.update(
        issuer=got if got.rstrip("/") == issuer.rstrip("/") else issuer,
        algorithms=usable,
        auth_method=auth,
        fetched_at=utcnow().isoformat(timespec="seconds"),
    )
    return endpoints, checks


async def fetch_discovery(url: str) -> tuple[Any, str | None]:
    """(document or None, error text). Uses the SSO transport (tests put a mock there)."""
    from app.services import sso

    try:
        async with sso._client() as c:  # noqa: SLF001 - the one outbound client of the identity code
            resp = await c.get(url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        return resp.json(), None
    except Exception as exc:  # noqa: BLE001 - network error, bad JSON: reported, never raised
        return None, type(exc).__name__


def client_from(
    row: Any, *, client_id: str, client_secret: str, redirect: str, opts: dict[str, Any]
) -> OidcClient | None:
    """The client of a ``google_workspace`` or ``oidc`` row (``None`` until discovery has run for ``oidc``)."""
    if row.kind == kinds.GOOGLE:
        disc = opts.get("discovery") or {}
        domains = tuple(opts.get("hosted_domains") or ())
        if not domains:
            return None
        single = (("hd", domains[0]),) if len(domains) == 1 else ()
        return OidcClient(
            slug=row.name,
            kind=row.kind,
            issuer=GOOGLE_ISSUERS[0],
            authorize_endpoint=disc.get("authorization_endpoint") or GOOGLE_ENDPOINTS["authorization_endpoint"],
            token_endpoint=disc.get("token_endpoint") or GOOGLE_ENDPOINTS["token_endpoint"],
            jwks_uri=disc.get("jwks_uri") or GOOGLE_ENDPOINTS["jwks_uri"],
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect,
            tenant_id="google",
            hosted_domains=domains,
            auth_method="client_secret_post",
            extra_authorize=single,
        )
    disc = opts.get("discovery") or {}
    issuer = disc.get("issuer") or opts.get("issuer")
    if not (issuer and disc.get("authorization_endpoint") and disc.get("token_endpoint") and disc.get("jwks_uri")):
        return None
    extra = [s for s in opts.get("scopes") or [] if isinstance(s, str) and s not in ("openid", "profile", "email")]
    return OidcClient(
        slug=row.name,
        kind=row.kind,
        issuer=str(issuer),
        authorize_endpoint=disc["authorization_endpoint"],
        token_endpoint=disc["token_endpoint"],
        jwks_uri=disc["jwks_uri"],
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect,
        tenant_id=namespace(str(issuer)),
        scopes=" ".join(["openid", "profile", "email", *extra]),
        algorithms=tuple(disc.get("algorithms") or ("RS256",)),
        auth_method=str(disc.get("auth_method") or "client_secret_basic"),
        groups_claim=str(opts.get("groups_claim") or "groups"),
        roles_claim=str(opts.get("roles_claim") or "roles"),
        trust_email=bool(opts.get("trust_email")),
        end_session_endpoint=disc.get("end_session_endpoint"),
    )
