"""Sign-in with the institution's Microsoft Entra ID (owner decisions 2026-10-15; design and guard rules in
docs/product/2026-10-15-integrations-options.md §5.5; UI contract docs/design/v2/sign-in.md; IT checklist
docs/deploy/sso-entra.md).

Direct OpenID Connect from the backend, no broker: authorization code flow with PKCE (S256), ``state`` and ``nonce``
through Authlib's httpx client; the ID token is verified with joserfc (Authlib's JOSE successor, BSD-3-Clause)
against the tenant's JWKS (cached, refetched once for an unknown key id).

Guard rules (each closes an escalation path):

* **Pinned tenant.** The authority is ``https://login.microsoftonline.com/{tenant}/v2.0``; ``iss`` and ``tid`` must
  equal it exactly. ``common`` / ``organizations`` / ``consumers`` and the consumer tenant are refused at
  configuration time. Guests of the tenant (``idp`` claim of another issuer, ``acct`` = 1) are refused.
* **Identity is ``(tid, oid)``**, never the e-mail (``user_identities``). An e-mail change keeps the user.
* **Two doors only.** (a) self sign-up of the pinned tenant (``self_signup`` = the ``sso_self_signup`` setting, on by
  default) always as the lowest role (``default_role_id``, Teacher; administrative roles are refused); (b) an
  administrator creates the account (``sso_invites`` kind ``invite``, link ``/login?invite=<token>``) or marks an
  existing one ``bind`` -- the first login whose *verified* UPN (``preferred_username`` / ``upn``, or ``email`` with
  ``xms_edov``) equals the invite binds ``(tid, oid)`` once, audited; invites expire (``invite_days``, 30). An
  expired invite for the address refuses the sign-in (``invite_expired``) until an administrator renews or deletes it.
* **No silent takeover.** Without an invite, a login whose verified UPN equals an existing account's e-mail is
  refused; a signed-in local user links from the profile after re-entering the password.
* **Roles are SmartSched's.** The optional mapping (``role_mapping_enabled``, off) of app roles / group object ids
  is applied at every login; administrative roles only while ``allow_admin_mapping`` is on; a change bumps
  ``users.token_version`` (sessions revoked). Group overage (``_claim_names``) never demotes.
* **Break-glass.** An active administrator with a local password always keeps password sign-in;
  ``oidc_only_non_admins`` cannot be switched on without one, and a mapping never demotes an administrator when no
  other break-glass administrator would remain.
* **No enumeration.** The panel only learns a public code (:data:`PUBLIC_CODES`): a disabled account, an existing
  account without an invite, a bad token, a replayed state all answer ``failed`` with a ``ref`` (the audit row id);
  the precise reason is in the audit log (``auth.login_refused``).
* **Nothing of the IdP is kept** but ``oid``, ``tid``, the e-mail at login and the display name. The access,
  refresh and ID tokens are dropped when the callback returns; the browser gets a one-time ``ticket`` (2 minutes,
  stored hashed) that ``POST /auth/sso/exchange`` turns into SmartSched's normal JWT.

Credentials come from the settings screen (``PUT /auth/sso/admin/entra``; the secret Fernet-encrypted with
APP_SECRET) or, for SSM-driven installs, from ``SSO_ENTRA_TENANT_ID`` / ``SSO_ENTRA_CLIENT_ID`` /
``SSO_ENTRA_CLIENT_SECRET`` in the backend environment (used for fields the screen leaves empty).

**Several providers (wave 3b W3-IDP).** Every function takes the provider's slug (``sso_providers.name``; default
``entra``, the provider above). The kinds ``google_workspace`` (pinned hosted domain ``hd``, ``email_verified``) and
``oidc`` (any issuer with discovery; exact ``iss``) share this flow through :class:`~app.services.identity.oidc.
OidcClient`; ``saml`` shares everything after the assertion is verified (app/services/identity/saml.py). Per
provider: ``allowed_domains`` (a verified address outside them is refused with ``domain``), ``invite_only`` (no
self sign-up), a role mapping whose rows only apply while their creator could still grant the role (no
escalation beyond the administrator who set it). The administration of the providers is
app/services/identity/providers.py.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import clean_email
from app.core.security import decrypt_secret, encrypt_secret, revoke_tokens, verify_password
from app.importers.normalize import clean_text
from app.models import Instructor, Program, Role, User
from app.models.base import utcnow
from app.models.sso import SsoAuthState, SsoInvite, SsoProvider, SsoRoleMapping, UserIdentity
from app.schemas.messages import Refusal
from app.services import audit
from app.services import bookings_events as events
from app.services.bookings_perms import (
    GRANT_GUARD,
    is_privileged_role,
    load_access,
    may_grant_role,
    may_manage_user,
    role_label,
    set_user_role,
    user_role,
)
from app.services.bookings_settings import get_group
from app.services.calendar_connectors import STATE_TTL, pkce_pair
from app.services.calendar_feeds import public_base
from app.services.identity import kinds as idp_kinds
from app.services.identity import saml as idp_saml
from app.services.identity.oidc import OidcClient

try:  # Authlib >= 1.9 talks httpx2 when it is installed (it is: anthropic depends on it); keep one module for both
    import httpx2 as http
except ImportError:  # pragma: no cover - legacy httpx fallback, as Authlib does
    import httpx as http  # type: ignore[no-redef]

from authlib.integrations.httpx_client import AsyncOAuth2Client  # noqa: E402
from joserfc import jws, jwt  # noqa: E402
from joserfc.errors import InvalidKeyIdError, JoseError  # noqa: E402
from joserfc.jwk import KeySet  # noqa: E402

log = logging.getLogger(__name__)

PROVIDER = "entra"
LABEL = "Microsoft 365"
LOGIN_HOST = "https://login.microsoftonline.com"
SCOPES = "openid profile email"
#: the Microsoft consumer (personal accounts) tenant; never a valid pin
CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
RESERVED_TENANTS = frozenset({"common", "organizations", "consumers"})
#: Turkish names of the GUID fields :func:`clean_guid` reports
GUID_TR = {
    "tenant id (directory id)": "Dizin (tenant) kimliği",
    "client_id (application id)": "Uygulama (client) kimliği",
    "id": "Kimlik",
}
TICKET_TTL = timedelta(minutes=2)
HTTP_TIMEOUT_S = 15.0
#: clock skew tolerated on exp / nbf / iat (seconds)
LEEWAY_S = 120
JWKS_TTL_S = 3600.0
#: an unknown ``kid`` triggers at most one JWKS refetch per key id in this window (rotation, not a DoS lever)
JWKS_FORCE_WINDOW_S = 300.0
ENV_KEYS = {
    "tenant_id": "SSO_ENTRA_TENANT_ID",
    "client_id": "SSO_ENTRA_CLIENT_ID",
    "client_secret": "SSO_ENTRA_CLIENT_SECRET",
}
#: ``prompt`` values the start URL passes on (sign-in.md §4.2: "Try another account")
PROMPTS = frozenset({"select_account", "login"})
#: outbound transport for the token endpoint and the JWKS (tests put an ``http.MockTransport`` here)
transport: Any = None

_GUID_RX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_INVISIBLE = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF), None)  # zero-width characters
_APP_ROLE_RX = re.compile(r"^[^\s]{1,120}$")
_DOMAIN_RX = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

#: internal refusal reason -> the public ``error`` code of the panel redirect (sign-in.md §6.3). Several reasons share
#: ``failed`` on purpose: the panel must not learn whether an account exists or is disabled.
PUBLIC_CODES: dict[str, str] = {
    "state": "failed",
    # round-1 R1-A-29 (T-R1-35): sign-in with Microsoft switched off is a state, not a failure with a support code
    "not_configured": "not_enabled",
    "exchange": "failed",
    "invalid_token": "failed",
    "account_exists": "failed",
    "disabled": "failed",
    "link_user": "failed",
    "denied": "cancelled",
    "unavailable": "unavailable",
    "tenant": "tenant",
    "guest": "tenant",
    "signup_closed": "signup_closed",
    "invite_expired": "invite_expired",
    "invite_invalid": "invite_invalid",
    "invite_mismatch": "invite_mismatch",
    "already_linked": "already_linked",  # link from the profile only
    # wave 3b: several providers
    "domain": "domain",
    "invite_provider": "invite_provider",
    # AU-16: the policy requires 2FA for the role and the provider asserted no MFA ("IdP MFA'yı zorunlu tut" on)
    "idp_mfa": "idp_mfa_required",
}

#: the public codes in Turkish and English (GET /auth/sso/providers ``messages``; sign-in.md §6.2/§6.3 copy)
MESSAGES: dict[str, dict[str, str]] = {
    "failed": {
        "tr": "Giriş yapılamadı. Tekrar deneyin. Sorun sürerse bu kodu yöneticinize iletin: {ref}",
        "en": "We couldn't sign you in. Try again. If it keeps happening, give this code to your administrator: {ref}",
    },
    "not_enabled": {
        "tr": "Microsoft ile giriş bu kurumda henüz açık değil.",
        "en": "Sign-in with Microsoft isn't turned on at this institution yet.",
    },
    "cancelled": {
        "tr": "Microsoft girişi tamamlanmadı. Hazır olduğunuzda tekrar deneyin.",
        "en": "Microsoft sign-in wasn't completed. Try again when you're ready.",
    },
    "unavailable": {
        "tr": "Microsoft'a şu anda ulaşılamıyor. Birkaç dakika sonra tekrar deneyin.",
        "en": "Microsoft can't be reached right now. Try again in a few minutes.",
    },
    "tenant": {
        "tr": "Bu hesapla giriş yapılamıyor. Kurumunuzun iş veya okul hesabıyla giriş yapın. Kişisel Microsoft "
        "hesapları ve başka kurumların hesapları kabul edilmez.",
        "en": "This account can't be used here. Sign in with your institution's work or school account. Personal "
        "Microsoft accounts and accounts from other organisations aren't accepted.",
    },
    "signup_closed": {
        "tr": "Kendiliğinden hesap açma kapalı. Hesabınız yoksa bir yöneticiye başvurun.",
        "en": "Self sign-up is turned off. No account yet? Ask an administrator.",
    },
    "invite_expired": {
        "tr": "Davetin süresi doldu. Yöneticinizden yeni bir davet isteyin.",
        "en": "This invitation has expired. Ask your administrator for a new one.",
    },
    "invite_invalid": {
        "tr": "Bu davet artık geçerli değil. Yöneticinizden yeni bir davet isteyin.",
        "en": "This invitation is no longer valid. Ask your administrator for a new one.",
    },
    "invite_mismatch": {
        "tr": "Davet başka bir adres için. Davet {invited_masked} adresine gönderildi; Microsoft'ta {signed_in} "
        "olarak giriş yaptınız.",
        "en": "The invitation is for another address. It was sent to {invited_masked}; you signed in to Microsoft as "
        "{signed_in}.",
    },
    "already_linked": {
        "tr": "Bu Microsoft hesabı başka bir SmartSched hesabına bağlı ya da bu hesap zaten başka bir Microsoft "
        "hesabına bağlı.",
        "en": "This Microsoft account is linked to another SmartSched account, or this account is already linked to "
        "another Microsoft account.",
    },
    "domain": {
        "tr": "Bu adresle giriş yapılamıyor: kurumun izin verdiği bir e-posta alan adıyla giriş yapın.",
        "en": "This address can't be used here: sign in with an e-mail domain the institution allows.",
    },
    "invite_provider": {
        "tr": "Bu davet başka bir giriş yöntemi için. Davet e-postasındaki düğmeyi kullanın.",
        "en": "This invitation is for another sign-in method. Use the button in the invitation e-mail.",
    },
    "idp_mfa_required": {
        "tr": "Kurumunuz bu rol için iki adımlı doğrulama istiyor. Kimlik sağlayıcınızda çok adımlı doğrulamayı açıp "
        "yeniden giriş yapın; sorun sürerse yöneticinize başvurun.",
        "en": "Your institution requires two-step verification for this role. Turn on multi-factor authentication at "
        "your identity provider and sign in again; if it keeps happening, contact your administrator.",
    },
    "sso_required": {
        "tr": "Bu hesap için parola ile giriş kapalı. 'Microsoft ile giriş yap' düğmesini kullanın.",
        "en": "Password sign-in is turned off for this account. Use 'Sign in with Microsoft'.",
    },
}


class SsoError(Exception):
    """A refused callback: ``code`` is a key of :data:`PUBLIC_CODES`; ``detail`` and ``code`` go to the audit log;
    ``extra`` are query parameters of the panel redirect (only for the invite codes)."""

    def __init__(self, code: str, detail: str = "", *, user_id: int | None = None, extra: dict[str, str] | None = None):
        super().__init__(code)
        self.code, self.detail, self.user_id, self.extra = code, detail[:200], user_id, extra or {}


class SsoAdminError(Exception):
    """A refused administration / link request (the API answers ``status`` with ``{code, tr, en}``)."""

    def __init__(self, status: int, code: str, en: str, tr: str):
        super().__init__(en)
        self.status, self.code, self.en, self.tr = status, code, en, tr

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "en": self.en, "tr": self.tr}


def _no_escalation(what: str = "this account") -> SsoAdminError:
    return SsoAdminError(
        403,
        "no_escalation",
        f"managing {what} requires every permission its role holds",
        "Bu işlem için ilgili rolün tüm izinlerine sahip olmanız gerekir",
    )


# --------------------------------------------------------------------------------------------------
# Text normalisation (pasted values: NBSP, zero-width, capitals; Turkish names kept as written)
# --------------------------------------------------------------------------------------------------


def _plain(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_INVISIBLE).replace("\xa0", " ").strip()


def clean_guid(value: str, what: str = "id") -> str:
    text = _plain(value).lower().strip("{}")
    if not _GUID_RX.match(text):
        raise Refusal(
            "sso_guid_invalid",
            f"{GUID_TR.get(what, what)} 3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a biçiminde bir GUID olmalı.",
            f"{what} must be a GUID like 3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a",
        )
    return text


def clean_tenant(value: str) -> str:
    """The directory (tenant) id: a GUID. Multi-tenant authorities and the consumer tenant are refused, so ``iss``
    can be compared exactly (Microsoft: tenant-specific authority for single-tenant apps)."""
    text = _plain(value).lower()
    if text in RESERVED_TENANTS:
        raise Refusal(
            "sso_tenant_reserved",
            f"“{text}” kullanılamaz: üniversitenin kendi dizin (tenant) kimliğini girin.",
            f"tenant id {text!r} is not allowed: pin the university's own directory (tenant) id",
        )
    guid = clean_guid(text, "tenant id (directory id)")
    if guid == CONSUMER_TENANT:
        raise Refusal(
            "sso_tenant_consumer",
            "Microsoft'un bireysel hesap dizini kullanılamaz: üniversitenin dizin (tenant) kimliğini girin.",
            "the Microsoft consumer tenant is not allowed: pin the university's directory (tenant) id",
        )
    return guid


def clean_domain(value: str) -> str | None:
    """``uni.edu.tr`` (the login page's hint); an e-mail or ``@domain`` is reduced to its domain; empty clears.
    Turkish dotted / dotless i fold to ``i`` (``UNİ.EDU.TR`` -> ``uni.edu.tr``)."""
    text = _plain(value).replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    text = text.rsplit("@", 1)[-1].strip(". ")
    if not text:
        return None
    if not _DOMAIN_RX.match(text):
        raise Refusal(
            "sso_domain_invalid",
            "Alan adı uni.edu.tr gibi bir alan adı olmalı.",
            "domain_hint must be a domain name like uni.edu.tr",
        )
    return text


def clean_display_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = clean_text(_plain(value))
    return text[:255] if text else None


def _fold_email(value: Any) -> str | None:
    if not isinstance(value, str) or "@" not in value:
        return None
    try:
        return clean_email(value)[:255]
    except ValueError:
        return None


def mask_email(value: str | None) -> str | None:
    """``ay•••@uni.edu.tr``: the first two characters of the local part and the full domain (sign-in.md §6.3)."""
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    return f"{local[:2]}•••@{domain}"


def safe_return_path(value: str | None) -> str | None:
    """A path inside the panel (``/bookings``), never another origin (``//host``, ``/\\host``, ``https://``)."""
    if not value:
        return None
    text = _plain(value)
    if (
        not text.startswith("/")
        or text.startswith("//")
        or "\\" in text
        or len(text) > 255
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in text)
        or "://" in text
    ):
        return None
    return text


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------------


#: the Entra client is an :class:`OidcClient` of kind ``entra`` (frozen contract shared by every OIDC kind)
EntraClient = OidcClient


def entra_client(tenant: str, client: str, secret: str, redirect: str, slug: str = PROVIDER) -> OidcClient:
    return OidcClient(
        slug=slug,
        kind=idp_kinds.ENTRA,
        issuer=f"{LOGIN_HOST}/{tenant}/v2.0",
        authorize_endpoint=f"{LOGIN_HOST}/{tenant}/oauth2/v2.0/authorize",
        token_endpoint=f"{LOGIN_HOST}/{tenant}/oauth2/v2.0/token",
        jwks_uri=f"{LOGIN_HOST}/{tenant}/discovery/v2.0/keys",
        client_id=client,
        client_secret=secret,
        redirect_uri=redirect,
        tenant_id=tenant,
        scopes=SCOPES,
        auth_method="client_secret_post",
    )


def redirect_uri(base: str, slug: str = PROVIDER) -> str:
    return f"{base}/api/v1/auth/sso/{slug}/callback"


async def get_provider(db: AsyncSession, *, create: bool = False, slug: str = PROVIDER) -> SsoProvider | None:
    row = (await db.execute(select(SsoProvider).where(SsoProvider.name == slug))).scalar_one_or_none()
    if row is None and create and slug == PROVIDER:
        row = SsoProvider(
            name=PROVIDER,
            kind=idp_kinds.ENTRA,
            enabled=False,
            self_signup=True,
            oidc_only_non_admins=False,
            role_mapping_enabled=False,
            allow_admin_mapping=False,
            invite_days=30,
        )
        db.add(row)
        await db.flush()
    return row


def _env(field: str) -> str:
    return (os.environ.get(ENV_KEYS[field]) or "").strip()


def _credentials(row: SsoProvider | None) -> tuple[str | None, str | None, str | None, list[str]]:
    """(tenant, client id, secret, fields taken from the environment). Stored values win; invalid env values are
    ignored (logged)."""
    from_env: list[str] = []
    tenant = row.tenant_id if row is not None else None
    env_ok = row is None or row.name == PROVIDER  # SSM values belong to the original Entra provider only
    if not tenant and env_ok and _env("tenant_id"):
        try:
            tenant = clean_tenant(_env("tenant_id"))
            from_env.append("tenant_id")
        except ValueError:
            log.warning("ignoring %s: not a tenant GUID", ENV_KEYS["tenant_id"])
    client = row.client_id if row is not None else None
    if not client and env_ok and _env("client_id"):
        try:
            client = clean_guid(_env("client_id"))
            from_env.append("client_id")
        except ValueError:
            log.warning("ignoring %s: not a GUID", ENV_KEYS["client_id"])
    secret: str | None = None
    if row is not None and row.client_secret_enc:
        try:
            secret = decrypt_secret(row.client_secret_enc)
        except ValueError:
            log.warning("the stored Entra client secret cannot be decrypted (APP_SECRET changed?)")
    if not secret and env_ok and _env("client_secret"):
        secret = _env("client_secret")
        from_env.append("client_secret")
    return tenant, client, secret, from_env


async def client_config(db: AsyncSession, row: SsoProvider | None = None) -> OidcClient | None:
    """The OIDC client when the provider's values and the public URL are all known (enabled or not); ``None`` for a
    SAML provider (see :func:`saml_config`)."""
    row = row or await get_provider(db)
    base, _src = await public_base(db)
    if row is not None and row.kind != idp_kinds.ENTRA:
        if row.kind not in (idp_kinds.GOOGLE, idp_kinds.OIDC) or not (row.client_id and base):
            return None
        tenant_unused, client, secret, _ = _credentials(row)
        if not (client and secret):
            return None
        from app.services.identity.oidc import client_from

        return client_from(
            row, client_id=client, client_secret=secret, redirect=redirect_uri(base, row.name), opts=row.options or {}
        )
    tenant, client, secret, _ = _credentials(row)
    if not (tenant and client and secret and base):
        return None
    slug = row.name if row is not None else PROVIDER
    return entra_client(tenant, client, secret, redirect_uri(base, slug), slug)


async def saml_config(db: AsyncSession, row: SsoProvider) -> idp_saml.SamlConfig | None:
    base, _src = await public_base(db)
    if row.kind != idp_kinds.SAML or not base:
        return None
    return idp_saml.config_from(row, base, row.options or {})


async def active_client(db: AsyncSession, slug: str = PROVIDER) -> tuple[SsoProvider, OidcClient] | None:
    row = await get_provider(db, slug=slug)
    if row is None or not row.enabled:
        return None
    cfg = await client_config(db, row)
    return (row, cfg) if cfg is not None else None


def provider_label(row: SsoProvider, locale: str = "tr") -> str:
    return (row.display_name or "").strip() or (
        LABEL if row.kind == idp_kinds.ENTRA else idp_kinds.default_label(row.kind, locale)
    )


async def enabled_providers(db: AsyncSession) -> list[dict[str, Any]]:
    """The sign-in buttons of /login: every enabled and usable provider in the administrators' order."""
    q = select(SsoProvider).where(SsoProvider.enabled.is_(True)).order_by(SsoProvider.sort_order, SsoProvider.id)
    out: list[dict[str, Any]] = []
    for row in (await db.execute(q)).scalars():
        usable = (
            await saml_config(db, row) is not None and idp_saml.AVAILABLE
            if row.kind == idp_kinds.SAML
            else await client_config(db, row) is not None
        )
        if not usable:
            continue
        out.append(
            {
                "name": row.name,
                "kind": row.kind,
                "label": provider_label(row),
                "label_en": provider_label(row, "en"),
                "badge": idp_kinds.BADGES.get(row.kind, "SSO"),
                "start_url": f"/api/v1/auth/sso/{row.name}/start",
                "enabled": True,
                "domain_hint": row.domain_hint,
                "self_signup": bool(row.self_signup and not row.invite_only),
                "order": row.sort_order,
            }
        )
    return out


async def _default_role(db: AsyncSession, row: SsoProvider | None) -> Role | None:
    if row is not None and row.default_role_id is not None:
        role = await db.get(Role, row.default_role_id)
        if role is not None:
            return role
    return (await db.execute(select(Role).where(Role.code == "TEACHER"))).scalar_one_or_none()


def _role_ref(role: Role | None) -> dict[str, Any] | None:
    return {"id": role.id, "code": role.code, "name": role.name} if role is not None else None


def _too_privileged_for_default(role: Role) -> bool:
    names = {p.name for p in role.permissions}
    return is_privileged_role(role) or bool(names & {"planning.admin", "planning.edit", "setup.users", GRANT_GUARD})


def _break_glass_filter() -> list[Any]:
    return [
        User.role == "ADMIN",
        User.is_active.is_(True),
        User.auth_source == "local",
        User.password_hash.is_not(None),
        User.password_hash != "",
    ]


async def break_glass_admins(db: AsyncSession, *, exclude_user_id: int | None = None) -> int:
    """Active administrators who can sign in with a local password (``auth_source = local``)."""
    q = select(func.count(User.id)).where(*_break_glass_filter())
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return int((await db.execute(q)).scalar_one())


async def config_out(db: AsyncSession) -> dict[str, Any]:
    row = await get_provider(db)
    tenant, client, secret, from_env = _credentials(row)
    base, source = await public_base(db)
    return {
        "enabled": bool(row and row.enabled),
        "configured": bool(tenant and client and secret and base),
        "tenant_id": tenant,
        "client_id": client,
        "client_secret_set": bool(secret),
        "from_environment": from_env,
        "authority": f"{LOGIN_HOST}/{tenant}/v2.0" if tenant else None,
        "redirect_uri": redirect_uri(base) if base else None,
        "public_url_source": source,
        "self_signup": row.self_signup if row is not None else True,
        "domain_hint": row.domain_hint if row is not None else None,
        "default_role": _role_ref(await _default_role(db, row)),
        "oidc_only_non_admins": bool(row and row.oidc_only_non_admins),
        "role_mapping_enabled": bool(row and row.role_mapping_enabled),
        "allow_admin_mapping": bool(row and row.allow_admin_mapping),
        "invite_days": row.invite_days if row is not None else 30,
        "break_glass_admins": await break_glass_admins(db),
        "updated_at": row.updated_at if row is not None else None,
    }


async def public_auth(db: AsyncSession) -> dict[str, Any]:
    """The login page's ``auth`` block (sign-in.md §14 ``GET /org/public``): no secret, nothing about any account."""
    row = await get_provider(db)
    enabled = await active_client(db) is not None
    role = await _default_role(db, row)
    buttons = await enabled_providers(db)
    oidc_only = (
        await db.execute(
            select(func.count(SsoProvider.id)).where(
                SsoProvider.enabled.is_(True), SsoProvider.oidc_only_non_admins.is_(True)
            )
        )
    ).scalar_one()
    return {
        #: wave 3b: one button per enabled provider in the administrators' order (``microsoft`` stays for the
        #: original Entra provider)
        "providers": buttons,
        "microsoft": {
            "enabled": enabled,
            "label": LABEL,
            "start_url": f"/api/v1/auth/sso/{PROVIDER}/start",
            "domain_hint": row.domain_hint if row is not None else None,
            "self_signup": bool(row.self_signup) if row is not None else True,
        },
        #: false: the password form is reachable only through ``/login?method=local`` (break-glass)
        "local_enabled": not (buttons and oidc_only),
        "ldap_enabled": bool((await get_group(db, "ldap"))["enabled"]),
        "self_signup_role_name": role.name if role is not None else None,
        # T-R1-30: the hint "Your account opens as <role>" reads in the reader's language (built-in names localised)
        "self_signup_role_code": role.code if role is not None else None,
        "self_signup_role_label": role_label(role),
    }


def _snapshot(row: SsoProvider) -> dict[str, Any]:
    return {
        "enabled": row.enabled,
        "tenant_id": row.tenant_id,
        "client_id": row.client_id,
        "client_secret_set": bool(row.client_secret_enc),
        "self_signup": row.self_signup,
        "domain_hint": row.domain_hint,
        "default_role_id": row.default_role_id,
        "oidc_only_non_admins": row.oidc_only_non_admins,
        "role_mapping_enabled": row.role_mapping_enabled,
        "allow_admin_mapping": row.allow_admin_mapping,
        "invite_days": row.invite_days,
    }


async def update_config(db: AsyncSession, actor: User, values: dict[str, Any]) -> None:
    """Apply a partial update (already validated by the schema); raises :class:`SsoAdminError`. The caller
    commits (or rolls back on error)."""
    row = await get_provider(db, create=True)
    assert row is not None
    before = _snapshot(row)
    secret = values.pop("client_secret", None)
    if secret:
        row.client_secret_enc = encrypt_secret(secret)
    if "default_role_id" in values and values["default_role_id"] is not None:
        role = await db.get(Role, values["default_role_id"])
        if role is None:
            raise SsoAdminError(422, "unknown_role", "unknown role", "bilinmeyen rol")
        if _too_privileged_for_default(role):
            raise SsoAdminError(
                422,
                "default_role_privileged",
                "the sign-up role must be the lowest one (e.g. Teacher or Viewer), not an administrative role",
                "Kendiliğinden açılan hesapların rolü en düşük rol olmalıdır (ör. Öğretmen ya da İzleyici)",
            )
        if not await may_grant_role(db, actor, role):
            raise _no_escalation("this role")
    if values.get("allow_admin_mapping") and not row.allow_admin_mapping and actor.role != "ADMIN":
        raise SsoAdminError(
            403,
            "admin_only",
            "only an Administrator may allow mappings to administrative roles",
            "Yönetici rollerine eşlemeye yalnızca bir Yönetici izin verebilir",
        )
    if "domain_hint" in values:
        row.domain_hint = values.pop("domain_hint")
    for key in (
        "enabled",
        "tenant_id",
        "client_id",
        "self_signup",
        "default_role_id",
        "oidc_only_non_admins",
        "role_mapping_enabled",
        "allow_admin_mapping",
        "invite_days",
    ):
        if key in values and values[key] is not None:
            setattr(row, key, values[key])
    if row.enabled:
        tenant, client, sec, _ = _credentials(row)
        if not (tenant and client and sec):
            raise SsoAdminError(
                422,
                "incomplete",
                "enabling needs the tenant id, the client (application) id and the client secret",
                "Etkinleştirmek için dizin (tenant) kimliği, uygulama (istemci) kimliği ve istemci gizli anahtarı "
                "gereklidir",
            )
        base, _src = await public_base(db)
        if not base:
            raise SsoAdminError(
                422,
                "no_public_url",
                "enabling needs the public URL of the panel (PUBLIC_URL or integrations.public_url): the redirect URI "
                "is built from it",
                "Etkinleştirmek için panelin genel adresi (PUBLIC_URL) gereklidir: yönlendirme adresi ondan "
                "oluşturulur",
            )
    if row.oidc_only_non_admins and await break_glass_admins(db) < 1:
        raise SsoAdminError(
            409,
            "break_glass",
            "refused: no active administrator with a local password would keep password sign-in (break-glass "
            "admin). Give one administrator a local password first.",
            "Reddedildi: yerel parolası olan etkin bir yönetici (acil durum yöneticisi) kalmıyor. Önce bir yöneticiye "
            "yerel parola verin.",
        )
    row.updated_at, row.updated_by = utcnow(), actor.id
    await db.flush()
    after = _snapshot(row)
    if after != before or secret:
        if secret:
            after["client_secret_changed"] = True
        await audit.record(db, "sso.config_update", "sso_provider", row.id, before=before, after=after, actor=actor)


# --------------------------------------------------------------------------------------------------
# "OIDC only for non-admins" (password sign-in guard, called by the login route)
# --------------------------------------------------------------------------------------------------


async def is_admin_user(db: AsyncSession, user: User) -> bool:
    if user.role == "ADMIN":
        return True
    role = await user_role(db, user)
    if is_privileged_role(role):
        return True
    return "planning.admin" in (await load_access(db, user)).perms


async def password_login_allowed(db: AsyncSession, user: User) -> bool:
    """False when ``oidc_only_non_admins`` is on for an enabled provider and ``user`` is no administrator."""
    q = select(func.count(SsoProvider.id)).where(
        SsoProvider.enabled.is_(True), SsoProvider.oidc_only_non_admins.is_(True)
    )
    if not (await db.execute(q)).scalar_one():
        return True
    return await is_admin_user(db, user)


async def record_password_refusal(db: AsyncSession, user: User, method: str) -> None:
    """Audit a password sign-in refused by ``oidc_only_non_admins``. The caller commits and answers the generic 401
    (sign-in.md §6.3: an SSO-only user gets the same string as a wrong password)."""
    await audit.record(
        db, "auth.login_refused", "user", user.id, after={"reason": "sso_required", "auth_method": method}
    )


# --------------------------------------------------------------------------------------------------
# Role mapping
# --------------------------------------------------------------------------------------------------


_GROUP_RX = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")


def clean_mapping_value(claim: str, value: str, kind: str = idp_kinds.ENTRA) -> str:
    """Entra: a group object id (GUID) or an app role value. Other kinds: the group / role value as the provider
    sends it (Keycloak ``/staff/planners``, eduPersonEntitlement ``urn:mace:…``), NBSP and zero-width removed."""
    if claim == "group" and kind == idp_kinds.ENTRA:
        return clean_guid(value, "group object id")
    text = _plain(value)
    if claim == "group":
        if not _GROUP_RX.match(text):
            raise ValueError("a group value has 1..160 characters and no control characters")
        return text
    if not _APP_ROLE_RX.match(text):
        raise ValueError("an app role value has 1..120 characters and no spaces (e.g. SmartSched.Planner)")
    return text


async def list_mappings(db: AsyncSession, slug: str = PROVIDER) -> list[dict[str, Any]]:
    q = select(SsoRoleMapping).where(SsoRoleMapping.provider == slug).order_by(SsoRoleMapping.id)
    out = []
    for m in (await db.execute(q)).scalars():
        role = await db.get(Role, m.role_id)
        if role is not None:
            out.append(
                {"id": m.id, "claim": m.claim, "value": m.value, "role": _role_ref(role), "created_at": m.created_at}
            )
    return out


def _grants_admin(role: Role) -> bool:
    return role.code == "ADMIN" or is_privileged_role(role)


async def add_mapping(
    db: AsyncSession, actor: User, claim: str, value: str, role_id: int, slug: str = PROVIDER
) -> SsoRoleMapping:
    row = await get_provider(db, create=True, slug=slug)
    if row is None:
        raise SsoAdminError(404, "not_found", "provider not found", "Kimlik sağlayıcısı bulunamadı")
    try:
        clean = clean_mapping_value(claim, value, row.kind)
    except ValueError as exc:
        raise SsoAdminError(422, "invalid_value", str(exc), "Geçersiz eşleme değeri") from exc
    role = await db.get(Role, role_id)
    if role is None:
        raise SsoAdminError(422, "unknown_role", "unknown role", "bilinmeyen rol")
    if not await may_grant_role(db, actor, role):
        raise SsoAdminError(
            403,
            "no_escalation",
            "you cannot map to a role whose permissions you do not all hold",
            "Tüm izinlerine sahip olmadığınız bir role eşleme yapamazsınız",
        )
    if _grants_admin(role) and not row.allow_admin_mapping:
        raise SsoAdminError(
            422,
            "admin_mapping_off",
            "mapping to an administrative role needs allow_admin_mapping (off by default)",
            "Yönetici rolüne eşleme için allow_admin_mapping açık olmalıdır (varsayılan kapalı)",
        )
    clash = (
        await db.execute(
            select(SsoRoleMapping.id).where(
                SsoRoleMapping.provider == slug, SsoRoleMapping.claim == claim, SsoRoleMapping.value == clean
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise SsoAdminError(409, "duplicate", "this value is already mapped", "Bu değer zaten eşlenmiş")
    m = SsoRoleMapping(provider=slug, claim=claim, value=clean, role_id=role.id, created_by=actor.id)
    db.add(m)
    await db.flush()
    await audit.record(
        db,
        "sso.mapping_create",
        "sso_role_mapping",
        m.id,
        after={"claim": claim, "value": clean, "role_id": role.id, "role": role.code or role.name, "provider": slug},
        actor=actor,
    )
    return m


async def delete_mapping(db: AsyncSession, actor: User, mapping_id: int, slug: str = PROVIDER) -> None:
    m = await db.get(SsoRoleMapping, mapping_id)
    if m is None or m.provider != slug:
        raise SsoAdminError(404, "not_found", "mapping not found", "Eşleme bulunamadı")
    role = await db.get(Role, m.role_id)
    if role is not None and not await may_grant_role(db, actor, role):
        raise SsoAdminError(
            403,
            "no_escalation",
            "you cannot change a mapping to a role whose permissions you do not all hold",
            "Tüm izinlerine sahip olmadığınız bir rolün eşlemesini değiştiremezsiniz",
        )
    before = {"claim": m.claim, "value": m.value, "role_id": m.role_id}
    await db.delete(m)
    await db.flush()
    await audit.record(db, "sso.mapping_delete", "sso_role_mapping", mapping_id, before=before, actor=actor)


async def _mapped_role(db: AsyncSession, row: SsoProvider, claims: dict[str, Any]) -> tuple[Role | None, str]:
    """(target role, why) from the mapping, or (None, reason) when the mapping does not apply to this login."""
    q = select(SsoRoleMapping).where(SsoRoleMapping.provider == row.name)
    mappings = list((await db.execute(q)).scalars())
    if not row.role_mapping_enabled or not mappings:
        return None, "mapping off"
    names = claims.get("_claim_names")
    if isinstance(names, dict) and "groups" in names:
        return None, "group overage"  # >200 groups: Entra left them out; never demote on missing data
    app_roles = set(claims.get("_roles") or ())
    groups = set(claims.get("_groups") or ())
    best: Role | None = None
    creators: dict[int, User | None] = {}
    for m in mappings:
        if (m.claim == "role" and m.value in app_roles) or (m.claim == "group" and m.value in groups):
            role = await db.get(Role, m.role_id)
            if role is None or (_grants_admin(role) and not row.allow_admin_mapping):
                continue
            # no escalation beyond the administrator who set the mapping: it applies only while its creator could
            # still grant the role (a demoted or deleted creator's mapping is inert)
            if m.created_by is None:
                continue
            if m.created_by not in creators:
                creators[m.created_by] = await db.get(User, m.created_by)
            creator = creators[m.created_by]
            if creator is None or not creator.is_active or not await may_grant_role(db, creator, role):
                continue
            if best is None or len(role.permissions) > len(best.permissions):
                best = role
    if best is not None:
        return best, "mapping"
    return await _default_role(db, row), "no mapping matched"


async def _apply_mapping(db: AsyncSession, row: SsoProvider, user: User, claims: dict[str, Any]) -> None:
    target, why = await _mapped_role(db, row, claims)
    if target is None:
        if why == "group overage":
            await audit.record(db, "sso.mapping_skipped", "user", user.id, after={"reason": why}, actor=user)
        return
    current = await user_role(db, user)
    if current is not None and current.id == target.id:
        return
    if user.role == "ADMIN" and target.code != "ADMIN" and await break_glass_admins(db, exclude_user_id=user.id) < 1:
        await audit.record(
            db,
            "sso.demotion_blocked",
            "user",
            user.id,
            after={"reason": "no other break-glass administrator", "mapped_role": target.code or target.name},
            actor=user,
        )
        return
    before = {"role_id": user.role_id, "role": user.role}
    set_user_role(user, target)
    revoke_tokens(user)  # a role change (above all a demotion) ends every existing session
    await audit.record(
        db,
        "sso.role_change",
        "user",
        user.id,
        before=before,
        after={"role_id": target.id, "role": user.role, "to": target.code or target.name, "reason": why},
        actor=user,
    )


# --------------------------------------------------------------------------------------------------
# JWKS (cached) and ID token validation
# --------------------------------------------------------------------------------------------------

_jwks: dict[str, tuple[KeySet, float]] = {}
_jwks_forced: dict[tuple[str, str], float] = {}


def clear_jwks_cache() -> None:
    _jwks.clear()
    _jwks_forced.clear()


def _client() -> Any:
    return http.AsyncClient(timeout=HTTP_TIMEOUT_S, follow_redirects=False, transport=transport)


async def _fetch_jwks(uri: str) -> KeySet:
    try:
        async with _client() as c:
            resp = await c.get(uri, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise SsoError("unavailable", f"jwks HTTP {resp.status_code}")
        keyset = KeySet.import_key_set(resp.json())
    except SsoError:
        raise
    except Exception as exc:  # network error, bad JSON, bad key set
        raise SsoError("unavailable", f"jwks {type(exc).__name__}") from exc
    _jwks[uri] = (keyset, time.monotonic())
    return keyset


async def jwks(uri: str, *, unknown_kid: str | None = None) -> KeySet:
    """The tenant's signing keys, cached for an hour; an unknown key id refetches once per window (rotation)."""
    now = time.monotonic()
    cached = _jwks.get(uri)
    if unknown_kid is not None:
        last = _jwks_forced.get((uri, unknown_kid))
        if last is not None and now - last < JWKS_FORCE_WINDOW_S and cached is not None:
            return cached[0]
        _jwks_forced[(uri, unknown_kid)] = now
        return await _fetch_jwks(uri)
    if cached is not None and now - cached[1] < JWKS_TTL_S:
        return cached[0]
    return await _fetch_jwks(uri)


def _registry(cfg: OidcClient) -> jwt.JWTClaimsRegistry:
    essential: dict[str, Any] = {"oid": {"essential": True}} if cfg.kind == idp_kinds.ENTRA else {}
    if cfg.kind != idp_kinds.ENTRA:
        essential["sub"] = {"essential": True}
    return jwt.JWTClaimsRegistry(
        leeway=LEEWAY_S,
        aud={"essential": True, "value": cfg.client_id},
        exp={"essential": True},
        nonce={"essential": True},
        **essential,
    )


def _claim_values(value: Any) -> list[str]:
    """A claim that should be a list of strings: a list, one string (space- or comma-separated is kept whole), or
    nothing."""
    if isinstance(value, str):
        return [_plain(value)] if value.strip() else []
    if isinstance(value, list):
        return [_plain(v) for v in value if isinstance(v, str) and v.strip()]
    return []


def _check_issuer(cfg: OidcClient, claims: dict[str, Any]) -> None:
    """Per kind: Entra pins ``iss`` + ``tid`` and refuses guests; Google pins the hosted domain ``hd``; a generic
    issuer must match exactly. All refusals are ``tenant`` (the account is from the wrong organisation)."""
    iss = claims.get("iss")
    if cfg.kind == idp_kinds.ENTRA:
        # the tenant first: a correctly signed token of another tenant (Entra signs every tenant with the same keys)
        if iss != cfg.issuer or str(claims.get("tid") or "").lower() != cfg.tenant_id:
            raise SsoError("tenant", f"iss={str(iss)[:90]} tid={str(claims.get('tid'))[:40]}")
        idp = claims.get("idp")
        if (isinstance(idp, str) and idp and idp != cfg.issuer) or str(claims.get("acct", "0")) == "1":
            raise SsoError("guest", f"guest account (idp={str(idp)[:80]})")
        return
    if cfg.kind == idp_kinds.GOOGLE:
        from app.services.identity.oidc import GOOGLE_ISSUERS

        if iss not in GOOGLE_ISSUERS:
            raise SsoError("tenant", f"iss={str(iss)[:90]}")
        hd = str(claims.get("hd") or "").lower()
        if not hd or hd not in cfg.hosted_domains:  # a personal gmail.com account has no hd
            raise SsoError("tenant", f"hd={hd[:80] or '-'}")
        return
    if iss != cfg.issuer:
        raise SsoError("tenant", f"iss={str(iss)[:90]}")


def _normalise_claims(cfg: OidcClient, claims: dict[str, Any]) -> dict[str, Any]:
    """Adds the provider-independent keys the sign-in code reads: ``_kind``, ``_sub`` / ``_ns`` (the identity),
    ``_roles`` / ``_groups`` (the mapping), ``_trust_email``."""
    claims["_kind"] = cfg.kind
    claims["_trust_email"] = cfg.trust_email
    if cfg.kind == idp_kinds.ENTRA:
        oid = str(claims.get("oid") or "").lower()
        if not _GUID_RX.match(oid):
            raise SsoError("invalid_token", "claims: oid is not a GUID")
        claims["oid"] = oid
        claims["_sub"], claims["_ns"] = oid, str(claims["tid"]).lower()
        claims["_roles"] = _claim_values(claims.get("roles"))
        claims["_groups"] = [g.lower() for g in _claim_values(claims.get("groups"))]
        return claims
    sub = str(claims.get("sub") or "")
    if not sub or len(sub) > 255 or any(ord(ch) < 32 for ch in sub):
        raise SsoError("invalid_token", "claims: unusable sub")
    claims["_sub"], claims["_ns"] = sub, cfg.tenant_id
    claims["_roles"] = _claim_values(claims.get(cfg.roles_claim))
    claims["_groups"] = _claim_values(claims.get(cfg.groups_claim))
    return claims


async def validate_id_token(cfg: OidcClient, id_token: Any, nonce_hash: str | None) -> dict[str, Any]:
    """Signature (the provider's JWKS), the issuer per kind (``tenant``; Entra guests ``guest``), ``aud``,
    ``exp`` / ``nbf``, ``nonce``, the subject (``invalid_token``). Raises :class:`SsoError`."""
    if not isinstance(id_token, str) or not id_token or not nonce_hash:
        raise SsoError("invalid_token", "no id_token")
    keyset = await jwks(cfg.jwks_uri)
    algs = list(cfg.algorithms or ("RS256",))
    try:
        try:
            token = jwt.decode(id_token, keyset, algorithms=algs)
        except InvalidKeyIdError:
            kid = ""
            try:
                kid = str(jws.extract_compact(id_token.encode("ascii")).headers().get("kid") or "")[:64]
            except Exception:  # noqa: BLE001 - malformed header: decode below fails the same way
                kid = ""
            keyset = await jwks(cfg.jwks_uri, unknown_kid=kid)
            token = jwt.decode(id_token, keyset, algorithms=algs)
    except JoseError as exc:
        raise SsoError("invalid_token", f"signature: {exc.error}") from exc
    except ValueError as exc:
        raise SsoError("invalid_token", "malformed id_token") from exc
    claims = {k: v for k, v in dict(token.claims).items() if not k.startswith("_") or k == "_claim_names"}
    _check_issuer(cfg, claims)
    try:
        _registry(cfg).validate(claims)
    except JoseError as exc:
        raise SsoError("invalid_token", f"claims: {exc.error} {exc.description or ''}".strip()) from exc
    aud = claims.get("aud")
    if isinstance(aud, list) and (len(aud) != 1 or claims.get("azp") not in (None, cfg.client_id)):
        raise SsoError("invalid_token", "claims: several audiences")
    if not hmac.compare_digest(_hash(str(claims.get("nonce"))), nonce_hash):
        raise SsoError("invalid_token", "claims: nonce mismatch")
    return _normalise_claims(cfg, claims)


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in ("1", "true")


def verified_identifiers(claims: dict[str, Any]) -> list[str]:
    """Folded UPN / e-mail values the provider vouches for. Entra: the member's UPN (``preferred_username`` /
    ``upn``) and the ``email`` claim only with ``xms_edov`` (e-mail domain owner verified). Google / OIDC: ``email``
    with ``email_verified`` (or the provider's "trust the e-mail" switch, ADFS); SAML: the ``mail`` attribute. In
    order of preference for the account e-mail."""
    kind = claims.get("_kind", idp_kinds.ENTRA)
    if kind != idp_kinds.ENTRA:
        e = _fold_email(claims.get("email"))
        if e and (_truthy(claims.get("email_verified")) or claims.get("_trust_email")):
            return [e]
        return []
    out: list[str] = []
    edov = claims.get("xms_edov")
    if edov is True or str(edov).lower() in ("1", "true"):
        e = _fold_email(claims.get("email"))
        if e:
            out.append(e)
    for key in ("preferred_username", "upn"):
        e = _fold_email(claims.get(key))
        if e and e not in out:
            out.append(e)
    return out


# --------------------------------------------------------------------------------------------------
# Flow: start, callback, ticket exchange, link
# --------------------------------------------------------------------------------------------------


def _oauth(cfg: OidcClient) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        token_endpoint_auth_method=cfg.auth_method,
        scope=cfg.scopes,
        redirect_uri=cfg.redirect_uri,
        code_challenge_method="S256",
        timeout=HTTP_TIMEOUT_S,
        follow_redirects=False,
        transport=transport,
    )


async def _purge_expired(db: AsyncSession) -> None:
    await db.execute(delete(SsoAuthState).where(SsoAuthState.expires_at < utcnow()))


async def _authorize(
    db: AsyncSession,
    cfg: OidcClient,
    purpose: str,
    *,
    user_id: int | None,
    return_path: str | None,
    data: dict[str, Any] | None = None,
    prompt: str | None = None,
    login_hint: str | None = None,
) -> str:
    await _purge_expired(db)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, _challenge = pkce_pair()  # the same PKCE helper as the calendar connectors
    db.add(
        SsoAuthState(
            state_hash=_hash(state),
            provider=cfg.slug,
            purpose=purpose,
            nonce_hash=_hash(nonce),
            code_verifier_enc=encrypt_secret(verifier),
            user_id=user_id,
            return_path=return_path,
            data=data,
            expires_at=utcnow() + STATE_TTL,
        )
    )
    await db.flush()
    extra: dict[str, str] = dict(cfg.extra_authorize)
    if cfg.kind == idp_kinds.ENTRA:
        extra.update(response_mode="query", prompt=prompt if prompt in PROMPTS else "select_account")
    elif cfg.kind == idp_kinds.GOOGLE:
        extra["prompt"] = prompt if prompt in PROMPTS else "select_account"
    elif prompt in PROMPTS:
        extra["prompt"] = str(prompt)
    if purpose == "test":
        extra["prompt"] = "login" if cfg.kind != idp_kinds.GOOGLE else "select_account"
    if login_hint:
        extra["login_hint"] = login_hint
    async with _oauth(cfg) as client:
        url, _ = client.create_authorization_url(
            cfg.authorize_endpoint, state=state, code_verifier=verifier, nonce=nonce, **extra
        )
    return str(url)


async def error_url(db: AsyncSession, code: str, *, link: bool = False, **params: str) -> str:
    """``/login?error=<code>[&ref=…]`` (``/profile?error=…`` for a link). ``code`` is a public code."""
    base, _ = await public_base(db)
    query = urlencode({"error": code, **{k: v for k, v in params.items() if v}})
    return f"{base}{'/profile' if link else '/login'}?{query}"


async def test_done_url(db: AsyncSession, ok: bool) -> str:
    base, _ = await public_base(db)
    return f"{base}/api/v1/auth/sso/test-done?{urlencode({'ok': '1' if ok else '0'})}"


async def _invite_by_token(db: AsyncSession, token: str | None) -> SsoInvite | None:
    if not token:
        return None
    q = select(SsoInvite).where(SsoInvite.token_hash == _hash(token[:256]))
    return (await db.execute(q)).scalar_one_or_none()


async def _login_invite(db: AsyncSession, slug: str, invite: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """(state data, login hint) of a sign-in started from ``/login?invite=``. Raises :class:`SsoError`."""
    if not invite:
        return None, None
    inv = await _invite_by_token(db, invite)
    if inv is None:
        raise SsoError("invite_invalid", "unknown invite token")
    if inv.expires_at < utcnow():
        raise SsoError("invite_expired", f"invite {inv.id} expired", user_id=inv.user_id)
    if inv.provider != slug:
        raise SsoError("invite_provider", f"invite {inv.id} is for {inv.provider}", user_id=inv.user_id)
    return {"invite_id": inv.id}, inv.email


async def start_login(
    db: AsyncSession,
    next_path: str | None,
    *,
    invite: str | None = None,
    prompt: str | None = None,
    login_hint: str | None = None,
    slug: str = PROVIDER,
) -> str:
    """Authorize URL (or SAML AuthnRequest URL) for a sign-in. Raises :class:`SsoError` (``not_configured``,
    ``invite_invalid``, ``invite_expired``, ``invite_provider``). The caller commits."""
    row = await get_provider(db, slug=slug)
    if row is not None and row.kind == idp_kinds.SAML:
        return await start_saml(db, row, next_path, invite=invite)
    active = await active_client(db, slug)
    if active is None:
        raise SsoError("not_configured")
    data, invited = await _login_invite(db, slug, invite)
    hint = _fold_email(login_hint) or invited
    return await _authorize(
        db,
        active[1],
        "login",
        user_id=None,
        return_path=safe_return_path(next_path),
        data=data,
        prompt=prompt,
        login_hint=hint,
    )


async def _identity_of(db: AsyncSession, user_id: int, slug: str = PROVIDER) -> UserIdentity | None:
    q = select(UserIdentity).where(UserIdentity.user_id == user_id, UserIdentity.provider == slug)
    return (await db.execute(q)).scalar_one_or_none()


async def _any_identity(db: AsyncSession, user_id: int) -> UserIdentity | None:
    q = select(UserIdentity).where(UserIdentity.user_id == user_id).order_by(UserIdentity.id)
    return (await db.execute(q)).scalars().first()


async def start_link(db: AsyncSession, user: User, password: str, slug: str = PROVIDER) -> str:
    """A signed-in user links their account at the provider; the password proves the local sign-in now."""
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise SsoAdminError(403, "password", "the password is not correct", "Parola doğru değil")
    if await _identity_of(db, user.id, slug) is not None:
        raise SsoAdminError(409, "already_linked", MESSAGES["already_linked"]["en"], MESSAGES["already_linked"]["tr"])
    active = await active_client(db, slug)
    if active is None:
        raise SsoAdminError(
            409,
            "not_configured",
            "Sign-in with Microsoft is not enabled on this installation",
            "Microsoft ile giriş bu kurulumda etkin değil",
        )
    return await _authorize(db, active[1], "link", user_id=user.id, return_path=None)


async def refuse(
    db: AsyncSession, err: SsoError, purpose: str, claims: dict[str, Any] | None = None, slug: str = PROVIDER
) -> str:
    """Audit the refusal (``auth.login_refused``, the precise reason) and answer the panel URL with the public code
    and the audit row as ``ref``."""
    row = await get_provider(db, slug=slug)
    method = "saml" if row is not None and row.kind == idp_kinds.SAML else "oidc"
    after: dict[str, Any] = {"reason": err.code, "auth_method": method, "provider": slug, "purpose": purpose}
    if err.detail:
        after["detail"] = err.detail
    if claims:
        if claims.get("_kind", idp_kinds.ENTRA) == idp_kinds.ENTRA:
            after["tid"], after["oid"] = claims.get("tid"), claims.get("oid")
        else:
            after["iss"], after["sub"] = str(claims.get("iss"))[:120], str(claims.get("_sub"))[:120]
    log.info("SSO sign-in refused (%s): %s (%s)", slug, err.code, err.detail)
    ev = await audit.record(db, "auth.login_refused", "user", err.user_id, after=after)
    ref = f"S-{ev.id}"
    await db.commit()
    if purpose == "test":
        return await test_done_url(db, False)
    public = PUBLIC_CODES.get(err.code, "failed")
    params = {"ref": ref} if public == "failed" else {}
    if public in ("domain", "invite_provider", "tenant", "unavailable", "signup_closed", "cancelled"):
        params["provider"] = slug
    return await error_url(db, public, link=purpose == "link", **params, **err.extra)


async def _take_state(db: AsyncSession, state: str | None, slug: str) -> SsoAuthState | None:
    row = None
    if state:
        q = select(SsoAuthState).where(SsoAuthState.state_hash == _hash(state[:512]))
        row = (await db.execute(q)).scalar_one_or_none()
    if row is None or row.purpose not in ("login", "link", "test") or row.provider != slug or row.expires_at < utcnow():
        if row is not None:
            await db.delete(row)
        return None
    return row


async def finish(
    db: AsyncSession, *, code: str | None, state: str | None, error: str | None, slug: str = PROVIDER
) -> str:
    """The browser's return from the OIDC provider. Always answers a URL: ``/login/sso?ticket=…[&next][&welcome]``
    (sign-in), ``/profile?sso=linked`` (link), the test page (an administrator's test login) or
    ``/login?error=<code>[&ref][&invite]``."""
    row = await _take_state(db, state, slug)
    if row is None:
        return await refuse(db, SsoError("state", "unknown, used or expired state"), "login", slug=slug)
    purpose, link_user_id, return_path, nonce_hash = row.purpose, row.user_id, row.return_path, row.nonce_hash
    data = dict(row.data or {})
    try:
        verifier = decrypt_secret(row.code_verifier_enc) if row.code_verifier_enc else ""
    except ValueError:
        verifier = ""
    await db.delete(row)  # single use, whatever happens next
    await db.commit()
    if error or not code:
        err = SsoError("denied", str(error or "no code"))
        if purpose == "test":
            return await _finish_test(db, slug, data, None, err)
        return await refuse(db, err, purpose, slug=slug)
    prov = await get_provider(db, slug=slug)
    cfg = await client_config(db, prov) if prov is not None else None
    if prov is None or cfg is None or (not prov.enabled and purpose != "test"):
        return await refuse(db, SsoError("not_configured"), purpose, slug=slug)
    if not verifier:
        return await refuse(db, SsoError("state", "verifier unreadable"), purpose, slug=slug)
    claims: dict[str, Any] | None = None
    try:
        claims = await _exchange_and_validate(cfg, code[:4096], verifier, nonce_hash)
        if purpose == "test":
            return await _finish_test(db, slug, data, claims, None)
        if purpose == "link":
            return await _finish_link(db, link_user_id, cfg, claims)
        user, welcome = await _resolve_login(db, prov, cfg, claims, data.get("invite_id"))
    except SsoError as err:
        await db.rollback()
        if purpose == "test":
            return await _finish_test(db, slug, data, claims, err)
        return await refuse(db, err, purpose, claims, slug=slug)
    return await _issue_ticket(db, user, return_path, welcome)


async def _exchange_and_validate(cfg: OidcClient, code: str, verifier: str, nonce_hash: str | None) -> dict[str, Any]:
    try:
        async with _oauth(cfg) as client:
            token = await client.fetch_token(
                cfg.token_endpoint, grant_type="authorization_code", code=code, code_verifier=verifier
            )
    except http.HTTPError as exc:
        raise SsoError("unavailable", f"token endpoint {type(exc).__name__}") from exc
    except Exception as exc:  # noqa: BLE001 - OAuthError (invalid_grant ...), bad JSON
        desc = str(getattr(exc, "description", "") or "")[:120]
        raise SsoError("exchange", f"token: {getattr(exc, 'error', type(exc).__name__)} {desc}".strip()) from exc
    id_token = token.get("id_token") if isinstance(token, dict) else None
    # the access and refresh tokens are not needed: nothing of them is stored or logged
    del token
    return await validate_id_token(cfg, id_token, nonce_hash)


# --------------------------------------------------------------------------------------------------
# SAML 2.0 (HTTP-Redirect request, HTTP-POST response; app/services/identity/saml.py)
# --------------------------------------------------------------------------------------------------


async def start_saml(
    db: AsyncSession,
    row: SsoProvider,
    next_path: str | None,
    *,
    invite: str | None = None,
    purpose: str = "login",
    data: dict[str, Any] | None = None,
) -> str:
    """The IdP's SSO URL with a deflated AuthnRequest; ``RelayState`` is the state (hashed in ``sso_auth_states``
    with the request id, so ``InResponseTo`` is checked on the way back)."""
    if not idp_saml.AVAILABLE:
        raise SsoError("unavailable", "SAML library (signxml) not installed")
    cfg = await saml_config(db, row)
    if cfg is None or (purpose == "login" and not row.enabled):
        raise SsoError("not_configured")
    state_data = dict(data or {})
    if purpose == "login":
        inv_data, _hint = await _login_invite(db, row.name, invite)
        state_data.update(inv_data or {})
    await _purge_expired(db)
    state, request_id = secrets.token_urlsafe(32), "_" + secrets.token_hex(20)
    state_data["request_id"] = request_id
    db.add(
        SsoAuthState(
            state_hash=_hash(state),
            provider=row.name,
            purpose=purpose,
            nonce_hash=_hash(request_id),
            return_path=safe_return_path(next_path),
            data=state_data,
            expires_at=utcnow() + STATE_TTL,
        )
    )
    await db.flush()
    return idp_saml.authn_request_url(cfg, request_id, state, datetime.now(UTC))


async def finish_saml(db: AsyncSession, *, slug: str, saml_response: str | None, relay_state: str | None) -> str:
    """The IdP's POST to the ACS. Same answers as :func:`finish`."""
    row = await _take_state(db, relay_state, slug)
    if row is None or row.purpose == "link":
        return await refuse(db, SsoError("state", "unknown, used or expired RelayState"), "login", slug=slug)
    purpose, return_path, data = row.purpose, row.return_path, dict(row.data or {})
    request_id = str(data.get("request_id") or "")
    await db.delete(row)
    await db.commit()
    prov = await get_provider(db, slug=slug)
    cfg = await saml_config(db, prov) if prov is not None else None
    if prov is None or cfg is None or (not prov.enabled and purpose != "test"):
        return await refuse(db, SsoError("not_configured"), purpose, slug=slug)
    if not saml_response:
        err = SsoError("denied", "no SAMLResponse")
        return await (
            _finish_test(db, slug, data, None, err) if purpose == "test" else refuse(db, err, purpose, slug=slug)
        )
    claims: dict[str, Any] | None = None
    try:
        try:
            claims = idp_saml.parse_response(cfg, saml_response[: 2 * idp_saml.MAX_XML], request_id, datetime.now(UTC))
        except idp_saml.SamlError as exc:
            raise SsoError(exc.code, exc.detail) from exc
        claims["_kind"] = idp_kinds.SAML
        claims["_trust_email"] = True
        claims["_roles"] = []
        claims["_groups"] = list(claims.get("groups") or [])
        if purpose == "test":
            return await _finish_test(db, slug, data, claims, None)
        user, welcome = await _resolve_login(db, prov, cfg, claims, data.get("invite_id"))
    except SsoError as err:
        await db.rollback()
        if purpose == "test":
            return await _finish_test(db, slug, data, claims, err)
        return await refuse(db, err, purpose, claims, slug=slug)
    return await _issue_ticket(db, user, return_path, welcome)


# --------------------------------------------------------------------------------------------------
# Test login (an administrator runs the full flow in a popup; the claims are reported, nothing is stored but the
# claim summary for 10 minutes; no account is created, bound or signed in)
# --------------------------------------------------------------------------------------------------

#: claims never echoed to the test report (protocol values, not facts about the user)
_TEST_HIDDEN = frozenset({"nonce", "at_hash", "c_hash", "sid", "uti", "rh", "aio", "_attributes"})


async def start_test(db: AsyncSession, actor: User, row: SsoProvider) -> tuple[str, str]:
    """(authorize URL, test id). Works while the provider is still off (that is the point of the test)."""
    test_id = secrets.token_urlsafe(18)
    data = {"test_id": test_id, "actor_id": actor.id}
    if row.kind == idp_kinds.SAML:
        url = await start_saml(db, row, None, purpose="test", data=data)
    else:
        cfg = await client_config(db, row)
        if cfg is None:
            raise SsoError("not_configured")
        url = await _authorize(db, cfg, "test", user_id=actor.id, return_path=None, data=data)
    db.add(
        SsoAuthState(
            state_hash=_hash("test:" + test_id),
            provider=row.name,
            purpose="result",
            user_id=actor.id,
            data={"status": "pending"},
            expires_at=utcnow() + STATE_TTL,
        )
    )
    await db.flush()
    return url, test_id


async def _finish_test(
    db: AsyncSession, slug: str, data: dict[str, Any], claims: dict[str, Any] | None, err: SsoError | None
) -> str:
    test_id = str(data.get("test_id") or "")
    q = select(SsoAuthState).where(
        SsoAuthState.state_hash == _hash("test:" + test_id), SsoAuthState.purpose == "result"
    )
    res = (await db.execute(q)).scalar_one_or_none()
    prov = await get_provider(db, slug=slug)
    report: dict[str, Any] = {"status": "done", "ok": err is None, "at": utcnow().isoformat(timespec="seconds")}
    if err is not None:
        public = PUBLIC_CODES.get(err.code, "failed")
        from app.services.identity import errors as idp_errors

        report.update(code=public, reason=err.code, detail=err.detail)
        report["hint"] = idp_errors.translate(f"{err.detail} {err.code}")
    if claims:
        shown = {k: v for k, v in claims.items() if not k.startswith("_") and k not in _TEST_HIDDEN}
        report["claims"] = {k: (v if isinstance(v, (str, int, bool, list)) else str(v)) for k, v in shown.items()}
        if claims.get("_attributes"):
            report["attributes"] = claims["_attributes"]
        ids = verified_identifiers(claims)
        report["verified_email"] = ids[0] if ids else None
        report["subject"] = str(claims.get("_sub") or "")[:255]
        report["groups"] = list(claims.get("_groups") or [])[:50]
        report["roles"] = list(claims.get("_roles") or [])[:50]
        if prov is not None:
            report["domain_ok"] = _domain_allowed(prov, ids)
            target, why = await _mapped_role(db, prov, claims)
            report["mapped_role"] = _role_ref(target) if target is not None and why == "mapping" else None
    if prov is not None:
        # the guided setup unlocks "Etkinleştir" only after a successful round trip (design v3 §5.4)
        prov.options = {**(prov.options or {}), "test_ok": err is None, "test_at": report["at"]}
        prov.last_check_at, prov.last_check_ok = utcnow(), err is None
        prov.last_check_detail = ("test login ok" if err is None else f"test login: {err.code}")[:255]
    if res is not None:
        res.data = report
    actor = await db.get(User, int(data["actor_id"])) if data.get("actor_id") else None
    await audit.record(
        db,
        "sso.test_login",
        "sso_provider",
        prov.id if prov is not None else None,
        after={"provider": slug, "ok": err is None, "reason": err.code if err else None},
        actor=actor,
    )
    await db.commit()
    return await test_done_url(db, err is None)


async def test_result(db: AsyncSession, actor: User, row: SsoProvider, test_id: str) -> dict[str, Any] | None:
    q = select(SsoAuthState).where(
        SsoAuthState.state_hash == _hash("test:" + test_id[:64]),
        SsoAuthState.purpose == "result",
        SsoAuthState.provider == row.name,
    )
    res = (await db.execute(q)).scalar_one_or_none()
    if res is None or res.expires_at < utcnow():
        return None
    return dict(res.data or {"status": "pending"})


# --------------------------------------------------------------------------------------------------
# Identity resolution (every kind)
# --------------------------------------------------------------------------------------------------


async def _find_identity(db: AsyncSession, cfg: Any, claims: dict[str, Any]) -> UserIdentity | None:
    q = select(UserIdentity).where(
        UserIdentity.provider == cfg.slug,
        UserIdentity.tenant_id == str(claims["_ns"]),
        UserIdentity.subject == str(claims["_sub"]),
    )
    return (await db.execute(q)).scalar_one_or_none()


def _new_identity(user_id: int, cfg: Any, claims: dict[str, Any], origin: str) -> UserIdentity:
    return UserIdentity(
        user_id=user_id,
        provider=cfg.slug,
        issuer=str(cfg.issuer)[:255],
        tenant_id=str(claims["_ns"]),
        subject=str(claims["_sub"]),
        origin=origin,
    )


def _touch(ident: UserIdentity, claims: dict[str, Any]) -> None:
    ids = verified_identifiers(claims)
    ident.email_at_login = ids[0] if ids else _fold_email(claims.get("email"))
    ident.display_name = clean_display_name(claims.get("name"))
    ident.last_login_at = utcnow()


def _domain_allowed(prov: SsoProvider, verified: list[str]) -> bool:
    """``allowed_domains`` empty: every address; else the account's verified address must be in one of them."""
    domains = [d for d in prov.allowed_domains or [] if isinstance(d, str) and d]
    if not domains:
        return True
    return any(e.rsplit("@", 1)[-1] in domains for e in verified)


def _identity_facts(ident: UserIdentity, claims: dict[str, Any]) -> dict[str, Any]:
    if claims.get("_kind", idp_kinds.ENTRA) == idp_kinds.ENTRA:
        return {"tid": ident.tenant_id, "oid": ident.subject}
    return {"iss": ident.issuer, "sub": ident.subject}


async def _resolve_login(
    db: AsyncSession, prov: SsoProvider, cfg: Any, claims: dict[str, Any], invite_id: Any
) -> tuple[User, dict[str, Any] | None]:
    """(user, welcome) -- ``welcome`` is set on the sign-in that created or bound the account."""
    if not _domain_allowed(prov, verified_identifiers(claims)):
        raise SsoError("domain", "verified address outside allowed_domains")
    ident = await _find_identity(db, cfg, claims)
    user = await db.get(User, ident.user_id) if ident is not None else None
    if ident is not None and user is None:  # orphan (no FK enforcement): the identity starts over
        await db.delete(ident)
        await db.flush()
        ident = None
    welcome: dict[str, Any] | None = None
    if user is None:
        user, ident, welcome = await _first_login(db, prov, cfg, claims, invite_id)
    assert ident is not None
    if not user.is_active:
        raise SsoError("disabled", "account disabled", user_id=user.id)
    _touch(ident, claims)
    await _apply_mapping(db, prov, user, claims)
    from app.services import mfa as _mfa  # AU-16: MFA asserted by the provider when the policy requires it

    await _mfa.idp_mfa_gate(db, prov, user, claims)
    user.last_login_at = utcnow()
    method = "saml" if prov.kind == idp_kinds.SAML else "oidc"
    await events.emit(db, "user.logged_in", {"user_id": user.id, "auth_method": method})
    await audit.record(
        db,
        "auth.login",
        "user",
        user.id,
        after={"auth_method": method, "provider": prov.name, **_identity_facts(ident, claims)},
        actor=user,
    )
    return user, welcome


async def _bind(
    db: AsyncSession, inv: SsoInvite, cfg: Any, claims: dict[str, Any]
) -> tuple[User, UserIdentity, dict[str, Any]]:
    target = await db.get(User, inv.user_id)
    if target is None or await _identity_of(db, target.id, cfg.slug) is not None:
        raise SsoError("invite_invalid", f"invite {inv.id}: account gone or already bound", user_id=inv.user_id)
    inviter = await db.get(User, inv.created_by) if inv.created_by else None
    ident = _new_identity(target.id, cfg, claims, inv.kind)
    db.add(ident)
    kind, email, invite_id = inv.kind, inv.email, inv.id
    await db.delete(inv)  # one time
    await db.flush()
    facts = {
        "kind": kind,
        "email": email,
        "invite_id": invite_id,
        "provider": cfg.slug,
        **_identity_facts(ident, claims),
    }
    if kind == "invite":
        await audit.record(db, "user.invite_accepted", "user", target.id, after=facts, actor=target)
    await audit.record(db, "auth.identity_bound", "user", target.id, after=facts, actor=target)
    welcome = {"welcome": "invited" if kind == "invite" else "bound", "inviter": audit.user_label(inviter)}
    return target, ident, welcome


async def _first_login(
    db: AsyncSession, prov: SsoProvider, cfg: Any, claims: dict[str, Any], invite_id: Any
) -> tuple[User, UserIdentity, dict[str, Any]]:
    verified = verified_identifiers(claims)
    if invite_id is not None:  # started from an invite link
        inv = await db.get(SsoInvite, int(invite_id))
        if inv is None or inv.provider != prov.name:
            raise SsoError("invite_invalid", f"invite {invite_id} revoked or used")
        if inv.expires_at < utcnow():
            raise SsoError("invite_expired", f"invite {inv.id} expired", user_id=inv.user_id)
        if inv.email not in verified:
            extra = {
                "invite": decrypt_secret(inv.token_enc),
                "invited_masked": mask_email(inv.email) or "",
                "signed_in": mask_email(verified[0] if verified else None) or "",
            }
            raise SsoError("invite_mismatch", f"invite {inv.id}", user_id=inv.user_id, extra=extra)
        return await _bind(db, inv, cfg, claims)
    if verified:
        q = select(SsoInvite).where(SsoInvite.email.in_(verified))
        inv = (await db.execute(q.order_by(SsoInvite.id))).scalars().first()
        if inv is not None:
            if inv.provider != prov.name:
                raise SsoError("invite_provider", f"invite {inv.id} is for {inv.provider}", user_id=inv.user_id)
            if inv.expires_at < utcnow():
                raise SsoError("invite_expired", f"invite {inv.id} expired", user_id=inv.user_id)
            return await _bind(db, inv, cfg, claims)
        clash = (await db.execute(select(User.id).where(User.email.in_(verified)))).scalars().first()
        if clash is not None:  # never linked by e-mail: an admin's invite or a confirmed link only
            raise SsoError(
                "account_exists", "verified address equals an existing account without an invite", user_id=clash
            )
    if not prov.self_signup or prov.invite_only:
        raise SsoError("signup_closed", "no account and self sign-up off (invite only)")
    role = await _default_role(db, prov)
    if role is not None and _too_privileged_for_default(role):
        role = (await db.execute(select(Role).where(Role.code == "TEACHER"))).scalar_one_or_none()
    user = User(
        email=verified[0] if verified else None,
        full_name=clean_display_name(claims.get("name")),
        is_active=True,
        auth_source="oidc",
        password_hash=None,
        force_password_reset=False,
    )
    set_user_role(user, role)
    db.add(user)
    await db.flush()
    ident = _new_identity(user.id, cfg, claims, "provision")
    db.add(ident)
    await db.flush()
    await audit.record(
        db,
        "auth.self_signup",
        "user",
        user.id,
        after={"role": user.role, "email": user.email, "provider": prov.name, **_identity_facts(ident, claims)},
        actor=user,
    )
    from app.services.identity.invites import send_account_created

    await send_account_created(db, user, "sso")
    return user, ident, {"welcome": "self"}


async def _finish_link(db: AsyncSession, user_id: int | None, cfg: Any, claims: dict[str, Any]) -> str:
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise SsoError("link_user", "link user gone or disabled", user_id=user_id)
    ident = await _find_identity(db, cfg, claims)
    if ident is not None and ident.user_id != user.id:
        raise SsoError("already_linked", "identity belongs to another account", user_id=user.id)
    own = await _identity_of(db, user.id, cfg.slug)
    if own is not None and ident is None:
        raise SsoError("already_linked", "account linked to another identity", user_id=user.id)
    if ident is None:
        ident = _new_identity(user.id, cfg, claims, "link")
        db.add(ident)
    _touch(ident, claims)
    await db.execute(delete(SsoInvite).where(SsoInvite.user_id == user.id))
    await db.flush()
    await audit.record(
        db,
        "auth.identity_bound",
        "user",
        user.id,
        after={
            "kind": "link",
            "provider": cfg.slug,
            **_identity_facts(ident, claims),
            "email_at_login": ident.email_at_login,
        },
        actor=user,
    )
    await db.commit()
    base, _ = await public_base(db)
    return f"{base}/profile?sso=linked"


async def _issue_ticket(db: AsyncSession, user: User, return_path: str | None, welcome: dict[str, Any] | None) -> str:
    ticket = secrets.token_urlsafe(32)
    db.add(
        SsoAuthState(
            state_hash=_hash(ticket),
            provider=PROVIDER,
            purpose="ticket",
            user_id=user.id,
            return_path=return_path,
            data=welcome,
            expires_at=utcnow() + TICKET_TTL,
        )
    )
    await db.commit()
    base, _ = await public_base(db)
    params = {"ticket": ticket}
    if return_path:
        params["next"] = return_path
    if welcome:
        params["welcome"] = str(welcome["welcome"])
    return f"{base}/login/sso?{urlencode(params)}"


@dataclass(frozen=True)
class Exchanged:
    user: User
    next: str | None
    welcome: str | None
    inviter_name: str | None


async def exchange_ticket(db: AsyncSession, ticket: str) -> Exchanged | None:
    """The one-time ticket -> its user (``None``: unknown, used, expired or the account was disabled since)."""
    q = select(SsoAuthState).where(SsoAuthState.state_hash == _hash(ticket))
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None or row.purpose != "ticket":
        return None
    user_id, expired, next_path, data = row.user_id, row.expires_at < utcnow(), row.return_path, dict(row.data or {})
    await db.delete(row)
    await db.commit()
    user = await db.get(User, user_id) if user_id and not expired else None
    if user is None or not user.is_active:
        return None
    return Exchanged(user, next_path, data.get("welcome"), data.get("inviter"))


async def me(db: AsyncSession, user: User) -> dict[str, Any]:
    ident = await _identity_of(db, user.id)
    pending = (
        await db.execute(select(SsoInvite.id).where(SsoInvite.user_id == user.id, SsoInvite.expires_at >= utcnow()))
    ).scalar_one_or_none()
    out: dict[str, Any] = {"linked": ident is not None, "pending_bind": pending is not None}
    if ident is not None:
        out.update(
            email_at_login=ident.email_at_login,
            display_name=ident.display_name,
            linked_at=ident.created_at,
            last_login_at=ident.last_login_at,
        )
    out["has_password"] = bool(user.password_hash)
    return out


async def unlink_own(db: AsyncSession, user: User) -> None:
    ident = await _identity_of(db, user.id)
    if ident is None:
        raise SsoAdminError(404, "not_linked", "no Microsoft account is linked", "Bağlı bir Microsoft hesabı yok")
    if not user.password_hash:
        raise SsoAdminError(
            409,
            "last_sign_in",
            "unlinking would leave this account without any way to sign in; ask an administrator to set a password "
            "first",
            "Bağlantıyı kaldırmak bu hesabı giriş yolu olmadan bırakır; önce yöneticinizden bir parola isteyin",
        )
    before = {"tid": ident.tenant_id, "oid": ident.subject}
    await db.delete(ident)
    await db.flush()
    await audit.record(db, "auth.identity_unbound", "user", user.id, before=before, actor=user)


# --------------------------------------------------------------------------------------------------
# Invites, "bind on next SSO login", instructor link (setup.users, no escalation)
# --------------------------------------------------------------------------------------------------


LOCAL = "local"
LOCAL_LABEL = {"tr": "Yerel parola", "en": "Local password"}


async def _provider_names(db: AsyncSession) -> dict[str, SsoProvider]:
    return {p.name: p for p in (await db.execute(select(SsoProvider))).scalars()}


async def _invite_out(db: AsyncSession, inv: SsoInvite, *, with_link: bool = True) -> dict[str, Any]:
    """An invite for the admin screens. The link (the token) is shown once: in the answer that created or renewed it
    (round-1 R1-M-25, T-R1-35); the list never repeats it (``with_link=False``)."""
    base, _ = await public_base(db)
    token = ""
    if with_link:
        try:
            token = decrypt_secret(inv.token_enc)
        except ValueError:
            token = ""
    prov = None if inv.provider == LOCAL else await get_provider(db, slug=inv.provider)
    return {
        "id": inv.id,
        "user_id": inv.user_id,
        "email": inv.email,
        "kind": inv.kind,
        "provider": inv.provider,
        "provider_kind": prov.kind if prov is not None else LOCAL,
        "provider_label": provider_label(prov) if prov is not None else LOCAL_LABEL["tr"],
        "status": "invite_expired" if inv.expires_at < utcnow() else "invited",
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "created_by": inv.created_by,
        "link": f"{base}/login?{urlencode({'invite': token})}" if token else None,
    }


async def _resolve_role(db: AsyncSession, role_id: int | None, code: str | None, prov: SsoProvider | None) -> Role:
    if role_id is not None:
        role = await db.get(Role, role_id)
    elif code:
        role = (await db.execute(select(Role).where(Role.code == code.strip().upper()))).scalar_one_or_none()
    else:
        role = await _default_role(db, prov)
    if role is None:
        raise SsoAdminError(422, "unknown_role", f"unknown role {role_id or code}", "bilinmeyen rol")
    return role


def _clean_invite_email(value: str | None) -> str:
    email = _fold_email(value)
    if not email:
        raise SsoAdminError(
            422,
            "invalid_email",
            "give the user's institution e-mail / UPN (name@university.edu.tr)",
            "Kullanıcının kurumsal e-posta adresini / UPN'sini girin (ad@universite.edu.tr)",
        )
    return email


def _new_token(inv: SsoInvite) -> None:
    token = secrets.token_urlsafe(24)
    inv.token_hash, inv.token_enc = _hash(token), encrypt_secret(token)


async def invite_provider(db: AsyncSession, slug: str | None) -> tuple[str, SsoProvider]:
    """(the slug an invite is for, the provider row whose ``invite_days`` / default role apply). ``local``: a password
    set from the invite link; its days and default role are the original Entra row's."""
    name = (slug or PROVIDER).strip().lower()
    if name == LOCAL:
        prov = await get_provider(db, create=True)
        assert prov is not None
        return LOCAL, prov
    prov = await get_provider(db, create=name == PROVIDER, slug=name)
    if prov is None:
        raise SsoAdminError(
            422, "unknown_provider", f"unknown identity provider {name!r}", "Bilinmeyen kimlik sağlayıcısı"
        )
    return name, prov


async def _place_invite(
    db: AsyncSession,
    actor: User,
    user: User,
    email: str,
    kind: str,
    days: int | None,
    prov: SsoProvider,
    provider: str = PROVIDER,
) -> SsoInvite:
    other = (
        (await db.execute(select(SsoInvite).where(SsoInvite.email == email).order_by(SsoInvite.id))).scalars().first()
    )
    if other is not None and other.user_id != user.id:
        if other.expires_at >= utcnow():
            raise SsoAdminError(
                409, "invite_taken", "another account is waiting for this UPN", "Bu UPN başka bir hesaba davetli"
            )
        await db.delete(other)
    await db.execute(delete(SsoInvite).where(SsoInvite.user_id == user.id))
    await db.flush()
    inv = SsoInvite(
        provider=provider,
        user_id=user.id,
        email=email,
        kind=kind,
        created_by=actor.id,
        expires_at=utcnow() + timedelta(days=days or prov.invite_days or 30),
    )
    _new_token(inv)
    db.add(inv)
    await db.flush()
    await audit.record(
        db,
        "user.invited" if kind == "invite" else "auth.binding_scheduled",
        "user",
        user.id,
        after={"kind": kind, "email": email, "expires_at": inv.expires_at, "provider": provider},
        actor=actor,
    )
    return inv


async def create_invite(db: AsyncSession, actor: User, body: dict[str, Any]) -> dict[str, Any]:
    slug, prov = await invite_provider(db, body.get("provider"))
    email = _clean_invite_email(body.get("email"))
    holder = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    reuse: User | None = None
    if holder is not None and not holder.is_active and await unused_placeholder(db, holder):
        pending = (await db.execute(select(SsoInvite.id).where(SsoInvite.user_id == holder.id))).scalar_one_or_none()
        if pending is None:
            reuse, holder = holder, None  # the account a revoked invite disabled (T-R1-35)
    if holder is not None:
        if await _any_identity(db, holder.id) is not None:
            raise SsoAdminError(
                409,
                "account_bound",
                "this address already belongs to a bound account",
                "Bu adres zaten bağlı bir hesapta",
            )
        pending = (await db.execute(select(SsoInvite.id).where(SsoInvite.user_id == holder.id))).scalar_one_or_none()
        if pending is not None:
            raise SsoAdminError(
                409,
                "invite_pending",
                "this address has an invite already: renew it instead",
                "Bu adrese zaten bir davet var: daveti yenileyin",
            )
        raise SsoAdminError(
            409,
            "account_exists",
            f"a user with e-mail {email} already exists: mark that account 'bind on next SSO login' instead",
            f"{email} adresli bir kullanıcı zaten var: o hesabı 'sonraki Microsoft girişinde bağla' olarak işaretleyin",
        )
    role = await _resolve_role(db, body.get("role_id"), body.get("role"), prov)
    if not await may_grant_role(db, actor, role):
        raise SsoAdminError(
            403,
            "no_escalation",
            f"granting the role {role.name!r} requires permissions you do not hold",
            f"{role.name!r} rolünü vermek için sahip olmadığınız izinler gerekir",
        )
    dept = body.get("department_id")
    if dept is not None and await db.get(Program, dept) is None:
        raise SsoAdminError(422, "unknown_department", f"unknown department {dept}", "bilinmeyen bölüm")
    if reuse is not None:
        user = reuse
        user.is_active = True
        user.full_name = clean_display_name(body.get("full_name")) or user.full_name
        user.department_id = dept
    else:
        user = User(
            email=email,
            full_name=clean_display_name(body.get("full_name")),
            is_active=True,
            auth_source="local" if slug == LOCAL else "oidc",
            password_hash=None,
            force_password_reset=False,
            department_id=dept,
        )
        db.add(user)
    if reuse is not None:
        user.auth_source = "local" if slug == LOCAL else "oidc"
    set_user_role(user, role)
    await db.flush()
    inv = await _place_invite(db, actor, user, email, "invite", body.get("days"), prov, slug)
    if body.get("instructor_id") is not None:
        await set_instructor(db, actor, user.id, body["instructor_id"])
    return await _invite_out(db, inv)


async def renew_invite(db: AsyncSession, actor: User, invite_id: int) -> dict[str, Any]:
    """A fresh link and the full validity again (the old link stops working)."""
    inv = await db.get(SsoInvite, invite_id)
    if inv is None:
        raise SsoAdminError(404, "not_found", "invite not found", "Davet bulunamadı")
    prov = await get_provider(db, create=True, slug=PROVIDER if inv.provider == LOCAL else inv.provider)
    if prov is None:
        prov = await get_provider(db, create=True)
    assert prov is not None
    target = await db.get(User, inv.user_id)
    if target is not None and not await may_manage_user(db, actor, target):
        raise _no_escalation()
    inv.expires_at = utcnow() + timedelta(days=prov.invite_days or 30)
    _new_token(inv)
    await db.flush()
    await audit.record(
        db,
        "user.invite_renewed",
        "user",
        inv.user_id,
        after={"kind": inv.kind, "expires_at": inv.expires_at},
        actor=actor,
    )
    return await _invite_out(db, inv)


async def mark_bind(
    db: AsyncSession, actor: User, user_id: int, email: str | None, days: int | None, provider: str | None = None
) -> dict[str, Any]:
    slug, prov = await invite_provider(db, provider)
    if slug == LOCAL:
        raise SsoAdminError(
            422, "unknown_provider", "binding needs an identity provider", "Bağlama bir kimlik sağlayıcısı gerektirir"
        )
    target = await db.get(User, user_id)
    if target is None:
        raise SsoAdminError(404, "not_found", "user not found", "Kullanıcı bulunamadı")
    if target.id == actor.id:
        raise SsoAdminError(
            422,
            "self",
            "link your own account from Profile (it proves both sides with your password)",
            "Kendi hesabınızı Profil sayfasından bağlayın (parolanızla iki tarafı da doğrular)",
        )
    if not await may_manage_user(db, actor, target):
        raise _no_escalation()
    if await _identity_of(db, target.id, slug) is not None:
        raise SsoAdminError(409, "already_linked", MESSAGES["already_linked"]["en"], MESSAGES["already_linked"]["tr"])
    clean = _clean_invite_email(email or target.email)
    holder = (await db.execute(select(User.id).where(User.email == clean, User.id != target.id))).scalar_one_or_none()
    if holder is not None:
        raise SsoAdminError(409, "email_taken", "another account has this e-mail", "Bu e-posta başka bir hesapta")
    return await _invite_out(db, await _place_invite(db, actor, target, clean, "bind", days, prov, slug))


async def list_invites(db: AsyncSession, provider: str | None = None) -> list[dict[str, Any]]:
    q = select(SsoInvite).order_by(SsoInvite.id)
    if provider:
        q = q.where(SsoInvite.provider == provider)
    rows = (await db.execute(q)).scalars()
    return [await _invite_out(db, i, with_link=False) for i in rows]


async def unused_placeholder(db: AsyncSession, user: User) -> bool:
    """The account an invite created and nobody ever used: no password, never signed in, no linked identity (an
    identity-provider invite: ``auth_source = oidc``; a local-password invite: ``local`` without a password)."""
    return (
        user.auth_source in ("oidc", "local")
        and not user.password_hash
        and user.last_login_at is None
        and await _any_identity(db, user.id) is None
    )


async def delete_invite(db: AsyncSession, actor: User, invite_id: int) -> None:
    """Revoke an invite or cancel a scheduled binding. Revoking an invite also disables the account it created when
    nobody has used it (round-1 R1-M-25, T-R1-35: it was left 'Aktif' with no way to sign in); a bound or used account,
    and the account of a cancelled binding, stay as they are (delete them in Users). A new invite to the same address
    re-enables the placeholder."""
    inv = await db.get(SsoInvite, invite_id)
    if inv is None:
        raise SsoAdminError(404, "not_found", "invite not found", "Davet bulunamadı")
    target = await db.get(User, inv.user_id)
    if target is not None and not await may_manage_user(db, actor, target):
        raise _no_escalation()
    before = {"kind": inv.kind, "email": inv.email}
    await db.delete(inv)
    disabled = False
    if inv.kind == "invite" and target is not None and target.is_active and await unused_placeholder(db, target):
        target.is_active = False
        revoke_tokens(target)
        disabled = True
    await db.flush()
    await audit.record(
        db,
        "user.invite_revoked",
        "user",
        inv.user_id,
        before=before,
        after={"account_disabled": True} if disabled else None,
        actor=actor,
    )


async def public_invite(db: AsyncSession, token: str) -> dict[str, Any] | None:
    """The invite banner (sign-in.md §12). ``None``: unknown or used; ``{"expired": True}`` when expired."""
    inv = await _invite_by_token(db, token)
    if inv is None:
        return None
    if inv.expires_at < utcnow():
        return {"expired": True}
    target = await db.get(User, inv.user_id)
    role = await user_role(db, target) if target is not None else None
    inviter = await db.get(User, inv.created_by) if inv.created_by else None
    left = inv.expires_at - utcnow()
    prov = None if inv.provider == LOCAL else await get_provider(db, slug=inv.provider)
    return {
        "kind": inv.kind,
        #: wave 3b: which door the invite opens (``local``: set a password from the link)
        "provider": inv.provider,
        "provider_kind": prov.kind if prov is not None else LOCAL,
        "provider_label": provider_label(prov) if prov is not None else LOCAL_LABEL["tr"],
        "provider_label_en": provider_label(prov, "en") if prov is not None else LOCAL_LABEL["en"],
        "start_url": f"/api/v1/auth/sso/{inv.provider}/start" if prov is not None else None,
        "inviter_name": audit.user_label(inviter),
        "role_name": role.name if role is not None else None,
        "invited_masked": mask_email(inv.email),
        "login_hint": inv.email,
        "days_left": max(0, left.days + (1 if left.seconds else 0)),
        "expires_at": inv.expires_at,
    }


async def admin_unlink(db: AsyncSession, actor: User, user_id: int, slug: str | None = None) -> None:
    target = await db.get(User, user_id)
    if target is None:
        raise SsoAdminError(404, "not_found", "user not found", "Kullanıcı bulunamadı")
    if not await may_manage_user(db, actor, target):
        raise _no_escalation()
    ident = await (_identity_of(db, target.id, slug) if slug else _identity_of(db, target.id))
    if ident is None and not slug:
        ident = await _any_identity(db, target.id)
    if ident is None:
        raise SsoAdminError(404, "not_linked", "no Microsoft account is linked", "Bağlı bir Microsoft hesabı yok")
    before = {"tid": ident.tenant_id, "oid": ident.subject, "provider": ident.provider}
    await db.delete(ident)
    revoke_tokens(target)  # sessions opened through that identity end too
    await db.flush()
    await audit.record(db, "auth.identity_unbound", "user", target.id, before=before, actor=actor)


async def set_instructor(db: AsyncSession, actor: User, user_id: int, instructor_id: int | None) -> dict[str, Any]:
    """Link a login to an instructor record (``instructors.user_id``; flow F-05) or clear it. Audited."""
    target = await db.get(User, user_id)
    if target is None:
        raise SsoAdminError(404, "not_found", "user not found", "Kullanıcı bulunamadı")
    if not await may_manage_user(db, actor, target):
        raise _no_escalation()
    current = list((await db.execute(select(Instructor).where(Instructor.user_id == target.id))).scalars())
    before = {"instructor_ids": [i.id for i in current]}
    new: Instructor | None = None
    if instructor_id is not None:
        new = await db.get(Instructor, instructor_id)
        if new is None or new.archived:
            raise SsoAdminError(422, "unknown_instructor", "unknown instructor", "Öğretim elemanı bulunamadı")
        if new.user_id is not None and new.user_id != target.id:
            raise SsoAdminError(
                409,
                "instructor_linked",
                "this instructor is linked to another account",
                "Bu öğretim elemanı başka bir hesaba bağlı",
            )
    for i in current:
        if new is None or i.id != new.id:
            i.user_id = None
    await db.flush()
    if new is not None:
        new.user_id = target.id
    await db.flush()
    after = {"instructor_ids": [new.id] if new is not None else []}
    if after != before:
        await audit.record(db, "user.instructor_link", "user", target.id, before=before, after=after, actor=actor)
    return {"user_id": target.id, "instructor_id": new.id if new is not None else None}


async def user_status(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Per user (sign-in.md §13 columns): ``status`` (``linked`` | ``invited`` | ``invite_expired`` | ``binding`` |
    ``none``), ``auth_methods``, ``invite``, ``binding_pending``, ``self_signup_at``, ``break_glass``,
    ``instructor_id``."""
    now: datetime = utcnow()
    invites = {i.user_id: i for i in (await db.execute(select(SsoInvite))).scalars()}
    kinds_of = {p.name: p.kind for p in (await _provider_names(db)).values()}
    all_idents: dict[int, list[UserIdentity]] = {}
    for i in (await db.execute(select(UserIdentity).order_by(UserIdentity.id))).scalars():
        all_idents.setdefault(i.user_id, []).append(i)
    # the Entra identity first (the Microsoft column of the Users screen), then the others
    idents = {uid: next((i for i in rows if i.provider == PROVIDER), rows[0]) for uid, rows in all_idents.items()}
    glass = set((await db.execute(select(User.id).where(*_break_glass_filter()))).scalars())
    linked = await db.execute(select(Instructor.id, Instructor.user_id).where(Instructor.user_id.is_not(None)))
    instructors = {uid: iid for iid, uid in linked}
    out: dict[str, dict[str, Any]] = {}
    for u in (await db.execute(select(User).order_by(User.id))).scalars():
        inv, ident = invites.get(u.id), idents.get(u.id)
        methods = []
        for i in all_idents.get(u.id, []):
            kind = kinds_of.get(i.provider, idp_kinds.ENTRA)
            m = {idp_kinds.ENTRA: "microsoft", idp_kinds.GOOGLE: "google"}.get(kind, kind)
            if m not in methods:
                methods.append(m)
        if u.auth_source == "ldap":
            methods.append("ldap")
        elif u.password_hash:
            methods.append("local")
        if ident is not None:
            status = "linked"
        elif inv is not None and inv.expires_at < now:
            status = "invite_expired"
        elif inv is not None:
            status = "invited" if inv.kind == "invite" else "binding"
        else:
            status = "none"
        invite = None
        if inv is not None:
            invite = {
                "id": inv.id,
                "kind": inv.kind,
                "expires_at": inv.expires_at,
                "invited_by": inv.created_by,
                "provider": inv.provider,
            }
        out[str(u.id)] = {
            "status": status,
            "auth_methods": methods,
            "invite": invite,
            "binding_pending": inv is not None and inv.kind == "bind" and inv.expires_at >= now,
            "self_signup_at": ident.created_at if ident is not None and ident.origin == "provision" else None,
            "break_glass": u.id in glass,
            "instructor_id": instructors.get(u.id),
            "providers": [i.provider for i in all_idents.get(u.id, [])],
        }
    return out


async def providers_out(db: AsyncSession) -> dict[str, Any]:
    auth = await public_auth(db)
    ms = auth["microsoft"]
    return {
        "auth": auth,
        "providers": [{"name": PROVIDER, "label": LABEL, "enabled": ms["enabled"], "start_url": ms["start_url"]}]
        + [
            {"name": p["name"], "label": p["label"], "enabled": True, "start_url": p["start_url"], "kind": p["kind"]}
            for p in auth["providers"]
            if p["name"] != PROVIDER
        ],
        "messages": MESSAGES,
    }
