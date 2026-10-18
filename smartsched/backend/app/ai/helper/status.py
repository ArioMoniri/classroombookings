"""What the helper's status chip shows (helper.md §5.2, ask A6): ``GET /helper/status``.

Owner default (2026-10-18): the helper is **index-only** (search, "Nerede?", shortcuts; nothing leaves the server)
until an admin routes the ``helper`` feature to a model. First the admin's ``ai.helper`` setting (HB-15,
:mod:`app.ai.helper.settings`): ``enabled: false`` or every audience of the person switched off gives
``enabled: false`` (the client hides the helper; ``reason`` ``disabled`` / ``audience_off``), and ``mode: index``
gives ``reason: index_mode``. Then AI mode needs all of:

1. an explicit ``helper`` route set by an admin (``ai.routes.features.helper``; the institution's default route does
   not count, so a fresh install or an existing AI setup never starts sending helper turns by itself);
2. the routed provider usable (enabled, credentials present);
3. the person's ``ai_personal`` consent (the helper is a personal feature; withdrawing it also clears the notes);
4. the turn loop deployed (``POST /helper/turn``, HB-06, lane HB-B).

Otherwise ``mode`` is ``index`` and ``reason`` says which step is missing. The provider name comes from the routing
config (``app.ai.providers.PROVIDERS``), never from the model; ``provider_kind`` is ``local`` when the provider's
base URL resolves to a private address (HB-13). Read-only: nothing here writes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

TURN_PATH = "/api/v1/helper/turn"

REASONS: dict[str, tuple[str, str]] = {
    "disabled": (
        "Yardımcı kurumunuzda kapalı; menü ve arama çalışmaya devam eder.",
        "The helper is switched off at your institution; the menus and search keep working.",
    ),
    "audience_off": (
        "Yardımcı sizin kullanıcı grubunuz için kapalı; menü ve arama çalışmaya devam eder.",
        "The helper is switched off for your user group; the menus and search keep working.",
    ),
    "index_mode": (
        "Yardımcı rehber modunda: arama, 'Nerede?' ve kısayollar çalışır; yapay zekâ kullanılmaz.",
        "The helper is in guide mode: search, 'Where?' and shortcuts work; no AI is used.",
    ),
    "not_routed": (
        "Yardımcı şu an rehber modunda: arama, 'Nerede?' ve kısayollar çalışır. Yapay zekâyı yöneticiniz açar.",
        "The helper is in guide mode: search, 'Where?' and shortcuts work. Your administrator switches on the AI.",
    ),
    "provider_unusable": (
        "Yardımcının yapay zekâ sağlayıcısı şu an kullanılamıyor; arama ve kısayollar çalışıyor.",
        "The helper's AI provider is not available right now; search and shortcuts work.",
    ),
    "consent_missing": (
        "Yapay zekâ yanıtları için Profil › Gizlilik'te rızanız gerekir; arama ve kısayollar çalışıyor.",
        "AI answers need your consent under Profile › Privacy; search and shortcuts work.",
    ),
    "turn_unavailable": (
        "Yardımcının yapay zekâ yanıtları henüz bu sunucuda yok; arama ve kısayollar çalışıyor.",
        "AI answers are not on this server yet; search and shortcuts work.",
    ),
}
ON = ("Yardımcı yapay zekâ ile yanıtlar.", "The helper answers with AI.")


def turn_registered(app: Any) -> bool:
    """Whether the turn loop's route is mounted (HB-06). Included routers are wrapped (FastAPI ≥ 0.140), so the
    flat route list misses them; the app's (cached) OpenAPI paths list every mounted route."""
    if any(getattr(r, "path", None) == TURN_PATH for r in getattr(app, "routes", ())):
        return True
    try:
        return TURN_PATH in (app.openapi().get("paths") or {})
    except Exception:  # noqa: BLE001 - a broken schema must not break the status chip
        return False


async def routing_reason(session: AsyncSession) -> str | None:
    """``not_routed`` / ``provider_unusable`` / ``None`` (an admin routed ``helper`` to a usable provider)."""
    from app.ai import gateway as gw
    from app.ai.providers import PROVIDERS

    resolved = await gw.resolve_route(session, "helper")
    if resolved.source != "feature" or not resolved.route.model:
        return "not_routed"
    provider = resolved.route.provider
    if provider not in PROVIDERS or not await gw.provider_usable(session, provider):
        return "provider_unusable"
    return None


async def helper_status(session: AsyncSession, user_id: int, *, turn_available: bool) -> dict[str, Any]:
    from app.ai import gateway as gw
    from app.ai.helper import settings as hs
    from app.ai.providers import PROVIDERS
    from app.models import User
    from app.services import kvkk
    from app.services.bookings_perms import load_access

    def off(reason: str, *, enabled: bool = True) -> dict[str, Any]:
        tr, en = REASONS[reason]
        return {
            "mode": "index",
            "enabled": enabled,
            "reason": reason,
            "provider_kind": None,
            "provider_label": None,
            "fallback_active": False,
            "message": {"tr": tr, "en": en},
        }

    user = await session.get(User, user_id)
    if user is not None:
        pol = await hs.policy(session, await load_access(session, user))
        if not pol.enabled:
            return off(pol.reason or "disabled", enabled=False)
        if pol.mode == "index":
            return off("index_mode")
    reason = await routing_reason(session)
    if reason is not None:
        return off(reason)
    if not await kvkk.has_consent(session, user_id, "ai_personal"):
        return off("consent_missing")
    if not turn_available:
        return off("turn_unavailable")
    resolved = await gw.resolve_route(session, "helper")
    provider = resolved.route.provider
    cfg = await gw.provider_config(session, provider)
    spec = PROVIDERS[provider]
    local = gw.is_local_url(str(cfg.get("base_url") or "")) if cfg.get("base_url") else False
    return {
        "mode": "ai",
        "enabled": True,
        "reason": None,
        "provider_kind": "local" if local else "cloud",
        "provider_label": {"tr": spec.label_tr, "en": spec.label_en},
        # the turn loop knows when it fell back (HB-B); the chip shows "Bulut · yedek" from its SSE event
        "fallback_active": False,
        "message": {"tr": ON[0], "en": ON[1]},
    }


__all__ = ["REASONS", "TURN_PATH", "helper_status", "routing_reason", "turn_registered"]
