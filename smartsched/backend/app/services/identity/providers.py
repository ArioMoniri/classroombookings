"""Administration of the identity providers (wave 3b W3-IDP; ``/api/v1/auth/sso/admin/providers*``).

Every provider is an organisation-wide ``sso_providers`` row: when one administrator saves it, every administrator
sees the same values. Secrets (``client_secret``) are Fernet-encrypted with APP_SECRET and write-only (the answer
says ``client_secret_set``, never a value or a fragment). Every change is audited (``sso.provider_create`` /
``sso.provider_update`` / ``sso.provider_order`` / ``sso.provider_delete``) with the actor, and the answer carries
"Son değişiklik" (``changed_by`` / ``changed_at``) and a ``version`` for conflict detection (design v3
integrations.md §5.6).

Guard rules (on top of app/services/sso.py):

* Microsoft (Entra) and Google Workspace exist once each; OIDC and SAML providers may be several (one slug each).
* New OIDC / SAML providers start invite-only; Entra / Google (tenant / domain pinned) allow self sign-up.
* The self sign-up role must be eligible (no administrative permission; T-R1-35) and grantable by the editor.
* Enabling needs a usable client: Entra tenant + client + secret; Google client + secret + a hosted domain; OIDC a
  successful discovery; SAML parsed metadata and the optional library; always the public URL.
* SAML (RF-12, idp-2026-10-18): with a federation signing certificate (``metadata_signing_cert``) only metadata
  whose root signature verifies with it is read; otherwise the stored metadata is dropped and the check row says
  why (TR/EN). The SP key pair (``sp_key_generate`` or a pasted ``sp_private_key`` + ``sp_certificate``) decrypts
  EncryptedAssertions and, with ``sign_requests`` (off by default), signs the AuthnRequests; the private key is
  Fernet-encrypted (``options.sp_private_key_enc``) and write-only like ``client_secret``.
* Disabling is refused when it would leave an administrator without any way in (no break-glass administrator and
  an administrator who signs in only through this provider).
* Deleting needs the provider off; its identities, mappings and invites go, the accounts stay.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_secret
from app.models import Role, User
from app.models.base import utcnow
from app.models.sso import SsoInvite, SsoProvider, SsoRoleMapping, UserIdentity
from app.services import audit, sso
from app.services.bookings_perms import may_grant_role
from app.services.bookings_settings import get_group
from app.services.calendar_feeds import public_base
from app.services.identity import errors, kinds, saml_crypto
from app.services.identity import saml as idp_saml
from app.services.identity.oidc import (
    GOOGLE_DISCOVERY,
    GOOGLE_ISSUERS,
    clean_claim_name,
    clean_issuer,
    discovery_url,
    fetch_discovery,
    plain,
    secure_url,
    validate_discovery,
)

Err = sso.SsoAdminError
SINGLETONS = (kinds.ENTRA, kinds.GOOGLE)
_SCOPE_RX = re.compile(r"^[A-Za-z0-9_.:/-]{1,64}$")


def _bad(code: str, en: str, tr: str, status: int = 422) -> Err:
    return Err(status, code, en, tr)


# --------------------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------------------


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt is not None else None


def version_of(row: SsoProvider) -> str:
    return row.updated_at.isoformat(timespec="microseconds") if row.updated_at else "0"


async def _configured(db: AsyncSession, row: SsoProvider) -> bool:
    if row.kind == kinds.SAML:
        return idp_saml.AVAILABLE and await sso.saml_config(db, row) is not None
    return await sso.client_config(db, row) is not None


def status_of(row: SsoProvider, configured: bool) -> str:
    """connected | not_configured | error | disabled (the W3-HUB card statuses)."""
    if not configured:
        return "error" if row.last_check_ok is False else "not_configured"
    if row.last_check_ok is False:
        return "error"
    return "connected" if row.enabled else "disabled"


async def provider_out(db: AsyncSession, row: SsoProvider) -> dict[str, Any]:
    opts = dict(row.options or {})
    configured = await _configured(db, row)
    base, _src = await public_base(db)
    editor = await db.get(User, row.updated_by) if row.updated_by else None
    identities = (
        await db.execute(select(func.count(UserIdentity.id)).where(UserIdentity.provider == row.name))
    ).scalar_one()
    _t, client, secret, from_env = sso._credentials(row)  # noqa: SLF001 - the env fallback of the Entra row
    meta = opts.get("metadata") or {}
    out: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "badge": kinds.BADGES.get(row.kind, "SSO"),
        "label": sso.provider_label(row),
        "label_en": sso.provider_label(row, "en"),
        "display_name": row.display_name,
        "preset": opts.get("preset"),
        "enabled": row.enabled,
        "configured": configured,
        "status": status_of(row, configured),
        "sort_order": row.sort_order,
        "allowed_domains": list(row.allowed_domains or []),
        "invite_only": row.invite_only,
        "self_signup": row.self_signup,
        "default_role": sso._role_ref(await sso._default_role(db, row)),  # noqa: SLF001
        "role_mapping_enabled": row.role_mapping_enabled,
        "allow_admin_mapping": row.allow_admin_mapping,
        "oidc_only_non_admins": row.oidc_only_non_admins,
        "invite_days": row.invite_days,
        "domain_hint": row.domain_hint,
        "client_id": client,
        "client_secret_set": bool(secret),
        "from_environment": from_env,
        "secret_expires": opts.get("secret_expires"),
        "tenant_id": row.tenant_id if row.kind == kinds.ENTRA else None,
        "issuer": opts.get("issuer") if row.kind == kinds.OIDC else None,
        "hosted_domains": list(opts.get("hosted_domains") or []),
        "groups_claim": opts.get("groups_claim") or "groups",
        "roles_claim": opts.get("roles_claim") or "roles",
        "trust_email": bool(opts.get("trust_email")),
        "scopes": list(opts.get("scopes") or []),
        "discovery": {
            "ok": opts.get("discovery_ok"),
            "checks": opts.get("discovery_checks") or [],
            "fetched_at": (opts.get("discovery") or {}).get("fetched_at") or meta.get("fetched_at"),
        },
        "saml": {
            "metadata_url": opts.get("metadata_url"),
            "idp_entity_id": meta.get("entity_id") or opts.get("idp_entity_id"),
            "sso_url": meta.get("sso_url"),
            "certificates": len(meta.get("certs") or []),
            "cert_not_after": meta.get("cert_not_after"),
            "email_attribute": opts.get("email_attribute") or kinds.ATTR_MAIL,
            "name_attribute": opts.get("name_attribute") or kinds.ATTR_DISPLAY_NAME,
            "groups_attribute": opts.get("groups_attribute") or kinds.ATTR_ENTITLEMENT,
            "subject_attribute": opts.get("subject_attribute"),
            "metadata_signing_cert": saml_crypto.cert_info(opts.get("metadata_signing_cert")),
            "metadata_signed": bool(meta.get("signed")),
            "sp_certificate": saml_crypto.cert_info(opts.get("sp_certificate")),
            "sp_private_key_set": bool(opts.get("sp_private_key_enc")),
            "sign_requests": bool(opts.get("sign_requests")),
        }
        if row.kind == kinds.SAML
        else None,
        "library_required": row.kind == kinds.SAML and not idp_saml.AVAILABLE,
        "redirect_uri": sso.redirect_uri(base, row.name) if base and row.kind != kinds.SAML else None,
        "start_url": f"/api/v1/auth/sso/{row.name}/start",
        "identities": int(identities),
        "test_ok": opts.get("test_ok"),
        "test_at": opts.get("test_at"),
        "last_check_at": _iso(row.last_check_at),
        "last_check_ok": row.last_check_ok,
        "last_check_detail": row.last_check_detail,
        "changed_by": audit.user_label(editor),
        "changed_at": _iso(row.updated_at),
        "version": version_of(row),
    }
    return out


async def ldap_card(db: AsyncSession) -> dict[str, Any]:
    group = await get_group(db, "ldap")
    return {
        "kind": kinds.LDAP,
        "badge": kinds.BADGES[kinds.LDAP],
        "label": kinds.DEFAULT_LABELS[kinds.LDAP]["tr"],
        "label_en": kinds.DEFAULT_LABELS[kinds.LDAP]["en"],
        "enabled": bool(group.get("enabled")),
        "configured": bool(group.get("host") or group.get("server") or group.get("uri")),
        "settings_href": "/settings?tab=ldap",
    }


async def list_out(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(select(SsoProvider).order_by(SsoProvider.sort_order, SsoProvider.id))).scalars()
    return {
        "providers": [await provider_out(db, r) for r in rows],
        "ldap": await ldap_card(db),
        "break_glass_admins": await sso.break_glass_admins(db),
        "saml_available": idp_saml.AVAILABLE,
    }


async def get_row(db: AsyncSession, provider_id: int) -> SsoProvider:
    row = await db.get(SsoProvider, provider_id)
    if row is None:
        raise _bad("not_found", "identity provider not found", "Kimlik sağlayıcısı bulunamadı", 404)
    return row


# --------------------------------------------------------------------------------------------------
# guided setup values (step 2: what to paste into the provider's console)
# --------------------------------------------------------------------------------------------------


def _value(key: str, tr: str, en: str, value: str | None) -> dict[str, Any]:
    return {"key": key, "label_tr": tr, "label_en": en, "value": value}


async def console_values(db: AsyncSession, row: SsoProvider) -> list[dict[str, Any]]:
    base, _src = await public_base(db)
    if not base:
        return []
    logout = f"{base}/login?reason=signed_out"
    opts = row.options or {}
    if row.kind == kinds.SAML:
        entity, acs = idp_saml.sp_entity_id(base, row.name), idp_saml.acs_url(base, row.name)
        return [
            _value("sp_metadata_url", "SP meta veri adresi", "SP metadata URL", entity),
            _value("entity_id", "Varlık kimliği (Entity ID)", "Entity ID", entity),
            _value("acs_url", "ACS adresi (HTTP-POST)", "Assertion Consumer Service URL (HTTP-POST)", acs),
            _value("slo_url", "Oturum kapatma sonrası adres", "Logout return URL", logout),
            _value("name_id_format", "NameID biçimi", "NameID format", idp_saml.PERSISTENT),
            _value(
                "attributes",
                "Öznitelikler",
                "Attributes",
                "mail, displayName, eduPersonPrincipalName, eduPersonEntitlement",
            ),
        ]
    redirect = sso.redirect_uri(base, row.name)
    if row.kind == kinds.ENTRA:
        return [
            _value("redirect_uri", "Yeniden yönlendirme URI'si (Web)", "Redirect URI (Web)", redirect),
            _value("front_channel_logout", "Ön kanal oturum kapatma URL'si", "Front-channel logout URL", logout),
            _value(
                "scopes",
                "API izinleri (Microsoft Graph, temsilci)",
                "API permissions (Graph, delegated)",
                "openid profile email User.Read",
            ),
        ]
    if row.kind == kinds.GOOGLE:
        return [
            _value("javascript_origin", "Yetkili JavaScript kaynağı", "Authorised JavaScript origin", base),
            _value("redirect_uri", "Yetkili yönlendirme URI'si", "Authorised redirect URI", redirect),
            _value("scopes", "Kapsamlar", "Scopes", "openid email profile"),
        ]
    extra = [s for s in opts.get("scopes") or [] if s not in ("openid", "profile", "email")]
    return [
        _value("redirect_uri", "Yönlendirme adresi", "Sign-in redirect URI", redirect),
        _value("post_logout_redirect_uri", "Oturum kapatma sonrası adres", "Post-logout redirect URI", logout),
        _value("scopes", "Kapsamlar", "Scopes", " ".join(["openid", "profile", "email", *extra])),
    ]


async def setup_out(db: AsyncSession, row: SsoProvider) -> dict[str, Any]:
    base, source = await public_base(db)
    opts = row.options or {}
    preset_key = opts.get("preset")
    preset = kinds.presets_for(row.kind).get(preset_key or "generic", {})
    return {
        "provider": await provider_out(db, row),
        "public_url": base,
        "public_url_source": source,
        "public_url_secure": bool(base and base.startswith("https://")),
        "console": await console_values(db, row),
        "steps": kinds.steps_for(row.kind, preset_key),
        "fields": kinds.FIELDS.get(row.kind, []),
        "issuer_hint": preset.get("issuer_hint") or preset.get("metadata_hint"),
        "groups_claim_hint": preset.get("groups_claim") or preset.get("groups_attribute"),
    }


async def sp_metadata_xml(db: AsyncSession, row: SsoProvider) -> str | None:
    base, _src = await public_base(db)
    if row.kind != kinds.SAML or not base:
        return None
    opts = row.options or {}
    cert = opts.get("sp_certificate") if opts.get("sp_private_key_enc") else None
    return idp_saml.sp_metadata(
        idp_saml.sp_entity_id(base, row.name),
        idp_saml.acs_url(base, row.name),
        sp_cert=cert,
        sign_requests=bool(opts.get("sign_requests")),
    )


# --------------------------------------------------------------------------------------------------
# create / update / order / delete
# --------------------------------------------------------------------------------------------------


def clean_slug(value: str) -> str:
    text = plain(value).replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    if not kinds.SLUG_RX.match(text) or text in kinds.RESERVED_SLUGS:
        raise _bad(
            "invalid_slug",
            "the slug has 2..40 characters a-z, 0-9 and '-', starts with a letter and is not reserved",
            "Kısa ad 2-40 karakter olmalı (a-z, 0-9, -), harfle başlamalı ve ayrılmış bir ad olmamalı",
        )
    return text


async def _free_slug(db: AsyncSession, wanted: str) -> str:
    taken = set((await db.execute(select(SsoProvider.name))).scalars())
    if wanted not in taken:
        return wanted
    n = 2
    while f"{wanted}-{n}" in taken:
        n += 1
    return f"{wanted}-{n}"


def _fingerprint(pem: Any) -> str | None:
    info = saml_crypto.cert_info(pem) if isinstance(pem, str) else None
    return info["sha256"] if info else None


def _snapshot(row: SsoProvider) -> dict[str, Any]:
    hidden = ("discovery_checks", "metadata_xml", "sp_private_key_enc")
    opts = {k: v for k, v in (row.options or {}).items() if k not in hidden}
    if (row.options or {}).get("metadata_xml"):
        opts["metadata_xml_set"] = True
    if (row.options or {}).get("sp_private_key_enc"):
        opts["sp_private_key_set"] = True  # never the key, not even encrypted
    for key in ("metadata_signing_cert", "sp_certificate"):
        if opts.get(key):
            opts[key] = _fingerprint(opts[key])
    if "metadata" in opts:
        opts["metadata"] = {k: v for k, v in opts["metadata"].items() if k != "certs"} | {
            "certs": len(opts["metadata"].get("certs") or [])
        }
    return {
        "name": row.name,
        "kind": row.kind,
        "display_name": row.display_name,
        "enabled": row.enabled,
        "sort_order": row.sort_order,
        "allowed_domains": row.allowed_domains,
        "invite_only": row.invite_only,
        "self_signup": row.self_signup,
        "default_role_id": row.default_role_id,
        "role_mapping_enabled": row.role_mapping_enabled,
        "allow_admin_mapping": row.allow_admin_mapping,
        "oidc_only_non_admins": row.oidc_only_non_admins,
        "invite_days": row.invite_days,
        "domain_hint": row.domain_hint,
        "tenant_id": row.tenant_id,
        "client_id": row.client_id,
        "client_secret_set": bool(row.client_secret_enc),
        "options": opts,
    }


async def create(db: AsyncSession, actor: User, body: dict[str, Any]) -> SsoProvider:
    kind = str(body.get("kind") or "")
    if kind not in kinds.KINDS:
        raise _bad("unknown_kind", f"unknown provider kind {kind!r}", "Bilinmeyen sağlayıcı türü")
    if kind in SINGLETONS:
        exists = (await db.execute(select(SsoProvider.id).where(SsoProvider.kind == kind))).first()
        if exists is not None:
            raise _bad(
                "exists",
                "this kind of provider exists already: edit it instead",
                "Bu tür bir sağlayıcı zaten var: onu düzenleyin",
                409,
            )
    preset = body.get("preset")
    presets = kinds.presets_for(kind)
    if presets and preset not in presets:
        preset = "generic"
    if body.get("name"):
        slug = clean_slug(str(body["name"]))
        if (await db.execute(select(SsoProvider.id).where(SsoProvider.name == slug))).first() is not None:
            raise _bad("slug_taken", "this slug is in use", "Bu kısa ad kullanımda", 409)
    else:
        wanted = {kinds.ENTRA: sso.PROVIDER, kinds.GOOGLE: "google"}.get(kind) or (
            preset if preset and preset != "generic" else kind
        )
        if kind == kinds.SAML and preset == "adfs":
            wanted = "adfs-saml"
        slug = await _free_slug(db, wanted)
    label = plain(str(body.get("display_name") or "")) or None
    if label is None and presets and preset and preset != "generic":
        label = str(presets[preset]["label"])
    last = (await db.execute(select(func.max(SsoProvider.sort_order)))).scalar_one()
    opts: dict[str, Any] = {"preset": preset} if preset else {}
    p = presets.get(preset or "", {})
    if kind == kinds.OIDC:
        opts.update(groups_claim=p.get("groups_claim", "groups"), roles_claim=p.get("roles_claim", "roles"))
        opts["scopes"] = list(p.get("scopes") or [])
    if kind == kinds.SAML:
        for key in ("email_attribute", "name_attribute", "groups_attribute"):
            if p.get(key):
                opts[key] = p[key]
    row = SsoProvider(
        name=slug,
        kind=kind,
        display_name=label[:80] if label else None,
        sort_order=(last or 0) + 10,
        enabled=False,
        # OIDC / SAML: invite-only by default; Entra / Google pin the tenant / domain (design v3 §5.5)
        self_signup=True,
        invite_only=kind in (kinds.OIDC, kinds.SAML),
        oidc_only_non_admins=False,
        role_mapping_enabled=False,
        allow_admin_mapping=False,
        invite_days=30,
        options=opts,
        updated_at=utcnow(),
        updated_by=actor.id,
    )
    db.add(row)
    await db.flush()
    await audit.record(db, "sso.provider_create", "sso_provider", row.id, after=_snapshot(row), actor=actor)
    return row


def _domains(values: Any, field: str) -> list[str]:
    if values is None:
        return []
    items = values if isinstance(values, list) else re.split(r"[,;\s]+", str(values))
    out: list[str] = []
    for v in items:
        if not isinstance(v, str) or not plain(v):
            continue
        try:
            d = sso.clean_domain(v)
        except ValueError as exc:
            raise _bad("invalid_domain", f"{field}: {v!r} is not a domain", f"Geçersiz alan adı: {plain(v)}") from exc
        if d and d not in out:
            out.append(d)
    return out


async def _check_default_role(db: AsyncSession, actor: User, role_id: int) -> None:
    role = await db.get(Role, role_id)
    if role is None:
        raise _bad("unknown_role", "unknown role", "bilinmeyen rol")
    if sso._too_privileged_for_default(role):  # noqa: SLF001
        raise _bad(
            "default_role_privileged",
            "the sign-up role must be the lowest one (e.g. Teacher or Viewer), not an administrative role",
            "Kendiliğinden açılan hesapların rolü en düşük rol olmalıdır (ör. Öğretmen ya da İzleyici)",
        )
    if not await may_grant_role(db, actor, role):
        raise sso._no_escalation("this role")  # noqa: SLF001


async def _admins_only_through(db: AsyncSession, row: SsoProvider) -> int:
    """Active administrators whose only way in is this provider (identity here, no password, no LDAP)."""
    q = (
        select(func.count(func.distinct(User.id)))
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(
            UserIdentity.provider == row.name,
            User.role == "ADMIN",
            User.is_active.is_(True),
            (User.password_hash.is_(None)) | (User.password_hash == ""),
            User.auth_source != "ldap",
        )
    )
    return int((await db.execute(q)).scalar_one())


async def update(db: AsyncSession, actor: User, row: SsoProvider, values: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update; returns the discovery report when one ran. Raises :class:`SsoAdminError`; the caller
    commits (or rolls back)."""
    if values.get("version") and values["version"] != version_of(row):
        editor = await db.get(User, row.updated_by) if row.updated_by else None
        who = audit.user_label(editor) or "—"
        raise _bad(
            "conflict",
            f"changed by {who} at {_iso(row.updated_at)} while you were editing; reload",
            f"Bu ayar siz düzenlerken {who} tarafından değiştirildi ({_iso(row.updated_at)}). Yenileyin.",
            409,
        )
    before = _snapshot(row)
    opts = dict(row.options or {})
    secret = values.get("client_secret")
    rediscover = key_changed = False
    if "name" in values and values["name"] and values["name"] != row.name:
        slug = clean_slug(values["name"])
        used = (
            await db.execute(select(func.count(UserIdentity.id)).where(UserIdentity.provider == row.name))
        ).scalar_one()
        if used or row.kind == kinds.ENTRA:
            raise _bad(
                "slug_locked", "the slug cannot change once accounts use it", "Kısa ad kullanımdayken değişmez", 409
            )
        if (await db.execute(select(SsoProvider.id).where(SsoProvider.name == slug))).first() is not None:
            raise _bad("slug_taken", "this slug is in use", "Bu kısa ad kullanımda", 409)
        for inv in (await db.execute(select(SsoInvite).where(SsoInvite.provider == row.name))).scalars():
            inv.provider = slug
        for m in (await db.execute(select(SsoRoleMapping).where(SsoRoleMapping.provider == row.name))).scalars():
            m.provider = slug
        row.name = slug
    if "display_name" in values:
        label = plain(str(values["display_name"] or ""))
        row.display_name = label[:80] or None
    if values.get("default_role_id") is not None:
        await _check_default_role(db, actor, int(values["default_role_id"]))
        row.default_role_id = int(values["default_role_id"])
    if values.get("allow_admin_mapping") and not row.allow_admin_mapping and actor.role != "ADMIN":
        raise _bad(
            "admin_only",
            "only an Administrator may allow mappings to administrative roles",
            "Yönetici rollerine eşlemeye yalnızca bir Yönetici izin verebilir",
            403,
        )
    for key in ("invite_only", "self_signup", "role_mapping_enabled", "allow_admin_mapping", "oidc_only_non_admins"):
        if values.get(key) is not None:
            setattr(row, key, bool(values[key]))
    if values.get("invite_days") is not None:
        row.invite_days = int(values["invite_days"])
    if values.get("sort_order") is not None:
        row.sort_order = int(values["sort_order"])
    if "allowed_domains" in values:
        row.allowed_domains = _domains(values["allowed_domains"], "allowed_domains") or None
    if "domain_hint" in values:
        try:
            row.domain_hint = sso.clean_domain(values["domain_hint"] or "")
        except ValueError as exc:
            raise _bad("invalid_domain", str(exc), "Geçersiz alan adı") from exc
    if secret:
        text = str(secret).strip().strip("\"'")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
            raise _bad(
                "secret_control_chars",
                "the secret contains control characters",
                "Gizli anahtar denetim karakterleri içeriyor",
            )
        row.client_secret_enc = encrypt_secret(text)
    if values.get("secret_expires") is not None:
        text = plain(str(values["secret_expires"]))[:10]
        if text:
            from datetime import date

            try:
                date.fromisoformat(text)
            except ValueError as exc:
                raise _bad(
                    "invalid_date", "secret_expires must be YYYY-MM-DD", "Bitiş tarihi YYYY-AA-GG olmalı"
                ) from exc
        opts["secret_expires"] = text or None
    if values.get("client_id") is not None:
        cid = plain(str(values["client_id"]))
        if row.kind == kinds.ENTRA and cid:
            try:
                cid = sso.clean_guid(cid, "client_id (application id)")
            except ValueError as exc:
                raise _bad(getattr(exc, "code", "sso_guid_invalid"), str(exc), getattr(exc, "tr", str(exc))) from exc
        row.client_id = cid[:64] or None
    if row.kind == kinds.ENTRA and values.get("tenant_id") is not None:
        try:
            row.tenant_id = sso.clean_tenant(str(values["tenant_id"]))
        except ValueError as exc:
            raise _bad(
                getattr(exc, "code", "sso_tenant"), str(exc), getattr(exc, "tr", "Geçersiz dizin kimliği")
            ) from exc
    if row.kind == kinds.GOOGLE and "hosted_domains" in values:
        opts["hosted_domains"] = _domains(values["hosted_domains"], "hosted_domains")
        if not opts["hosted_domains"]:
            raise _bad(
                "hosted_domain_required",
                "Google Workspace needs the institution's domain (hd), e.g. uni.edu.tr",
                "Google Workspace için kurumun alan adı (hd) gerekli, ör. uni.edu.tr",
            )
    if row.kind == kinds.OIDC:
        if values.get("issuer") is not None:
            try:
                issuer = clean_issuer(str(values["issuer"]))
            except ValueError as exc:
                raise _bad(
                    "invalid_issuer", str(exc), "Yayıncı (issuer) https:// ile başlayan bir adres olmalı"
                ) from exc
            if issuer != opts.get("issuer"):
                opts["issuer"] = issuer
                opts.pop("discovery", None)
                opts["discovery_ok"] = None
                rediscover = True
        for key, default in (("groups_claim", "groups"), ("roles_claim", "roles")):
            if values.get(key) is not None:
                try:
                    opts[key] = clean_claim_name(values[key], default)
                except ValueError as exc:
                    raise _bad("invalid_claim", str(exc), "Talep adı 1-120 karakter olmalı, boşluk içermemeli") from exc
        if values.get("trust_email") is not None:
            opts["trust_email"] = bool(values["trust_email"])
        if values.get("scopes") is not None:
            scopes = [plain(s) for s in values["scopes"] if isinstance(s, str) and plain(s)]
            if not all(_SCOPE_RX.match(s) for s in scopes):
                raise _bad("invalid_scope", "a scope has 1..64 characters [A-Za-z0-9_.:/-]", "Geçersiz kapsam")
            opts["scopes"] = scopes
    if row.kind == kinds.SAML:
        for key in ("email_attribute", "name_attribute", "groups_attribute", "subject_attribute", "idp_entity_id"):
            if key in values and values[key] is not None:
                opts[key] = plain(str(values[key]))[:255] or None
        if values.get("metadata_url") is not None:
            url = plain(str(values["metadata_url"])) or None
            if url and not secure_url(url):
                raise _bad(
                    "invalid_metadata_url", "the metadata URL must be https://", "Meta veri adresi https:// olmalı"
                )
            if url != opts.get("metadata_url"):
                opts["metadata_url"], rediscover = url, True
        if values.get("metadata_xml"):
            opts["metadata_xml"] = str(values["metadata_xml"])[: idp_saml.MAX_XML]
            rediscover = True
        if values.get("idp_entity_id") is not None:
            rediscover = rediscover or bool(opts.get("metadata_url") or opts.get("metadata_xml"))
        if values.get("metadata_signing_cert") is not None:
            pem = _signing_cert(str(values["metadata_signing_cert"]))
            if pem != opts.get("metadata_signing_cert"):
                if pem:
                    opts["metadata_signing_cert"] = pem
                else:
                    opts.pop("metadata_signing_cert", None)
                rediscover = rediscover or bool(opts.get("metadata_url") or opts.get("metadata_xml"))
        if values.get("sign_requests") is not None:
            opts["sign_requests"] = bool(values["sign_requests"])
        key_changed = await _sp_key_update(db, row, opts, values)
        if opts.get("sign_requests") and not opts.get("sp_private_key_enc"):
            raise _bad(
                "sp_key_required",
                "signing the requests needs an SP key: generate one or paste it first",
                "İstekleri imzalamak için bir SP anahtarı gerekli: önce anahtar oluşturun ya da yapıştırın",
            )
    row.options = opts
    report = None
    if rediscover:
        report = await discover(db, row, record=False)
    if values.get("enabled") is not None:
        want = bool(values["enabled"])
        if want and not row.enabled:
            await _check_enable(db, row)
        if not want and row.enabled and await sso.break_glass_admins(db) < 1 and await _admins_only_through(db, row):
            raise _bad(
                "last_admin_path",
                "refused: this is the last way in for an administrator. Create a local (break-glass) administrator "
                "first.",
                "Bu, yöneticilerin kullandığı son giriş yöntemi. Önce bir yerel yönetici hesabı (acil durum) "
                "oluşturun.",
                409,
            )
        row.enabled = want
    elif row.enabled:
        await _check_enable(db, row)  # a live provider keeps a usable configuration
    if row.oidc_only_non_admins and await sso.break_glass_admins(db) < 1:
        raise _bad(
            "break_glass",
            "refused: no active administrator with a local password would keep password sign-in (break-glass "
            "admin). Give one administrator a local password first.",
            "Reddedildi: yerel parolası olan etkin bir yönetici (acil durum yöneticisi) kalmıyor. Önce bir yöneticiye "
            "yerel parola verin.",
            409,
        )
    row.updated_at, row.updated_by = utcnow(), actor.id
    await db.flush()
    after = _snapshot(row)
    if after != before or secret or key_changed:
        if secret:
            after["client_secret_changed"] = True
        if key_changed:
            after["sp_private_key_changed"] = True
        await audit.record(db, "sso.provider_update", "sso_provider", row.id, before=before, after=after, actor=actor)
    return {"discovery": report} if report is not None else {}


def _signing_cert(text: str) -> str | None:
    if not plain(text):
        return None
    try:
        return idp_saml.pem_certificate(text)
    except ValueError as exc:
        raise _bad(
            "invalid_certificate",
            "the certificate could not be read: paste it as PEM (-----BEGIN CERTIFICATE-----) or as base64",
            "Sertifika okunamadı: PEM (-----BEGIN CERTIFICATE-----) ya da base64 olarak yapıştırın",
        ) from exc


async def _sp_key_update(db: AsyncSession, row: SsoProvider, opts: dict[str, Any], values: dict[str, Any]) -> bool:
    """Generate, paste or remove the SP key pair; ``True`` when it changed. The key is never echoed (not even in a
    refusal) and is stored Fernet-encrypted."""
    if values.get("sp_key_remove"):
        if opts.get("sign_requests"):
            raise _bad(
                "sp_key_in_use",
                "the requests are signed with this key: switch request signing off first",
                "İstekler bu anahtarla imzalanıyor: önce istek imzalamayı kapatın",
                409,
            )
        removed = bool(opts.pop("sp_private_key_enc", None))
        opts.pop("sp_certificate", None)
        return removed
    key_text, cert_text = values.get("sp_private_key"), values.get("sp_certificate")
    base, _src = await public_base(db)
    common_name = (base or "").split("://")[-1].split("/")[0] or f"smartsched-{row.name}"
    if values.get("sp_key_generate"):
        key_pem, cert_pem = saml_crypto.generate_keypair(common_name)
    elif key_text and plain(str(key_text)):
        try:
            key_pem = saml_crypto.pem_private_key(str(key_text))
        except ValueError:
            raise _bad(
                "invalid_private_key",
                "the SP private key could not be read: paste an unencrypted RSA key (2048 bits or more) as PEM",
                "SP özel anahtarı okunamadı: şifresiz bir RSA anahtarını (en az 2048 bit) PEM olarak yapıştırın",
            ) from None  # the cause would carry parser state of the key
        if cert_text and plain(str(cert_text)):
            cert_pem = _signing_cert(str(cert_text)) or ""
            if not saml_crypto.key_matches(key_pem, cert_pem):
                raise _bad(
                    "sp_key_mismatch",
                    "the SP certificate does not belong to this private key",
                    "SP sertifikası bu özel anahtarla eşleşmiyor",
                )
        else:
            cert_pem = saml_crypto.self_signed(key_pem, common_name)
    elif cert_text and plain(str(cert_text)):
        raise _bad(
            "sp_key_required",
            "an SP certificate needs its private key in the same request",
            "SP sertifikası, aynı istekte özel anahtarıyla birlikte verilmelidir",
        )
    else:
        return False
    opts["sp_private_key_enc"] = encrypt_secret(key_pem)
    opts["sp_certificate"] = cert_pem
    return True


async def _check_enable(db: AsyncSession, row: SsoProvider) -> None:
    base, _src = await public_base(db)
    if not base:
        raise _bad(
            "no_public_url",
            "enabling needs the public URL of the panel (PUBLIC_URL or integrations.public_url): the redirect URI "
            "is built from it",
            "Etkinleştirmek için panelin genel adresi (PUBLIC_URL) gereklidir: yönlendirme adresi ondan oluşturulur",
        )
    opts = row.options or {}
    if row.kind == kinds.SAML:
        if not idp_saml.AVAILABLE:
            raise _bad(
                "library_required",
                "SAML needs the optional library signxml on the server (pip install signxml)",
                "SAML için sunucuda isteğe bağlı signxml kütüphanesi gerekli (kütüphane gerekli)",
            )
        if opts.get("metadata_signing_cert") and not (opts.get("metadata") or {}).get("signed"):
            failed = next(
                (c for c in opts.get("discovery_checks") or [] if c.get("key") == "metadata_signature" and not c["ok"]),
                None,
            )
            raise _bad(
                "metadata_signature",
                failed["en"] if failed else "the metadata signature has not been verified yet: read the metadata",
                failed["tr"] if failed else "Meta veri imzası henüz doğrulanmadı: önce meta veriyi okuyun",
            )
        if await sso.saml_config(db, row) is None:
            raise _bad("discovery_required", "read the IdP metadata first", "Önce IdP meta verisini okuyun")
        return
    if row.kind == kinds.OIDC and not (opts.get("discovery_ok") and opts.get("discovery")):
        raise _bad(
            "discovery_required",
            "enabling needs a successful discovery of the issuer",
            "Etkinleştirmek için yayıncının keşif belgesi başarıyla okunmalı",
        )
    if await sso.client_config(db, row) is None:
        raise _bad(
            "incomplete",
            "enabling needs every required value (client id, client secret, tenant / hosted domain / issuer)",
            "Etkinleştirmek için gerekli tüm değerler girilmeli (istemci kimliği, gizli anahtar, kiracı / alan adı / "
            "yayıncı)",
        )


async def discover(
    db: AsyncSession, row: SsoProvider, *, record: bool = True, actor: User | None = None
) -> dict[str, Any]:
    """Fetch and validate the discovery document (OIDC kinds) or the IdP metadata (SAML); stores the endpoints and
    the check rows and the last check. Never raises for a provider-side problem: the report says what failed."""
    opts = dict(row.options or {})
    checks: list[dict[str, Any]]
    ok = False
    if row.kind == kinds.SAML:
        ok, checks = await _saml_metadata(opts)
    else:
        if row.kind == kinds.OIDC:
            issuer = opts.get("issuer")
            url = discovery_url(issuer) if issuer else None
        elif row.kind == kinds.GOOGLE:
            issuer, url = GOOGLE_ISSUERS[0], GOOGLE_DISCOVERY
        else:
            issuer = f"{sso.LOGIN_HOST}/{row.tenant_id}/v2.0" if row.tenant_id else None
            url = discovery_url(issuer) if issuer else None
        if not url or not issuer:
            checks = [errors.check("issuer", False, "missing")]
        else:
            doc, err = await fetch_discovery(url)
            if doc is None:
                checks = [errors.check("discovery", False, err or "unreachable", url=url)]
            else:
                endpoints, checks = validate_discovery(issuer, doc)
                checks.insert(0, errors.check("discovery", True, url=url))
                if endpoints is not None:
                    ok = True
                    if row.kind != kinds.ENTRA:  # Entra's endpoints are fixed by the pinned tenant
                        opts["discovery"] = endpoints
                        if row.kind == kinds.OIDC:
                            opts["issuer"] = endpoints["issuer"]
                    if row.kind == kinds.ENTRA:
                        checks.append(errors.check("tenant", True, tenant=row.tenant_id or ""))
    opts["discovery_ok"], opts["discovery_checks"] = ok, checks
    row.options = opts
    row.last_check_at, row.last_check_ok = utcnow(), ok
    row.last_check_detail = (
        "discovery ok" if ok else f"discovery: {next((c['key'] for c in checks if not c['ok']), '')}"
    )[:255]
    await db.flush()
    if record:
        await audit.record(
            db, "sso.provider_discover", "sso_provider", row.id, after={"ok": ok, "provider": row.name}, actor=actor
        )
    return {"ok": ok, "checks": checks}


async def _saml_metadata(opts: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    if not idp_saml.AVAILABLE:
        return False, [errors.check("library", False, "library_required")]
    xml: bytes | None = None
    if opts.get("metadata_url"):
        from app.services import sso as sso_mod

        try:
            async with sso_mod._client() as c:  # noqa: SLF001
                resp = await c.get(opts["metadata_url"], headers={"Accept": "application/samlmetadata+xml, */*"})
            if resp.status_code != 200:
                return False, [errors.check("metadata", False, f"HTTP {resp.status_code}")]
            xml = resp.content
        except Exception as exc:  # noqa: BLE001
            return False, [errors.check("metadata", False, type(exc).__name__)]
    elif opts.get("metadata_xml"):
        xml = str(opts["metadata_xml"]).encode("utf-8")
    if not xml:
        return False, [errors.check("metadata", False, "missing")]
    signing = opts.get("metadata_signing_cert")
    try:
        meta = idp_saml.parse_metadata(xml, opts.get("idp_entity_id"), signing_cert=signing)
    except idp_saml.MetadataError as exc:
        opts.pop("metadata", None)  # never keep metadata whose required signature failed
        return False, [errors.check("metadata_signature", False, exc.code)]
    except ValueError as exc:
        return False, [errors.check("metadata", False, str(exc))]
    checks = [errors.check("metadata", True, entity=meta["entity_id"])]
    if signing:
        info = saml_crypto.cert_info(signing) or {}
        checks.append(errors.check("metadata_signature", True, subject=info.get("subject", "")))
    not_after = _cert_not_after(meta["certs"])
    expired = not_after is not None and not_after < utcnow().isoformat()
    checks.append(errors.check("certificate", not expired, "expired" if expired else "", date=(not_after or "")[:10]))
    meta["cert_not_after"] = not_after
    meta["fetched_at"] = utcnow().isoformat(timespec="seconds")
    opts["metadata"] = meta
    return not expired, checks


def _cert_not_after(pems: list[str]) -> str | None:
    from cryptography import x509

    dates = []
    for pem in pems:
        try:
            cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
            dates.append(cert.not_valid_after_utc.replace(tzinfo=None).isoformat(timespec="seconds"))
        except ValueError:
            continue
    return max(dates) if dates else None


async def reorder(db: AsyncSession, actor: User, ids: list[int]) -> None:
    rows = {r.id: r for r in (await db.execute(select(SsoProvider))).scalars()}
    if sorted(set(ids)) != sorted(ids) or any(i not in rows for i in ids):
        raise _bad("invalid_order", "give every provider id once", "Her sağlayıcıyı bir kez verin")
    before = {r.name: r.sort_order for r in rows.values()}
    rest = [i for i in sorted(rows, key=lambda i: (rows[i].sort_order, i)) if i not in ids]
    for pos, pid in enumerate([*ids, *rest]):
        rows[pid].sort_order = (pos + 1) * 10
    await db.flush()
    after = {r.name: r.sort_order for r in rows.values()}
    await audit.record(db, "sso.provider_order", "sso_provider", None, before=before, after=after, actor=actor)


async def remove(db: AsyncSession, actor: User, row: SsoProvider) -> dict[str, int]:
    if row.enabled:
        raise _bad("enabled", "turn the provider off before deleting it", "Silmeden önce sağlayıcıyı kapatın", 409)
    counts: dict[str, int] = {}
    for model, key in ((UserIdentity, "identities"), (SsoRoleMapping, "mappings"), (SsoInvite, "invites")):
        res = await db.execute(delete(model).where(model.provider == row.name))
        counts[key] = int(res.rowcount or 0)  # type: ignore[attr-defined]
    before = _snapshot(row)
    await db.delete(row)
    await db.flush()
    await audit.record(db, "sso.provider_delete", "sso_provider", row.id, before=before, after=counts, actor=actor)
    return counts
