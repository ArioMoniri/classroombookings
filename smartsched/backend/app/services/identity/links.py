"""Profile › Güvenlik: a signed-in user's own identities at the non-Entra providers (Google Workspace, generic OIDC,
SAML; W3-IDP open item, idp-2026-10-18). Microsoft keeps its own section and routes (``/auth/sso/entra/link``).

* **List** (:func:`my_identities`): every enabled, usable provider plus any provider this account is linked to
  (so a link can still be removed after the provider was switched off), in the administrators' /login order.
* **Link** (:func:`start_link`): re-authentication first (the password, or a session younger than
  ``mfa.REAUTH_WINDOW``, the rule of every security action), only for an account with a local password, one
  identity per provider; the answer is the provider URL (OIDC with PKCE/state/nonce, SAML an AuthnRequest), and the
  binding itself happens and is audited (``auth.identity_bound``) when the provider sends the person back.
* **Unlink** (:func:`unlink`): re-authentication, then the identity row goes; audited ``auth.identity_unbound``.

The administrator rules do not change: reset links and 2FA resets stay refused for IdP-only accounts
(``mfa.account_type`` = ``sso``); a local account that links an identity keeps its password and stays ``mixed``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.sso import SsoProvider, UserIdentity
from app.services import audit, mfa, sso
from app.services.identity import kinds
from app.services.identity import saml as idp_saml

Err = sso.SsoAdminError


async def _usable(db: AsyncSession, row: SsoProvider) -> bool:
    if not row.enabled:
        return False
    if row.kind == kinds.SAML:
        return idp_saml.AVAILABLE and await sso.saml_config(db, row) is not None
    return await sso.client_config(db, row) is not None


async def my_identities(db: AsyncSession, user: User) -> dict[str, Any]:
    q = select(SsoProvider).where(SsoProvider.kind != kinds.ENTRA).order_by(SsoProvider.sort_order, SsoProvider.id)
    idents = {
        i.provider: i for i in (await db.execute(select(UserIdentity).where(UserIdentity.user_id == user.id))).scalars()
    }
    out: list[dict[str, Any]] = []
    for row in (await db.execute(q)).scalars():
        usable = await _usable(db, row)
        ident = idents.get(row.name)
        if not usable and ident is None:
            continue
        out.append(
            {
                "slug": row.name,
                "kind": row.kind,
                "badge": kinds.BADGES.get(row.kind, "SSO"),
                "label": sso.provider_label(row),
                "label_en": sso.provider_label(row, "en"),
                "enabled": usable,
                "linked": ident is not None,
                "email_at_login": ident.email_at_login if ident else None,
                "display_name": ident.display_name if ident else None,
                "linked_at": ident.created_at if ident else None,
                "last_login_at": ident.last_login_at if ident else None,
            }
        )
    return {"has_password": bool(user.password_hash), "providers": out}


def _reauth_failed() -> Err:
    return Err(
        403,
        "reauth_failed",
        "confirm with your password (the password is wrong or missing)",
        "Parolanızla onaylayın (parola yanlış ya da girilmedi).",
    )


async def _reauth(db: AsyncSession, user: User, password: str | None, recent: bool) -> None:
    if not await mfa.reauth(db, user, password, recent=recent):
        raise _reauth_failed()


async def _provider(db: AsyncSession, slug: str) -> SsoProvider:
    row = await sso.get_provider(db, slug=slug)
    if row is None:
        raise Err(404, "not_found", "identity provider not found", "Kimlik sağlayıcısı bulunamadı")
    return row


async def start_link(db: AsyncSession, user: User, slug: str, password: str | None, *, recent: bool) -> str:
    """The provider URL the browser navigates to. Raises :class:`SsoAdminError`; the caller commits."""
    row = await _provider(db, slug)
    if not user.password_hash:
        raise Err(
            409,
            "no_password",
            "only an account with a SmartSched password links another sign-in; this account signs in at its provider",
            "Yalnızca SmartSched parolası olan bir hesap başka bir giriş yolu bağlayabilir; bu hesap kimlik "
            "sağlayıcısıyla giriş yapıyor.",
        )
    await _reauth(db, user, password, recent)
    label = sso.provider_label(row)
    if not await _usable(db, row):
        raise Err(
            409,
            "not_configured",
            f"sign-in with {sso.provider_label(row, 'en')} is not enabled on this installation",
            f"{label} ile giriş bu kurulumda etkin değil",
        )
    if await sso._identity_of(db, user.id, row.name) is not None:  # noqa: SLF001 - the shared lookup
        raise Err(
            409,
            "already_linked",
            f"this account is already linked to {sso.provider_label(row, 'en')}",
            f"Bu hesap {label} ile zaten bağlı",
        )
    try:
        if row.kind == kinds.SAML:
            return await sso.start_saml(db, row, None, purpose="link", user_id=user.id)
        cfg = await sso.client_config(db, row)
        assert cfg is not None  # _usable checked it
        return await sso._authorize(db, cfg, "link", user_id=user.id, return_path=None)  # noqa: SLF001
    except sso.SsoError as exc:
        raise Err(
            409, "not_configured", f"the provider cannot start a sign-in ({exc.code})", f"{label} şu an kullanılamıyor"
        ) from exc


async def unlink(db: AsyncSession, user: User, slug: str, password: str | None, *, recent: bool) -> None:
    """Remove this account's identity at the provider after re-authentication; audited. The caller commits."""
    await _reauth(db, user, password, recent)
    row = await sso.get_provider(db, slug=slug)
    ident = await sso._identity_of(db, user.id, slug)  # noqa: SLF001
    if ident is None:
        raise Err(404, "not_linked", "no identity of this provider is linked", "Bu sağlayıcıdan bağlı bir kimlik yok")
    if not user.password_hash and user.auth_source != "ldap":
        raise Err(
            409,
            "last_sign_in",
            "unlinking would leave this account without any way to sign in; ask an administrator to set a password "
            "first",
            "Bağlantıyı kaldırmak bu hesabı giriş yolu olmadan bırakır; önce yöneticinizden bir parola isteyin",
        )
    before = {
        "provider": slug,
        "kind": row.kind if row is not None else None,
        "issuer": ident.issuer,
        "subject": ident.subject,
        "email_at_login": ident.email_at_login,
    }
    await db.delete(ident)
    await db.flush()
    await audit.record(db, "auth.identity_unbound", "user", user.id, before=before, actor=user)
