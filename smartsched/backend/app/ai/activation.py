"""One stored key switches the AI on for everyone (owner report 2026-11-02).

The helper (``Yardımcı``; the AI in Boş derslik bul and every other page) answers with the model only when an
administrator routed the ``helper`` feature explicitly (:func:`app.ai.helper.status.routing_reason`: the
institution's default route does not count). Before this module, saving the Anthropic key in the admin panel
therefore changed nothing for teachers: the helper stayed in guide mode (``reason: not_routed``) until someone also
synced the models and picked one for ``helper`` on Modeller.

Owner decision 2026-11-02: a key saved in the panel (``PUT /ai/admin/providers/{p}`` or ``PUT /settings``
``anthropic_api_key``) or written at deploy time (``deploy/seed/bootstrap_settings.py``, which calls the same
handler) is the institution's decision to use AI. :func:`activate` then writes the explicit ``helper`` route when
there is none:

* the institution's default route (``ai.routes.default``) when an admin set one, else
* Anthropic with the stored ``anthropic_model`` (:data:`app.ai.client.DEFAULT_MODEL` when unset).

An existing ``helper`` route is never changed (the admin's choice wins), the write is audited (``ai.routes``,
reason) and visible on Modeller. Every other gate stays: the helper's own switch and audiences (``ai.helper``,
``mode: index`` keeps guide mode), permissions, limits, guardrails and the person's KVKK ``ai_personal`` consent.

:func:`activate_once` runs at start-up for installs whose key was saved before this change: once per database (the
marker ``ai.activation`` records it), so an admin who later removes the ``helper`` route is not overruled by a
restart. Nothing here reads or logs a key value.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting, User

log = logging.getLogger(__name__)

MARKER_KEY = "ai.activation"
HELPER = "helper"


async def helper_route_for(session: AsyncSession) -> dict[str, Any] | None:
    """The route :func:`activate` would write for ``helper``: the admin's default route, else Anthropic with the
    legacy model; ``None`` when that provider has no usable credentials (nothing is activated without a key)."""
    from app.ai import gateway as gw
    from app.ai.providers import PROVIDERS

    routes = await gw.get_routes(session)
    default = gw.Route.from_dict(routes["default"])
    if default is not None and default.model and default.provider in PROVIDERS:
        if await gw.provider_usable(session, default.provider):
            return default.to_dict()
        return None
    if await gw.provider_usable(session, gw.DEFAULT_PROVIDER):
        return {"provider": gw.DEFAULT_PROVIDER, "model": await gw.legacy_model(session)}
    return None


async def _marker(session: AsyncSession) -> dict[str, Any] | None:
    row = await session.get(Setting, MARKER_KEY)
    if row is None or not row.value:
        return None
    try:
        data = json.loads(row.value)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def _put_marker(session: AsyncSession, result: str, actor: User | None, reason: str) -> None:
    value = json.dumps(
        {"result": result, "at": datetime.now(UTC).isoformat(timespec="seconds"), "by": actor.id if actor else None,
         "reason": reason[:200]},
        sort_keys=True,
    )  # fmt: skip
    row = await session.get(Setting, MARKER_KEY)
    if row is None:
        session.add(Setting(key=MARKER_KEY, value=value, is_secret=False))
    else:
        row.value, row.is_secret = value, False


async def activate(session: AsyncSession, *, actor: User | None, reason: str) -> dict[str, Any]:
    """Route ``helper`` when it has no route of its own and a provider is usable. Idempotent; flushes, the caller
    commits. Returns ``{"helper": "routed" | "kept" | "no_provider", ...}`` (never a key)."""
    from app.ai import gateway as gw
    from app.services import audit

    routes = await gw.get_routes(session)
    if gw.Route.from_dict(routes["features"].get(HELPER)) is not None:
        await _put_marker(session, "kept", actor, reason)
        await session.flush()
        return {"helper": "kept"}
    route = await helper_route_for(session)
    if route is None:
        return {"helper": "no_provider"}
    after = {"default": routes["default"], "features": {**routes["features"], HELPER: route}}
    await gw.put_json(session, gw.ROUTES_KEY, after)
    await audit.record(session, "ai.routes", "setting", gw.ROUTES_KEY, before=routes, after=after, actor=actor,
                       reason=reason)  # fmt: skip
    await _put_marker(session, "routed", actor, reason)
    await session.flush()
    log.info("AI activated for every user: helper routed to %s %s (%s)", route["provider"], route["model"], reason)
    return {"helper": "routed", "provider": route["provider"], "model": route["model"]}


async def activate_once(session: AsyncSession) -> dict[str, Any]:
    """Start-up: :func:`activate` once per database (a key saved before 2026-11-02). Commits when it wrote."""
    if await _marker(session) is not None:
        return {"helper": "done"}
    out = await activate(session, actor=None, reason="start-up: an AI key is stored (owner decision 2026-11-02)")
    if out["helper"] != "no_provider":
        await session.commit()
    return out


__all__ = ["MARKER_KEY", "activate", "activate_once", "helper_route_for"]
