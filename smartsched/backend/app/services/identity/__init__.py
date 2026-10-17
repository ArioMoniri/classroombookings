"""Identity providers (wave 3b W3-IDP): kinds and presets (``kinds``), the OIDC client contract and discovery
(``oidc``), the SAML 2.0 service provider (``saml``), the administration (``providers``), invitations (``invites``),
check rows / error translation (``errors``) and the integrations-hub status (``status``). The sign-in flow itself is
app/services/sso.py.

``integration_status(session)`` is the W3-HUB contract (app/api/v1/integrations.py); it is imported lazily here so
that importing this package never imports the sign-in flow (no import cycle)."""

from __future__ import annotations

from typing import Any


async def integration_status(session: Any) -> list[dict[str, Any]]:
    from app.services.identity.status import integration_status as cards

    return await cards(session)
