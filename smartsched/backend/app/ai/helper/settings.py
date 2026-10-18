"""The institution's helper controls, setting ``ai.helper`` (HB-15; architecture doc §5.9, §8; helper.md §4.1 rule 8).

One row in the settings table, so every admin sees and edits the same values (``GET / PUT /ai/admin/helper``,
audited ``ai.helper``). HB-09's memory switch (:mod:`app.ai.helper.memory`) lives in the same row.

```
{enabled, mode: ai | index, audiences: {<audience>: bool}, actions: {<name>: {enabled, audiences: [..] | null}},
 memory: {enabled, retention_days}, history_days, feedback_notes, guard: {scope: strict | normal | loose}}
```

* **Defaults** (nothing saved): everything on, ``mode: ai``. The helper still answers from the index only until an
  admin routes the ``helper`` feature (:mod:`app.ai.helper.status`). The writes are only the person's own bookings,
  requests and approval decisions (HB-05).
* **Audiences** are the welcome guide's (:func:`app.services.welcome.audiences_for`, permissions plus an instructor
  record), so both features agree on who is an academician. A person with none of the listed audiences counts as
  allowed unless the helper is off.
* **Actions**: an action switched off (or not listed for the person's audiences) is not in the model's tools, in
  ``GET /helper/actions``, on list-row buttons or nav cards (:func:`strip_card`), and its card / confirm answer 403
  ``action_off``. Permissions still apply on top (:func:`app.ai.helper.actions.registry.permitted`).
* **Off-scope check**: ``guard.scope`` picks the share of words the feature index must know for a question without a
  scheduling word (:data:`SCOPES`, :func:`app.ai.helper.guard.check` ``min_coverage``).
* **Limits** are not here: faculty and department quotas come from the HB-10 chain (``ai.limits``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import guard
from app.ai.helper import schema as s
from app.ai.helper.actions import registry as reg
from app.ai.helper.memory import DEFAULTS as MEMORY_DEFAULTS
from app.ai.helper.memory import SETTINGS_KEY
from app.services import settings_service
from app.services.bookings_perms import Access
from app.services.welcome import AUDIENCE_LABELS, AUDIENCES, audiences_for

MODES = ("ai", "index")
#: share of a question's words the index must know when it has no scheduling word (``guard.check``)
SCOPES: dict[str, float] = {"strict": 0.5, "normal": guard.MIN_COVERAGE, "loose": 0.2}
SCOPE_LABELS: dict[str, tuple[str, str, str, str]] = {
    "strict": (
        "Sıkı",
        "Strict",
        "Yalnızca açıkça SmartSched ile ilgili sorular yanıtlanır.",
        "Only questions clearly about SmartSched are answered.",
    ),
    "normal": (
        "Normal",
        "Normal",
        "Önerilen: menüdeki sözcükleri içeren sorular yanıtlanır.",
        "Recommended: questions with words from the menus are answered.",
    ),
    "loose": (
        "Gevşek",
        "Loose",
        "Daha az soru geri çevrilir; konu dışı sorular arada geçebilir.",
        "Fewer questions are turned away; an off-topic one may get through.",
    ),
}
RISK_LABELS: dict[str, tuple[str, str]] = {
    "R0": ("Yalnızca gösterir", "Shows only"),
    "R1": ("Kendi rezervasyonu", "Own booking"),
    "R2": ("Başkalarını etkiler", "Affects others"),
}
ACTION_OFF = (
    "Bu işlem yöneticiniz tarafından kapatıldı; sayfasından yapabilirsiniz.",
    "Your administrator switched this action off; you can do it on its page.",
)


class SettingsError(Exception):
    def __init__(self, status: int, code: str, tr: str, en: str, **data: Any) -> None:
        super().__init__(en)
        self.status, self.code, self.tr, self.en, self.data = status, code, tr, en, data


def defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "mode": "ai",
        "audiences": dict.fromkeys(AUDIENCES, True),
        "actions": {a.name: {"enabled": True, "audiences": None} for a in reg.all_actions()},
        "memory": dict(MEMORY_DEFAULTS["memory"]),
        "history_days": int(MEMORY_DEFAULTS["history_days"]),
        "feedback_notes": True,
        "guard": {"scope": "normal"},
    }


def _days(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 365 else default


def normalise(stored: dict[str, Any]) -> dict[str, Any]:
    """The stored value over the defaults; unknown keys, names and bad types fall back to the defaults."""
    out = defaults()
    if isinstance(stored.get("enabled"), bool):
        out["enabled"] = stored["enabled"]
    if stored.get("mode") in MODES:
        out["mode"] = stored["mode"]
    for k, v in (stored.get("audiences") or {}).items():
        if k in out["audiences"] and isinstance(v, bool):
            out["audiences"][k] = v
    for name, cfg in (stored.get("actions") or {}).items():
        if name not in out["actions"] or not isinstance(cfg, dict):
            continue
        if isinstance(cfg.get("enabled"), bool):
            out["actions"][name]["enabled"] = cfg["enabled"]
        auds = cfg.get("audiences")
        if isinstance(auds, list):
            out["actions"][name]["audiences"] = [a for a in AUDIENCES if a in auds]
    mem = stored.get("memory") or {}
    if isinstance(mem.get("enabled"), bool):
        out["memory"]["enabled"] = mem["enabled"]
    out["memory"]["retention_days"] = _days(mem.get("retention_days"), out["memory"]["retention_days"])
    out["history_days"] = _days(stored.get("history_days"), out["history_days"])
    if isinstance(stored.get("feedback_notes"), bool):
        out["feedback_notes"] = stored["feedback_notes"]
    scope = (stored.get("guard") or {}).get("scope")
    if scope in SCOPES:
        out["guard"]["scope"] = scope
    return out


def version(st: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(st, sort_keys=True).encode()).hexdigest()[:16]


async def load(session: AsyncSession) -> dict[str, Any]:
    raw = await settings_service.get_value(session, SETTINGS_KEY)
    try:
        stored = json.loads(raw) if isinstance(raw, str) and raw else {}
    except json.JSONDecodeError:
        stored = {}
    return normalise(stored if isinstance(stored, dict) else {})


def _unknown(code: str, field_name: str) -> SettingsError:
    if code == "unknown_action":
        return SettingsError(422, code, "Böyle bir yardımcı işlemi yok.", "There is no such helper action.",
                             field=field_name)  # fmt: skip
    return SettingsError(422, code, "Böyle bir kullanıcı grubu yok.", "There is no such audience.", field=field_name)


async def save(session: AsyncSession, patch: dict[str, Any], *, expected_version: str | None = None) -> dict[str, Any]:
    """Apply a partial patch (no commit). 409 ``stale_settings`` when another admin saved since ``expected_version``;
    422 ``unknown_action`` / ``unknown_audience``."""
    current = await load(session)
    if expected_version is not None and expected_version != version(current):
        raise SettingsError(
            409,
            "stale_settings",
            "Ayarlar siz düzenlerken başka bir yönetici tarafından değiştirildi; güncel hâli yüklendi.",
            "Another administrator changed these settings while you were editing; the current values are loaded.",
            settings=current,
            version=version(current),
        )
    nxt = json.loads(json.dumps(current))
    for key in ("enabled", "mode", "history_days", "feedback_notes"):
        if patch.get(key) is not None:
            nxt[key] = patch[key]
    for k, v in (patch.get("audiences") or {}).items():
        if k not in nxt["audiences"]:
            raise _unknown("unknown_audience", f"audiences.{k}")
        nxt["audiences"][k] = bool(v)
    for name, cfg in (patch.get("actions") or {}).items():
        if name not in nxt["actions"]:
            raise _unknown("unknown_action", f"actions.{name}")
        cfg = cfg or {}
        if cfg.get("enabled") is not None:
            nxt["actions"][name]["enabled"] = bool(cfg["enabled"])
        if "audiences" in cfg:
            auds = cfg["audiences"]
            if auds is not None:
                bad = [a for a in auds if a not in AUDIENCES]
                if bad:
                    raise _unknown("unknown_audience", f"actions.{name}.audiences")
                auds = [a for a in AUDIENCES if a in auds]
            nxt["actions"][name]["audiences"] = auds
    for k, v in (patch.get("memory") or {}).items():
        if v is not None and k in nxt["memory"]:
            nxt["memory"][k] = v
    if (patch.get("guard") or {}).get("scope") is not None:
        nxt["guard"]["scope"] = patch["guard"]["scope"]
    nxt = normalise(nxt)
    await settings_service.set_value(session, SETTINGS_KEY, json.dumps(nxt, sort_keys=True))
    return nxt


def min_coverage(st: dict[str, Any]) -> float:
    return SCOPES.get(str((st.get("guard") or {}).get("scope")), guard.MIN_COVERAGE)


async def audiences_of(session: AsyncSession, access: Access) -> list[str]:
    from app.models import Instructor

    linked = bool((await session.execute(select(exists().where(Instructor.user_id == access.user_id)))).scalar())
    return audiences_for(access.perms, instructor_linked=linked)


def person_allowed(st: dict[str, Any], auds: list[str]) -> bool:
    if not st["enabled"]:
        return False
    return not auds or any(st["audiences"].get(a, True) for a in auds)


def enabled_names(st: dict[str, Any], auds: list[str]) -> list[str]:
    """The actions switched on for someone with ``auds`` (permissions are checked separately)."""
    held = set(auds)
    return [
        name
        for name, cfg in st["actions"].items()
        if cfg["enabled"] and (cfg["audiences"] is None or held & set(cfg["audiences"]))
    ]


@dataclass
class Policy:
    """What the helper may do for one person (read once per turn / request)."""

    #: the helper is shown to this person (``reason`` says why not)
    enabled: bool
    reason: str | None
    mode: str
    audiences: list[str]
    #: the action names switched on for this person (``registry.permitted`` / ``tools_for`` ``enabled=``)
    actions: list[str] = field(default_factory=list)
    min_coverage: float = guard.MIN_COVERAGE


async def policy(session: AsyncSession, access: Access) -> Policy:
    st = await load(session)
    restricted = not all(st["audiences"].values()) or any(c["audiences"] is not None for c in st["actions"].values())
    # the audiences cost a query; without any audience switch they change nothing (the default)
    auds = await audiences_of(session, access) if restricted else audiences_for(access.perms, instructor_linked=False)
    allowed = person_allowed(st, auds)
    reason = None if allowed else ("disabled" if not st["enabled"] else "audience_off")
    return Policy(allowed, reason, st["mode"], auds, enabled_names(st, auds) if allowed else [], min_coverage(st))


def strip_card[C: BaseModel](card: C, enabled: set[str]) -> C:
    """Remove the buttons of switched-off actions: list-row buttons, nav ``actions``, result follow-ups, and the same
    inside a status card's fallback rows. Mutates and returns ``card``."""

    def walk(node: Any) -> None:
        if isinstance(node, s.NavCard):
            node.actions = [a for a in node.actions if a in enabled]
        if isinstance(node, s.Row):
            node.actions = [a for a in node.actions if a.action in enabled]
        if isinstance(node, s.ResultCard):
            node.follow_ups = [f for f in node.follow_ups if f.action is None or f.action in enabled]
        if isinstance(node, BaseModel):
            for name in type(node).model_fields:
                walk(getattr(node, name))
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(card)
    return card


def catalog() -> dict[str, Any]:
    return {
        "audiences": [{"id": a, "label": dict(AUDIENCE_LABELS[a])} for a in AUDIENCES],
        "actions": [
            {
                "name": a.name,
                "kind": a.kind,
                "risk": a.risk,
                "summary": {"tr": a.summary_tr, "en": a.summary_en},
                "risk_label": {"tr": RISK_LABELS[a.risk][0], "en": RISK_LABELS[a.risk][1]},
            }
            for a in reg.all_actions()
        ],
        "scopes": [
            {"id": k, "label": {"tr": tr, "en": en}, "hint": {"tr": htr, "en": hen}}
            for k, (tr, en, htr, hen) in SCOPE_LABELS.items()
        ],
    }


__all__ = [
    "ACTION_OFF",
    "AUDIENCES",
    "MODES",
    "RISK_LABELS",
    "SCOPES",
    "Policy",
    "SettingsError",
    "audiences_of",
    "catalog",
    "defaults",
    "enabled_names",
    "load",
    "min_coverage",
    "normalise",
    "person_allowed",
    "policy",
    "save",
    "strip_card",
    "version",
]
