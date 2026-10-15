"""Sign-in with the institution's Microsoft Entra ID (owner decisions 2026-10-15; design and guard rules in
docs/product/2026-10-15-integrations-options.md §5.5; IT checklist docs/deploy/sso-entra.md).

Direct OpenID Connect from the backend, no broker: authorization code flow with PKCE (S256), ``state`` and ``nonce``
through Authlib's httpx client; the ID token is verified with joserfc (Authlib's JOSE successor, BSD-3-Clause)
against the tenant's JWKS (cached, refetched once for an unknown key id).

Guard rules (each closes an escalation path):

* **Pinned tenant.** The authority is ``https://login.microsoftonline.com/{tenant}/v2.0``; ``iss`` and ``tid`` must
  equal it exactly. ``common`` / ``organizations`` / ``consumers`` and the consumer tenant are refused at
  configuration time. Guests of the tenant (``idp`` claim of another issuer, ``acct`` = 1) are refused.
* **Identity is ``(tid, oid)``**, never the e-mail (``user_identities``). An e-mail change keeps the user.
* **Two doors only.** (a) self sign-up of the pinned tenant (``auto_provision``, on by default) always as the lowest
  role (``default_role_id``, Teacher; privileged roles are refused); (b) an administrator creates the account
  (``sso_invites`` kind ``invite``) or marks an existing one ``bind`` -- the first login whose *verified* UPN
  (``preferred_username`` / ``upn`` of a member, or ``email`` with ``xms_edov``) equals the invite binds
  ``(tid, oid)`` once, audited; invites expire (``invite_days``, 30).
* **No silent takeover.** Without an invite, a login whose verified UPN equals an existing account's e-mail is
  refused (``account_exists``); a signed-in local user links from the profile after re-entering the password.
* **Roles are SmartSched's.** The optional mapping (``role_mapping_enabled``, off) of app roles / group object ids
  is applied at every login; privileged roles only while ``allow_admin_mapping`` is on; a change bumps
  ``users.token_version`` (sessions revoked). Group overage (``_claim_names``) never demotes.
* **Break-glass.** An active administrator with a local password always keeps password sign-in;
  ``oidc_only_non_admins`` cannot be switched on without one, and a mapping never demotes an administrator when no
  other break-glass administrator would remain.
* **Nothing of the IdP is kept** but ``oid``, ``tid``, the e-mail at login and the display name. The access,
  refresh and ID tokens are dropped when the callback returns; the browser gets a one-time ``ticket`` (2 minutes,
  stored hashed) that ``POST /auth/sso/exchange`` turns into SmartSched's normal JWT.

Credentials come from the settings screen (``PUT /auth/sso/admin/entra``; the secret Fernet-encrypted with
APP_SECRET) or, for SSM-driven installs, from ``SSO_ENTRA_TENANT_ID`` / ``SSO_ENTRA_CLIENT_ID`` /
``SSO_ENTRA_CLIENT_SECRET`` in the backend environment (used for fields the screen leaves empty).
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
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import clean_email
from app.core.security import decrypt_secret, encrypt_secret, revoke_tokens, verify_password
from app.importers.normalize import clean_text
from app.models import Program, Role, User
from app.models.base import utcnow
from app.models.sso import SsoAuthState, SsoInvite, SsoProvider, SsoRoleMapping, UserIdentity
from app.services import audit
from app.services import bookings_events as events
from app.services.bookings_perms import (
    GRANT_GUARD,
    is_privileged_role,
    load_access,
    may_grant_role,
    may_manage_user,
    set_user_role,
    user_role,
)
from app.services.calendar_connectors import STATE_TTL, pkce_pair
from app.services.calendar_feeds import public_base

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
#: outbound transport for the token endpoint and the JWKS (tests put an ``http.MockTransport`` here)
transport: Any = None

_GUID_RX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_INVISIBLE = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF), None)  # zero-width characters
_APP_ROLE_RX = re.compile(r"^[^\s]{1,120}$")

#: ``sso_error`` codes of the panel redirects, in Turkish and English (GET /auth/sso/providers)
MESSAGES: dict[str, dict[str, str]] = {
    "state": {
        "tr": "Oturum açma isteğinin süresi doldu ya da istek zaten kullanıldı. Lütfen yeniden deneyin.",
        "en": "The sign-in request expired or was already used. Please try again.",
    },
    "denied": {
        "tr": "Microsoft oturum açma işlemi iptal edildi ya da izin verilmedi.",
        "en": "The Microsoft sign-in was cancelled or consent was not given.",
    },
    "not_configured": {
        "tr": "Microsoft 365 ile giriş bu kurulumda etkin değil. Kullanıcı adı ve parolanızla giriş yapın.",
        "en": "Sign-in with Microsoft 365 is not enabled on this installation. Sign in with your username and password.",
    },
    "exchange": {
        "tr": "Microsoft oturum açma işlemi tamamlanamadı. Lütfen yeniden deneyin.",
        "en": "The Microsoft sign-in could not be completed. Please try again.",
    },
    "unavailable": {
        "tr": "Microsoft oturum açma hizmetine şu anda ulaşılamıyor. Biraz sonra yeniden deneyin.",
        "en": "The Microsoft sign-in service cannot be reached right now. Try again shortly.",
    },
    "invalid_token": {
        "tr": "Microsoft'tan gelen kimlik bilgisi doğrulanamadı (kurum dışı hesap ya da geçersiz yanıt).",
        "en": "The identity from Microsoft could not be verified (an account outside the institution, or an invalid "
        "answer).",
    },
    "guest": {
        "tr": "Konuk (misafir) hesaplarla giriş yapılamaz. Kurumunuzun kendi hesabını kullanın.",
        "en": "Guest accounts cannot sign in. Use your own institution account.",
    },
    "provisioning_off": {
        "tr": "Bu Microsoft hesabı için SmartSched'de bir hesap yok ve kendiliğinden hesap açma kapalı. "
        "Hesap açılması için yöneticinize başvurun.",
        "en": "There is no SmartSched account for this Microsoft account and automatic sign-up is off. "
        "Ask your administrator to create your account.",
    },
    "account_exists": {
        "tr": "Bu e-posta adresiyle bir SmartSched hesabı zaten var. Her zamanki gibi giriş yapıp Profil sayfasından "
        "Microsoft hesabınızı bağlayın ya da yöneticinizden bağlantı daveti isteyin.",
        "en": "A SmartSched account with this e-mail already exists. Sign in the usual way and link your Microsoft "
        "account from your profile, or ask your administrator for a link invite.",
    },
    "invite_expired": {
        "tr": "Davetinizin süresi dolmuş. Yöneticinizden yeni bir davet isteyin.",
        "en": "Your invite has expired. Ask your administrator for a new one.",
    },
    "disabled": {
        "tr": "Hesabınız devre dışı. Yöneticinize başvurun.",
        "en": "Your account is disabled. Contact your administrator.",
    },
    "already_linked": {
        "tr": "Bu Microsoft hesabı başka bir SmartSched hesabına bağlı ya da bu hesap zaten başka bir Microsoft "
        "hesabına bağlı.",
        "en": "This Microsoft account is linked to another SmartSched account, or this account is already linked to "
        "another Microsoft account.",
    },
    "sso_required": {
        "tr": "Bu hesap için parola ile giriş kapalı. 'Microsoft 365 ile giriş yap' düğmesini kullanın.",
        "en": "Password sign-in is turned off for this account. Use 'Sign in with Microsoft 365'.",
    },
}


class SsoError(Exception):
    """A refused callback: ``code`` is a key of :data:`MESSAGES`; ``detail`` goes to the audit log only."""

    def __init__(self, code: str, detail: str = "", *, user_id: int | None = None):
        super().__init__(code)
        self.code, self.detail, self.user_id = code, detail[:200], user_id


class SsoAdminError(Exception):
    """A refused administration / link request (the API answers ``status`` with ``{code, tr, en}``)."""

    def __init__(self, status: int, code: str, en: str, tr: str):
        super().__init__(en)
        self.status, self.code, self.en, self.tr = status, code, en, tr

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "en": self.en, "tr": self.tr}


# --------------------------------------------------------------------------------------------------
# Text normalisation (pasted values: NBSP, zero-width, capitals; Turkish names kept as written)
# --------------------------------------------------------------------------------------------------


def _plain(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_INVISIBLE).replace("\xa0", " ").strip()


def clean_guid(value: str, what: str = "id") -> str:
    text = _plain(value).lower().strip("{}")
    if not _GUID_RX.match(text):
        raise ValueError(f"{what} must be a GUID like 3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a")
    return text


def clean_tenant(value: str) -> str:
    """The directory (tenant) id: a GUID. Multi-tenant authorities and the consumer tenant are refused, so ``iss``
    can be compared exactly (Microsoft: tenant-specific authority for single-tenant apps)."""
    text = _plain(value).lower()
    if text in RESERVED_TENANTS:
        raise ValueError(f"tenant id {text!r} is not allowed: pin the university's own directory (tenant) id")
    guid = clean_guid(text, "tenant id (directory id)")
    if guid == CONSUMER_TENANT:
        raise ValueError("the Microsoft consumer tenant is not allowed: pin the university's directory (tenant) id")
    return guid


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


@dataclass(frozen=True)
class EntraClient:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def authority(self) -> str:
        return f"{LOGIN_HOST}/{self.tenant_id}/v2.0"

    @property
    def issuer(self) -> str:
        return self.authority

    @property
    def authorize_endpoint(self) -> str:
        return f"{LOGIN_HOST}/{self.tenant_id}/oauth2/v2.0/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{LOGIN_HOST}/{self.tenant_id}/oauth2/v2.0/token"

    @property
    def jwks_uri(self) -> str:
        return f"{LOGIN_HOST}/{self.tenant_id}/discovery/v2.0/keys"


def redirect_uri(base: str) -> str:
    return f"{base}/api/v1/auth/sso/{PROVIDER}/callback"


async def get_provider(db: AsyncSession, *, create: bool = False) -> SsoProvider | None:
    row = (await db.execute(select(SsoProvider).where(SsoProvider.name == PROVIDER))).scalar_one_or_none()
    if row is None and create:
        row = SsoProvider(
            name=PROVIDER,
            enabled=False,
            auto_provision=True,
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
    if not tenant and _env("tenant_id"):
        try:
            tenant = clean_tenant(_env("tenant_id"))
            from_env.append("tenant_id")
        except ValueError:
            log.warning("ignoring %s: not a tenant GUID", ENV_KEYS["tenant_id"])
    client = row.client_id if row is not None else None
    if not client and _env("client_id"):
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
    if not secret and _env("client_secret"):
        secret = _env("client_secret")
        from_env.append("client_secret")
    return tenant, client, secret, from_env


async def client_config(db: AsyncSession, row: SsoProvider | None = None) -> EntraClient | None:
    """The OIDC client when tenant, client id, secret and the public URL are all known (enabled or not)."""
    row = row or await get_provider(db)
    tenant, client, secret, _ = _credentials(row)
    base, _src = await public_base(db)
    if not (tenant and client and secret and base):
        return None
    return EntraClient(tenant, client, secret, redirect_uri(base))


async def active_client(db: AsyncSession) -> tuple[SsoProvider, EntraClient] | None:
    row = await get_provider(db)
    if row is None or not row.enabled:
        return None
    cfg = await client_config(db, row)
    return (row, cfg) if cfg is not None else None


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


async def break_glass_admins(db: AsyncSession, *, exclude_user_id: int | None = None) -> int:
    """Active administrators who can sign in with a local password (``auth_source = local``)."""
    q = select(func.count(User.id)).where(
        User.role == "ADMIN",
        User.is_active.is_(True),
        User.auth_source == "local",
        User.password_hash.is_not(None),
        User.password_hash != "",
    )
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
        "auto_provision": row.auto_provision if row is not None else True,
        "default_role": _role_ref(await _default_role(db, row)),
        "oidc_only_non_admins": bool(row and row.oidc_only_non_admins),
        "role_mapping_enabled": bool(row and row.role_mapping_enabled),
        "allow_admin_mapping": bool(row and row.allow_admin_mapping),
        "invite_days": row.invite_days if row is not None else 30,
        "break_glass_admins": await break_glass_admins(db),
        "updated_at": row.updated_at if row is not None else None,
    }


def _snapshot(row: SsoProvider) -> dict[str, Any]:
    return {
        "enabled": row.enabled,
        "tenant_id": row.tenant_id,
        "client_id": row.client_id,
        "client_secret_set": bool(row.client_secret_enc),
        "auto_provision": row.auto_provision,
        "default_role_id": row.default_role_id,
        "oidc_only_non_admins": row.oidc_only_non_admins,
        "role_mapping_enabled": row.role_mapping_enabled,
        "allow_admin_mapping": row.allow_admin_mapping,
        "invite_days": row.invite_days,
    }


async def update_config(db: AsyncSession, actor: User, values: dict[str, Any]) -> None:
    """Apply a partial update (already validated by the schema); raises :class:`SsoAdminError`. The caller
    commits."""
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
            raise SsoAdminError(403, "no_escalation", "you cannot grant this role", "Bu rolü veremezsiniz")
    if values.get("allow_admin_mapping") and not row.allow_admin_mapping and actor.role != "ADMIN":
        raise SsoAdminError(
            403,
            "admin_only",
            "only an Administrator may allow mappings to administrative roles",
            "Yönetici rollerine eşlemeye yalnızca bir Yönetici izin verebilir",
        )
    for key in (
        "enabled",
        "tenant_id",
        "client_id",
        "auto_provision",
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
                "Etkinleştirmek için panelin genel adresi (PUBLIC_URL) gereklidir: yönlendirme adresi ondan oluşturulur",
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
    """False when ``oidc_only_non_admins`` is on (and Entra sign-in enabled) and ``user`` is no administrator."""
    row = await get_provider(db)
    if row is None or not row.enabled or not row.oidc_only_non_admins:
        return True
    return await is_admin_user(db, user)


async def record_password_refusal(db: AsyncSession, user: User, method: str) -> dict[str, str]:
    """Audit a password sign-in refused by ``oidc_only_non_admins``; returns the 403 detail. The caller commits."""
    await audit.record(
        db, "auth.login_refused", "user", user.id, after={"reason": "sso_required", "auth_method": method}
    )
    return {"code": "sso_required", **MESSAGES["sso_required"]}


# --------------------------------------------------------------------------------------------------
# Role mapping
# --------------------------------------------------------------------------------------------------


def clean_mapping_value(claim: str, value: str) -> str:
    if claim == "group":
        return clean_guid(value, "group object id")
    text = _plain(value)
    if not _APP_ROLE_RX.match(text):
        raise ValueError("an app role value has 1..120 characters and no spaces (e.g. SmartSched.Planner)")
    return text


async def list_mappings(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(select(SsoRoleMapping).where(SsoRoleMapping.provider == PROVIDER).order_by(SsoRoleMapping.id))
    ).scalars()
    out = []
    for m in rows:
        role = await db.get(Role, m.role_id)
        if role is not None:
            out.append({"id": m.id, "claim": m.claim, "value": m.value, "role": _role_ref(role), "created_at": m.created_at})
    return out


def _grants_admin(role: Role) -> bool:
    return role.code == "ADMIN" or is_privileged_role(role)


async def add_mapping(db: AsyncSession, actor: User, claim: str, value: str, role_id: int) -> SsoRoleMapping:
    try:
        clean = clean_mapping_value(claim, value)
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
    row = await get_provider(db, create=True)
    assert row is not None
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
                SsoRoleMapping.provider == PROVIDER, SsoRoleMapping.claim == claim, SsoRoleMapping.value == clean
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise SsoAdminError(409, "duplicate", "this value is already mapped", "Bu değer zaten eşlenmiş")
    m = SsoRoleMapping(provider=PROVIDER, claim=claim, value=clean, role_id=role.id, created_by=actor.id)
    db.add(m)
    await db.flush()
    await audit.record(
        db,
        "sso.mapping_create",
        "sso_role_mapping",
        m.id,
        after={"claim": claim, "value": clean, "role_id": role.id, "role": role.code or role.name},
        actor=actor,
    )
    return m


async def delete_mapping(db: AsyncSession, actor: User, mapping_id: int) -> None:
    m = await db.get(SsoRoleMapping, mapping_id)
    if m is None or m.provider != PROVIDER:
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
    mappings = list(
        (await db.execute(select(SsoRoleMapping).where(SsoRoleMapping.provider == PROVIDER))).scalars()
    )
    if not row.role_mapping_enabled or not mappings:
        return None, "mapping off"
    names = claims.get("_claim_names")
    if isinstance(names, dict) and "groups" in names:
        return None, "group overage"  # >200 groups: Entra left them out; never demote on missing data
    app_roles = {str(r) for r in claims.get("roles") or [] if isinstance(r, str)}
    groups = {str(g).lower() for g in claims.get("groups") or [] if isinstance(g, str)}
    best: Role | None = None
    for m in mappings:
        if (m.claim == "role" and m.value in app_roles) or (m.claim == "group" and m.value in groups):
            role = await db.get(Role, m.role_id)
            if role is None or (_grants_admin(role) and not row.allow_admin_mapping):
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


def _registry(cfg: EntraClient) -> jwt.JWTClaimsRegistry:
    return jwt.JWTClaimsRegistry(
        leeway=LEEWAY_S,
        iss={"essential": True, "value": cfg.issuer},
        aud={"essential": True, "value": cfg.client_id},
        exp={"essential": True},
        tid={"essential": True, "value": cfg.tenant_id},
        oid={"essential": True},
        nonce={"essential": True},
    )


async def validate_id_token(cfg: EntraClient, id_token: Any, nonce_hash: str | None) -> dict[str, Any]:
    """Signature (RS256 via the tenant's JWKS), exact ``iss`` and ``tid``, ``aud``, ``exp`` / ``nbf``, ``nonce``,
    a GUID ``oid``. Raises :class:`SsoError` ``invalid_token`` / ``unavailable``."""
    if not isinstance(id_token, str) or not id_token or not nonce_hash:
        raise SsoError("invalid_token", "no id_token")
    keyset = await jwks(cfg.jwks_uri)
    try:
        try:
            token = jwt.decode(id_token, keyset, algorithms=["RS256"])
        except InvalidKeyIdError:
            kid = ""
            try:
                kid = str(jws.extract_compact(id_token.encode("ascii")).headers().get("kid") or "")[:64]
            except Exception:  # noqa: BLE001 - malformed header: decode below fails the same way
                kid = ""
            keyset = await jwks(cfg.jwks_uri, unknown_kid=kid)
            token = jwt.decode(id_token, keyset, algorithms=["RS256"])
    except JoseError as exc:
        raise SsoError("invalid_token", f"signature: {exc.error}") from exc
    except ValueError as exc:
        raise SsoError("invalid_token", "malformed id_token") from exc
    claims = dict(token.claims)
    try:
        _registry(cfg).validate(claims)
    except JoseError as exc:
        raise SsoError("invalid_token", f"claims: {exc.error} {exc.description or ''}".strip()) from exc
    aud = claims.get("aud")
    if isinstance(aud, list) and (len(aud) != 1 or claims.get("azp") not in (None, cfg.client_id)):
        raise SsoError("invalid_token", "claims: several audiences")
    if not hmac.compare_digest(_hash(str(claims.get("nonce"))), nonce_hash):
        raise SsoError("invalid_token", "claims: nonce mismatch")
    oid = str(claims.get("oid") or "").lower()
    if not _GUID_RX.match(oid):
        raise SsoError("invalid_token", "claims: oid is not a GUID")
    claims["oid"] = oid
    idp = claims.get("idp")
    if (isinstance(idp, str) and idp and idp != cfg.issuer) or str(claims.get("acct", "0")) == "1":
        raise SsoError("guest", f"guest account (idp={str(idp)[:80]})")
    return claims


def verified_identifiers(claims: dict[str, Any]) -> list[str]:
    """Folded UPN / e-mail values the tenant vouches for: the member's UPN (``preferred_username`` / ``upn``) and
    the ``email`` claim only with ``xms_edov`` (e-mail domain owner verified). In order of preference for the
    account e-mail."""
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


def _oauth(cfg: EntraClient) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        token_endpoint_auth_method="client_secret_post",
        scope=SCOPES,
        redirect_uri=cfg.redirect_uri,
        code_challenge_method="S256",
        timeout=HTTP_TIMEOUT_S,
        follow_redirects=False,
        transport=transport,
    )


async def _purge_expired(db: AsyncSession) -> None:
    await db.execute(delete(SsoAuthState).where(SsoAuthState.expires_at < utcnow()))


async def _authorize(
    db: AsyncSession, cfg: EntraClient, purpose: str, *, user_id: int | None, return_path: str | None
) -> str:
    await _purge_expired(db)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, _challenge = pkce_pair()  # the same PKCE helper as the calendar connectors
    db.add(
        SsoAuthState(
            state_hash=_hash(state),
            provider=PROVIDER,
            purpose=purpose,
            nonce_hash=_hash(nonce),
            code_verifier_enc=encrypt_secret(verifier),
            user_id=user_id,
            return_path=return_path,
            expires_at=utcnow() + STATE_TTL,
        )
    )
    await db.flush()
    async with _oauth(cfg) as client:
        url, _ = client.create_authorization_url(
            cfg.authorize_endpoint,
            state=state,
            code_verifier=verifier,
            nonce=nonce,
            response_mode="query",
            prompt="select_account",
        )
    return str(url)


async def login_error_url(db: AsyncSession, code: str, *, link: bool = False) -> str:
    base, _ = await public_base(db)
    return f"{base}{'/profile' if link else '/login'}?{urlencode({'sso_error': code})}"


async def start_login(db: AsyncSession, return_path: str | None) -> str:
    """Authorize URL (Entra) for a sign-in; raises :class:`SsoError` ``not_configured``. The caller commits."""
    active = await active_client(db)
    if active is None:
        raise SsoError("not_configured")
    return await _authorize(db, active[1], "login", user_id=None, return_path=safe_return_path(return_path))


async def _identity_of(db: AsyncSession, user_id: int) -> UserIdentity | None:
    q = select(UserIdentity).where(UserIdentity.user_id == user_id, UserIdentity.provider == PROVIDER)
    return (await db.execute(q)).scalar_one_or_none()


async def start_link(db: AsyncSession, user: User, password: str) -> str:
    """A signed-in user links their Microsoft account; the password proves the local sign-in now."""
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise SsoAdminError(403, "password", "the password is not correct", "Parola doğru değil")
    if await _identity_of(db, user.id) is not None:
        raise SsoAdminError(409, "already_linked", MESSAGES["already_linked"]["en"], MESSAGES["already_linked"]["tr"])
    active = await active_client(db)
    if active is None:
        raise SsoAdminError(
            409, "not_configured", MESSAGES["not_configured"]["en"], MESSAGES["not_configured"]["tr"]
        )
    return await _authorize(db, active[1], "link", user_id=user.id, return_path=None)


async def _fail(db: AsyncSession, err: SsoError, purpose: str, claims: dict[str, Any] | None = None) -> str:
    after: dict[str, Any] = {"reason": err.code, "auth_method": "oidc", "provider": PROVIDER, "purpose": purpose}
    if err.detail:
        after["detail"] = err.detail
    if claims:
        after["tid"], after["oid"] = claims.get("tid"), claims.get("oid")
    log.info("Entra sign-in refused: %s (%s)", err.code, err.detail)
    await audit.record(db, "auth.sso_failed", "user", err.user_id, after=after)
    await db.commit()
    return await login_error_url(db, err.code, link=purpose == "link")


async def finish(db: AsyncSession, *, code: str | None, state: str | None, error: str | None) -> str:
    """The browser's return from Entra. Always answers a panel URL: ``/login/sso?ticket=…`` (sign-in),
    ``/profile?sso=linked`` (link) or ``…?sso_error=<code>``."""
    row = None
    if state:
        q = select(SsoAuthState).where(SsoAuthState.state_hash == _hash(state[:512]))
        row = (await db.execute(q)).scalar_one_or_none()
    if row is None or row.purpose not in ("login", "link") or row.provider != PROVIDER or row.expires_at < utcnow():
        if row is not None:
            await db.delete(row)
        return await _fail(db, SsoError("state", "unknown, used or expired state"), "login")
    purpose, link_user_id, return_path, nonce_hash = row.purpose, row.user_id, row.return_path, row.nonce_hash
    try:
        verifier = decrypt_secret(row.code_verifier_enc) if row.code_verifier_enc else ""
    except ValueError:
        verifier = ""
    await db.delete(row)  # single use, whatever happens next
    await db.commit()
    if error or not code:
        return await _fail(db, SsoError("denied" if error or not code else "exchange", str(error or "")), purpose)
    active = await active_client(db)
    if active is None:
        return await _fail(db, SsoError("not_configured"), purpose)
    prov, cfg = active
    if not verifier:
        return await _fail(db, SsoError("state", "verifier unreadable"), purpose)
    claims: dict[str, Any] | None = None
    try:
        claims = await _exchange_and_validate(cfg, code[:4096], verifier, nonce_hash)
        if purpose == "link":
            return await _finish_link(db, link_user_id, cfg, claims)
        user = await _resolve_login(db, prov, cfg, claims)
    except SsoError as err:
        await db.rollback()
        return await _fail(db, err, purpose, claims)
    return await _issue_ticket(db, user, return_path)


async def _exchange_and_validate(
    cfg: EntraClient, code: str, verifier: str, nonce_hash: str | None
) -> dict[str, Any]:
    try:
        async with _oauth(cfg) as client:
            token = await client.fetch_token(
                cfg.token_endpoint, grant_type="authorization_code", code=code, code_verifier=verifier
            )
    except http.HTTPError as exc:
        raise SsoError("unavailable", f"token endpoint {type(exc).__name__}") from exc
    except Exception as exc:  # noqa: BLE001 - OAuthError (invalid_grant ...), bad JSON
        raise SsoError("exchange", f"token: {getattr(exc, 'error', type(exc).__name__)}") from exc
    id_token = token.get("id_token") if isinstance(token, dict) else None
    # the access and refresh tokens are not needed: nothing of them is stored or logged
    del token
    return await validate_id_token(cfg, id_token, nonce_hash)


async def _find_identity(db: AsyncSession, claims: dict[str, Any]) -> UserIdentity | None:
    q = select(UserIdentity).where(
        UserIdentity.provider == PROVIDER,
        UserIdentity.tenant_id == str(claims["tid"]).lower(),
        UserIdentity.subject == claims["oid"],
    )
    return (await db.execute(q)).scalar_one_or_none()


def _new_identity(user_id: int, cfg: EntraClient, claims: dict[str, Any], origin: str) -> UserIdentity:
    return UserIdentity(
        user_id=user_id,
        provider=PROVIDER,
        issuer=cfg.issuer,
        tenant_id=str(claims["tid"]).lower(),
        subject=claims["oid"],
        origin=origin,
    )


def _touch(ident: UserIdentity, claims: dict[str, Any]) -> None:
    ids = verified_identifiers(claims)
    ident.email_at_login = ids[0] if ids else _fold_email(claims.get("email"))
    ident.display_name = clean_display_name(claims.get("name"))
    ident.last_login_at = utcnow()


async def _resolve_login(db: AsyncSession, prov: SsoProvider, cfg: EntraClient, claims: dict[str, Any]) -> User:
    ident = await _find_identity(db, claims)
    user = await db.get(User, ident.user_id) if ident is not None else None
    if user is None:
        user, ident = await _first_login(db, prov, cfg, claims)
    assert ident is not None
    if not user.is_active:
        raise SsoError("disabled", "account disabled", user_id=user.id)
    _touch(ident, claims)
    await _apply_mapping(db, prov, user, claims)
    user.last_login_at = utcnow()
    await events.emit(db, "user.logged_in", {"user_id": user.id, "auth_method": "oidc"})
    await audit.record(
        db,
        "auth.sso_login",
        "user",
        user.id,
        after={"auth_method": "oidc", "provider": PROVIDER, "tid": ident.tenant_id, "oid": ident.subject},
        actor=user,
    )
    return user


async def _first_login(
    db: AsyncSession, prov: SsoProvider, cfg: EntraClient, claims: dict[str, Any]
) -> tuple[User, UserIdentity]:
    verified = verified_identifiers(claims)
    invite = None
    if verified:
        q = select(SsoInvite).where(SsoInvite.provider == PROVIDER, SsoInvite.email.in_(verified))
        invite = (await db.execute(q.order_by(SsoInvite.id))).scalars().first()
    if invite is not None:
        if invite.expires_at < utcnow():
            raise SsoError("invite_expired", f"invite {invite.id} expired", user_id=invite.user_id)
        target = await db.get(User, invite.user_id)
        if target is None or await _identity_of(db, target.id) is not None:
            raise SsoError("already_linked", f"invite {invite.id}", user_id=invite.user_id)
        ident = _new_identity(target.id, cfg, claims, invite.kind)
        db.add(ident)
        kind, email, invite_id = invite.kind, invite.email, invite.id
        await db.delete(invite)  # one time
        await db.flush()
        await audit.record(
            db,
            "auth.sso_bind",
            "user",
            target.id,
            after={"kind": kind, "email": email, "invite_id": invite_id, "tid": ident.tenant_id, "oid": ident.subject},
            actor=target,
        )
        return target, ident
    if verified:
        clash = (await db.execute(select(User.id).where(User.email.in_(verified)))).scalars().first()
        if clash is not None:  # never linked by e-mail: an admin's invite or a confirmed link only
            raise SsoError("account_exists", "verified UPN equals an existing account without an invite", user_id=clash)
    if not prov.auto_provision:
        raise SsoError("provisioning_off", "no account and auto-provisioning off")
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
        "auth.sso_provision",
        "user",
        user.id,
        after={"role": user.role, "email": user.email, "tid": ident.tenant_id, "oid": ident.subject},
        actor=user,
    )
    return user, ident


async def _finish_link(db: AsyncSession, user_id: int | None, cfg: EntraClient, claims: dict[str, Any]) -> str:
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise SsoError("state", "link user gone or disabled", user_id=user_id)
    ident = await _find_identity(db, claims)
    if ident is not None and ident.user_id != user.id:
        raise SsoError("already_linked", "identity belongs to another account", user_id=user.id)
    own = await _identity_of(db, user.id)
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
        "auth.sso_link",
        "user",
        user.id,
        after={"tid": ident.tenant_id, "oid": ident.subject, "email_at_login": ident.email_at_login},
        actor=user,
    )
    await db.commit()
    base, _ = await public_base(db)
    return f"{base}/profile?sso=linked"


async def _issue_ticket(db: AsyncSession, user: User, return_path: str | None) -> str:
    ticket = secrets.token_urlsafe(32)
    db.add(
        SsoAuthState(
            state_hash=_hash(ticket),
            provider=PROVIDER,
            purpose="ticket",
            user_id=user.id,
            return_path=return_path,
            expires_at=utcnow() + TICKET_TTL,
        )
    )
    await db.commit()
    base, _ = await public_base(db)
    params = {"ticket": ticket, **({"next": return_path} if return_path else {})}
    return f"{base}/login/sso?{urlencode(params)}"


async def exchange_ticket(db: AsyncSession, ticket: str) -> User | None:
    """The one-time ticket -> its user (``None``: unknown, used, expired or the account was disabled since)."""
    q = select(SsoAuthState).where(SsoAuthState.state_hash == _hash(ticket))
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None or row.purpose != "ticket":
        return None
    user_id, expired = row.user_id, row.expires_at < utcnow()
    await db.delete(row)
    await db.commit()
    user = await db.get(User, user_id) if user_id and not expired else None
    return user if user is not None and user.is_active else None


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
    await audit.record(db, "sso.unlink", "user", user.id, before=before, actor=user)


# --------------------------------------------------------------------------------------------------
# Invites and "bind on next SSO login" (setup.users, no escalation)
# --------------------------------------------------------------------------------------------------


def _invite_out(inv: SsoInvite) -> dict[str, Any]:
    return {
        "id": inv.id,
        "user_id": inv.user_id,
        "email": inv.email,
        "kind": inv.kind,
        "status": "invite_expired" if inv.expires_at < utcnow() else "invited",
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "created_by": inv.created_by,
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


async def _place_invite(
    db: AsyncSession, actor: User, user: User, email: str, kind: str, days: int | None, prov: SsoProvider
) -> SsoInvite:
    other = (
        await db.execute(select(SsoInvite).where(SsoInvite.provider == PROVIDER, SsoInvite.email == email))
    ).scalar_one_or_none()
    if other is not None and other.user_id != user.id:
        if other.expires_at >= utcnow():
            raise SsoAdminError(
                409, "invite_taken", "another account is waiting for this UPN", "Bu UPN başka bir hesaba davetli"
            )
        await db.delete(other)
    await db.execute(delete(SsoInvite).where(SsoInvite.user_id == user.id))
    await db.flush()
    inv = SsoInvite(
        provider=PROVIDER,
        user_id=user.id,
        email=email,
        kind=kind,
        created_by=actor.id,
        expires_at=utcnow() + timedelta(days=days or prov.invite_days or 30),
    )
    db.add(inv)
    await db.flush()
    await audit.record(
        db,
        "sso.invite_create" if kind == "invite" else "sso.bind_mark",
        "user",
        user.id,
        after={"kind": kind, "email": email, "expires_at": inv.expires_at},
        actor=actor,
    )
    return inv


async def create_invite(db: AsyncSession, actor: User, body: dict[str, Any]) -> dict[str, Any]:
    prov = await get_provider(db, create=True)
    assert prov is not None
    email = _clean_invite_email(body.get("email"))
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none() is not None:
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
    user = User(
        email=email,
        full_name=clean_display_name(body.get("full_name")),
        is_active=True,
        auth_source="oidc",
        password_hash=None,
        force_password_reset=False,
        department_id=dept,
    )
    set_user_role(user, role)
    db.add(user)
    await db.flush()
    return _invite_out(await _place_invite(db, actor, user, email, "invite", body.get("days"), prov))


async def mark_bind(db: AsyncSession, actor: User, user_id: int, email: str | None, days: int | None) -> dict[str, Any]:
    prov = await get_provider(db, create=True)
    assert prov is not None
    target = await db.get(User, user_id)
    if target is None:
        raise SsoAdminError(404, "not_found", "user not found", "Kullanıcı bulunamadı")
    if not await may_manage_user(db, actor, target):
        raise SsoAdminError(
            403,
            "no_escalation",
            "managing this account requires every permission its role holds",
            "Bu hesabı yönetmek için rolünün tüm izinleri gerekir",
        )
    if await _identity_of(db, target.id) is not None:
        raise SsoAdminError(409, "already_linked", MESSAGES["already_linked"]["en"], MESSAGES["already_linked"]["tr"])
    clean = _clean_invite_email(email or target.email)
    holder = (await db.execute(select(User.id).where(User.email == clean, User.id != target.id))).scalar_one_or_none()
    if holder is not None:
        raise SsoAdminError(409, "email_taken", "another account has this e-mail", "Bu e-posta başka bir hesapta")
    return _invite_out(await _place_invite(db, actor, target, clean, "bind", days, prov))


async def list_invites(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(select(SsoInvite).where(SsoInvite.provider == PROVIDER).order_by(SsoInvite.id))).scalars()
    return [_invite_out(i) for i in rows]


async def delete_invite(db: AsyncSession, actor: User, invite_id: int) -> None:
    inv = await db.get(SsoInvite, invite_id)
    if inv is None:
        raise SsoAdminError(404, "not_found", "invite not found", "Davet bulunamadı")
    target = await db.get(User, inv.user_id)
    if target is not None and not await may_manage_user(db, actor, target):
        raise SsoAdminError(403, "no_escalation", "you cannot manage this account", "Bu hesabı yönetemezsiniz")
    before = {"kind": inv.kind, "email": inv.email}
    await db.delete(inv)
    await db.flush()
    await audit.record(db, "sso.invite_delete", "user", inv.user_id, before=before, actor=actor)


async def admin_unlink(db: AsyncSession, actor: User, user_id: int) -> None:
    target = await db.get(User, user_id)
    if target is None:
        raise SsoAdminError(404, "not_found", "user not found", "Kullanıcı bulunamadı")
    if not await may_manage_user(db, actor, target):
        raise SsoAdminError(403, "no_escalation", "you cannot manage this account", "Bu hesabı yönetemezsiniz")
    ident = await _identity_of(db, target.id)
    if ident is None:
        raise SsoAdminError(404, "not_linked", "no Microsoft account is linked", "Bağlı bir Microsoft hesabı yok")
    before = {"tid": ident.tenant_id, "oid": ident.subject}
    await db.delete(ident)
    revoke_tokens(target)  # sessions opened through that identity end too
    await db.flush()
    await audit.record(db, "sso.unlink", "user", target.id, before=before, actor=actor)


async def user_status(db: AsyncSession) -> dict[str, str]:
    """``{user_id: linked | invited | invite_expired}`` for every account with an identity or an invite (the users
    list shows it; accounts without either are absent)."""
    out: dict[str, str] = {}
    now: datetime = utcnow()
    for inv in (await db.execute(select(SsoInvite).where(SsoInvite.provider == PROVIDER))).scalars():
        out[str(inv.user_id)] = "invite_expired" if inv.expires_at < now else "invited"
    for uid in (await db.execute(select(UserIdentity.user_id).where(UserIdentity.provider == PROVIDER))).scalars():
        out[str(uid)] = "linked"
    return out


def providers_out(enabled: bool) -> dict[str, Any]:
    return {
        "providers": [
            {"name": PROVIDER, "label": LABEL, "enabled": enabled, "start_url": f"/api/v1/auth/sso/{PROVIDER}/start"}
        ],
        "messages": MESSAGES,
    }

