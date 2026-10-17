"""The identity cards of the integrations hub (W3-HUB contract ``integration_status(session) -> list[dict]``; fields of
app/api/v1/integrations.py ``CardIn``). Read-only; no secret and no fragment of one."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sso import SsoProvider
from app.services.identity import kinds
from app.services.identity import providers as svc

_SUMMARY = {
    "connected": ("Girişte kullanılıyor.", "Used for sign-in."),
    "disabled": ("Yapılandırıldı, kapalı.", "Configured, switched off."),
    "not_configured": ("Kurulum bekliyor.", "Waiting for setup."),
    "error": ("Son kontrol başarısız.", "The last check failed."),
}


async def integration_status(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await session.execute(select(SsoProvider).order_by(SsoProvider.sort_order, SsoProvider.id))).scalars())
    cards: list[dict[str, Any]] = []
    for row in rows:
        p = await svc.provider_out(session, row)
        tr, en = _SUMMARY.get(p["status"], _SUMMARY["not_configured"])
        cards.append(
            {
                "key": f"identity.{row.name}"[:64],
                "name_tr": p["label"],
                "name_en": p["label_en"],
                "summary_tr": f"{kinds.DESCRIPTIONS[row.kind]['tr'][:200]} {tr}"[:300],
                "summary_en": f"{kinds.DESCRIPTIONS[row.kind]['en'][:200]} {en}"[:300],
                "status": p["status"],
                "enabled": row.enabled,
                "detail_tr": "Kütüphane gerekli (signxml)." if p["library_required"] else None,
                "detail_en": "Library required (signxml)." if p["library_required"] else None,
                "last_check_at": p["last_check_at"],
                "last_check_ok": p["last_check_ok"],
                "changed_by": p["changed_by"],
                "changed_at": p["changed_at"],
                "setup_href": f"/admin/integrations?tab=identity&setup=identity.{row.name}",
                # W3-HUB: drives the "secret expiring" bell event (only providers with a client secret)
                "secret_expires_at": p["secret_expires"] if p["client_secret_set"] else None,
                "toggle": {
                    "method": "PUT",
                    "path": f"/auth/sso/admin/providers/{row.id}",
                    "field": "enabled",
                    "enable_in_setup": not (p["configured"] and p["test_ok"]),
                },
                "ref": {"provider_id": row.id, "kind": row.kind},
            }
        )
    ldap = await svc.ldap_card(session)
    cards.append(
        {
            "key": "identity.ldap",
            "name_tr": ldap["label"],
            "name_en": ldap["label_en"],
            "summary_tr": kinds.DESCRIPTIONS[kinds.LDAP]["tr"],
            "summary_en": kinds.DESCRIPTIONS[kinds.LDAP]["en"],
            "status": "connected" if ldap["enabled"] else ("disabled" if ldap["configured"] else "not_configured"),
            "enabled": ldap["enabled"],
            "setup_href": "/settings?tab=ldap",
            "ref": {"kind": kinds.LDAP},
        }
    )
    if not rows:
        cards.insert(
            0,
            {
                "key": "identity.providers",
                "name_tr": "Kimlik sağlayıcıları",
                "name_en": "Identity providers",
                "summary_tr": "Microsoft, Google, OIDC ya da SAML ile girişi kurun.",
                "summary_en": "Set up sign-in with Microsoft, Google, OIDC or SAML.",
                "status": "not_configured",
                "setup_href": "/admin/integrations?tab=identity",
            },
        )
    return cards
