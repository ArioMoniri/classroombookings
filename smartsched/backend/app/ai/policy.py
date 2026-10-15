"""Admin switches for sending uploaded content to Anthropic (review 2026-10-15 D7 / P19-A1).

Two switches, both **off** by default:

* ``ai.intake_enabled`` - text read from uploaded files (Excel/CSV/DOCX/PDF/TXT/EML ...) may be sent to the
  Claude API to find rules. Off: the file is still read locally and every unit is routed to "needs AI".
* ``ai.vision_enabled`` - page images (scanned PDFs, photos) may be sent too. Needs intake.

Sending is a cross-border transfer under KVKK (Art. 9 as amended by Law 7499), so a switch only counts when an
administrator turned it on through :func:`set_policy` with the KVKK acknowledgement: that writes the sign-off
record ``ai.kvkk_signoff`` (who, when, legal basis, notice version, features) and an ``ai.policy`` audit event.
A flag set any other way (the generic ``PUT /settings`` ``extra``) is ignored by :func:`ai_allowed`.

Every AI path that sends uploaded content calls :func:`ai_allowed` first (the chat upload today; the council
intake path once merged). Text the planner types (chat, elicitation) is not governed by these switches.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting, User

INTAKE_KEY = "ai.intake_enabled"
VISION_KEY = "ai.vision_enabled"
SIGNOFF_KEY = "ai.kvkk_signoff"
FEATURES: dict[str, str] = {"intake": INTAKE_KEY, "vision": VISION_KEY}
AIKind = Literal["intake", "vision"]

LEGAL_BASIS = "KVKK Art. 9 as amended by Law 7499 (cross-border transfer to the Claude API, Anthropic PBC)"
NOTICE_VERSION = "2026-10-15"
NOTICE = {
    "tr": (
        "Bu özellik açıldığında yüklenen dosyaların metni (görüntü izni varsa sayfa görüntüleri) kural önerisi "
        "çıkarmak için yurt dışındaki Claude API'ye (Anthropic) gönderilir. Göndermeden önce e-posta adresleri ve "
        "telefon numaraları maskelenir; yine de dosyalarda kişisel veri (ad, soyad) bulunabilir. Her öneri "
        "koordinatör onayı olmadan kaydedilmez. Açmadan önce KVKK sorumlusunun onayını alın."
    ),
    "en": (
        "When enabled, the text of uploaded files (and page images if vision is enabled) is sent to the Claude "
        "API (Anthropic, outside Türkiye) to find rule proposals. E-mail addresses and phone numbers are masked "
        "first, but files may still contain personal data such as names. No proposal is saved without a "
        "coordinator's review. Obtain the KVKK officer's sign-off before enabling."
    ),
}


class PolicyError(ValueError):
    """Invalid switch change (HTTP 422 at the API)."""


async def _raw(session: AsyncSession, key: str) -> str | None:
    row = await session.get(Setting, key)
    return row.value if row is not None else None


async def _put(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value, is_secret=False))
    else:
        row.value, row.is_secret = value, False


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


async def _signoff(session: AsyncSession) -> dict[str, Any] | None:
    raw = await _raw(session, SIGNOFF_KEY)
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def ai_allowed(session: AsyncSession, kind: AIKind) -> bool:
    """May uploaded content of ``kind`` be sent to Anthropic? The switch must be on *and* covered by the
    administrator's KVKK sign-off; ``vision`` also needs ``intake``."""
    if kind not in FEATURES:
        raise ValueError(f"unknown AI feature {kind!r}")
    needed = ["intake"] if kind == "intake" else ["intake", "vision"]
    sign = await _signoff(session)
    covered = set(sign.get("features") or []) if sign and sign.get("enabled") else set()
    for feature in needed:
        if not _truthy(await _raw(session, FEATURES[feature])) or feature not in covered:
            return False
    return True


async def get_policy(session: AsyncSession) -> dict[str, Any]:
    """State for the settings screen: effective switches, the sign-off record and the notice texts."""
    return {
        "intake_enabled": await ai_allowed(session, "intake"),
        "vision_enabled": await ai_allowed(session, "vision"),
        "signoff": await _signoff(session),
        "notice": NOTICE,
        "notice_version": NOTICE_VERSION,
        "legal_basis": LEGAL_BASIS,
    }


async def set_policy(
    session: AsyncSession,
    actor: User,
    *,
    intake_enabled: bool | None = None,
    vision_enabled: bool | None = None,
    kvkk_ack: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """Change the switches (administrator only; the API checks the role). Turning anything on needs
    ``kvkk_ack``; every change replaces the sign-off record and is audited. Commits."""
    from app.services import audit

    before = await get_policy(session)
    intake = before["intake_enabled"] if intake_enabled is None else bool(intake_enabled)
    vision = before["vision_enabled"] if vision_enabled is None else bool(vision_enabled)
    if vision and not intake:
        raise PolicyError("vision needs intake: enable intake_enabled too")
    turning_on = (intake and not before["intake_enabled"]) or (vision and not before["vision_enabled"])
    if turning_on and not kvkk_ack:
        raise PolicyError("enabling AI intake needs the KVKK acknowledgement (kvkk_ack=true) after the officer's sign-off")
    features = [f for f, on in (("intake", intake), ("vision", vision)) if on]
    record = {
        "by": actor.id,
        "by_label": actor.full_name or actor.email,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "features": features,
        "enabled": bool(features),
        "legal_basis": LEGAL_BASIS,
        "notice_version": NOTICE_VERSION,
        "acknowledged": bool(kvkk_ack),
        **({"reason": reason.strip()[:500]} if reason and reason.strip() else {}),
    }
    await _put(session, INTAKE_KEY, "true" if intake else "false")
    await _put(session, VISION_KEY, "true" if vision else "false")
    await _put(session, SIGNOFF_KEY, json.dumps(record, ensure_ascii=False))
    await session.flush()
    await audit.record(
        session,
        "ai.policy",
        "setting",
        "ai.policy",
        before={"intake_enabled": before["intake_enabled"], "vision_enabled": before["vision_enabled"]},
        after={"intake_enabled": intake, "vision_enabled": vision, "features": features},
        actor=actor,
        reason=reason,
    )
    await session.commit()
    return await get_policy(session)


__all__ = [
    "FEATURES",
    "INTAKE_KEY",
    "NOTICE",
    "SIGNOFF_KEY",
    "VISION_KEY",
    "PolicyError",
    "ai_allowed",
    "get_policy",
    "set_policy",
]
