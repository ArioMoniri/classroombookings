"""The model's tool calls, validated before anything runs (HB-03 / HB-06 seam; architecture doc §2.3, §2.4).

The turn loop (lane HB-B, ``POST /helper/turn``) owns the model call. For every assistant message it calls
:func:`apply_message`; this module owns what happens to the tool calls in it:

1. **Stop reasons first.** ``refusal``, ``max_tokens`` and ``pause_turn`` run no tool (:class:`TurnStopped`); a
   truncated or declined turn never acts.
2. **Only what was offered.** A tool name outside this turn's list (an unknown name, a write after taint, an action
   the admin switched off) is refused with ``not_offered``; an action switched off for the person's audience is
   refused again by :func:`run_action` (``action_off``, HB-15), which also strips switched-off buttons from cards.
3. **Strict arguments.** The input is validated with the action's pydantic model (``extra="forbid"``) before the
   action runs; a wrong shape answers ``invalid_args`` with the issues, so the model can correct itself (RA-05,
   RA-15). The provider's own ``strict: true`` is never trusted on its own.
4. **The same checks as the card endpoint** (:func:`run_action`: permission, per-user rate, the bookings gate, the
   action's own service checks), with the person's own ``Access``.
5. **Writes stop at a preview.** A write action answers a ``confirm`` card; only the person's button
   (``POST /helper/actions/confirm``) writes. The confirm and undo tokens never go back to the model
   (:meth:`ToolOutcome.model_content`).
6. Every card is checked against ``helper.card.v1`` (:func:`app.ai.helper.schema.validate_card`) before it is sent.

:func:`tool_results` builds the one user message with all ``tool_result`` blocks of a round.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions import registry as reg

#: stop reasons after which no tool of the message runs
STOPS = frozenset({"refusal", "max_tokens", "pause_turn", "model_context_window_exceeded"})
#: card fields the model never sees (the button's secrets and the client's correlation ids)
HIDDEN = frozenset({"token", "undo_token", "id", "expires_at", "undo_expires_at"})


class TurnStopped(Exception):
    """The assistant message ended with a stop reason after which nothing may run."""

    def __init__(self, stop_reason: str) -> None:
        super().__init__(stop_reason)
        self.stop_reason = stop_reason


async def gate(a: reg.Action, ctx: reg.Ctx) -> None:
    """The REST twin's bookings gate (maintenance mode), so neither the model nor a shortcut gets around it."""
    if a.gate is None:
        return
    from app.api.v1 import bookings as bookings_api

    try:
        if a.gate == "maintenance":
            await bookings_api.maintenance_gate(ctx.access, ctx.session)
        else:
            await bookings_api.list_gate(ctx.access, ctx.session)
    except HTTPException as exc:
        msg = exc.detail if isinstance(exc.detail, str) else "bookings are closed for maintenance"
        raise reg.ActionRefused(
            exc.status_code, "maintenance", "Rezervasyonlar şu an bakımda.", str(msg or "maintenance")
        ) from exc


RATE_TR = "Çok sık denediniz; bir dakika sonra yeniden deneyin."
RATE_EN = "Too many tries; try again in a minute."


async def run_action(ctx: reg.Ctx, a: reg.Action, raw_args: Any) -> s.CardBase:
    """One action, every check: permission, the admin's switch for the person's audience (HB-15), rate, gate,
    strict args, then the action (a read, or a write's preview); the card loses the buttons of switched-off actions.
    Raises :class:`~app.ai.helper.actions.registry.ActionRefused` / ``ArgsInvalid``; writes nothing for a write."""
    from app.ai.helper import settings as hs

    if not a.allowed(ctx.access):
        raise reg.ActionRefused(
            403, "not_allowed", "Bu işlem hesabınızda yok.", "This isn't available on your account."
        )
    enabled = set((await hs.policy(ctx.session, ctx.access)).actions)
    if a.name not in enabled:
        raise reg.ActionRefused(403, "action_off", *hs.ACTION_OFF)
    if reg.RATE.hit(ctx.access.user_id, a):
        raise reg.ActionRefused(429, "rate_limited", RATE_TR, RATE_EN)
    await gate(a, ctx)
    parsed = reg.parse_args(a, raw_args)
    card = hs.strip_card(await a.run(ctx, parsed), enabled)
    s.validate_card(cards.dump(card))
    return card


def offered(tools: Iterable[dict[str, Any]]) -> frozenset[str]:
    """The tool names of one turn's list (:func:`app.ai.helper.actions.registry.tools_for`)."""
    return frozenset(str(t["name"]) for t in tools)


@dataclass
class ToolOutcome:
    tool_use_id: str
    name: str
    #: the ``helper.card.v1`` card for the client (validated)
    card: dict[str, Any]
    is_error: bool
    #: the result carries free text other people wrote: the rest of the turn loses its write tools (§2.4)
    taints: bool = False
    issues: list[str] = field(default_factory=list)

    def model_content(self) -> str:
        """What the model reads back: the card without its tokens and ids; a pending write says it waits for the
        person's button (the model cannot confirm anything)."""
        data = {k: v for k, v in self.card.items() if k not in HIDDEN}
        if self.card.get("type") == "confirm":
            data["waiting_for"] = "the_user_button"
        if self.issues:
            data["issues"] = self.issues
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def _status(kind: str, code: str, tr: str, en: str, action: str | None) -> dict[str, Any]:
    safe = code if code.replace("_", "").isalpha() and 2 <= len(code) <= 48 else "error"
    action_name = action if action and reg.get(action) is not None else None
    return cards.dump(cards.status(kind, safe.lower(), tr, en, action=action_name))


async def run_tool_use(
    ctx: reg.Ctx, tool_use_id: str, name: str, tool_input: Any, *, offered: frozenset[str]
) -> ToolOutcome:
    a = reg.get(name) if name in offered else None
    if a is None:
        card = _status(
            "refusal", "not_offered", "Bu işlem burada yapılamaz.", "This action is not available here.", None
        )
        return ToolOutcome(tool_use_id, name, card, is_error=True)
    try:
        built = await run_action(ctx, a, tool_input)
    except reg.ArgsInvalid as exc:
        card = _status(
            "error",
            "invalid_args",
            "İşlemin bilgileri eksik ya da hatalı.",
            "The action's details are missing or invalid.",
            name,
        )
        return ToolOutcome(tool_use_id, name, card, is_error=True, issues=exc.issues)
    except reg.ActionRefused as exc:
        kind = "limit" if exc.status == 429 else ("refusal" if exc.status in (403, 404) else "error")
        fresh = exc.data.get("card")
        card = fresh if isinstance(fresh, dict) else _status(kind, exc.code, exc.tr, exc.en, name)
        return ToolOutcome(tool_use_id, name, card, is_error=True)
    return ToolOutcome(tool_use_id, name, cards.dump(built), is_error=False, taints=a.taints)


async def apply_message(ctx: reg.Ctx, message: Any, *, offered: frozenset[str]) -> list[ToolOutcome]:
    """Run the tool calls of one assistant message (an ``anthropic`` ``Message`` / ``BetaMessage`` or the provider
    adapters' equivalent with ``stop_reason`` and ``content`` blocks), in order, each validated first."""
    stop = str(getattr(message, "stop_reason", "") or "")
    if stop in STOPS:
        raise TurnStopped(stop)
    out: list[ToolOutcome] = []
    names = set(offered)
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        o = await run_tool_use(
            ctx, str(block.id), str(block.name), getattr(block, "input", None), offered=frozenset(names)
        )
        out.append(o)
        if o.taints:  # §2.4: after other people's free text, no write for the rest of the turn
            names = {n for n in names if (a := reg.get(n)) is not None and a.kind == "read"}
    return out


def writes_allowed_after(outcomes: Iterable[ToolOutcome]) -> bool:
    """``False`` once a tool result carried other people's free text (the next round's ``tools_for(allow_writes)``)."""
    return not any(o.taints for o in outcomes)


def tool_results(outcomes: Iterable[ToolOutcome]) -> dict[str, Any]:
    """All ``tool_result`` blocks of a round in ONE user message (parallel tool use)."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": o.tool_use_id,
                "content": o.model_content(),
                "is_error": o.is_error,
            }
            for o in outcomes
        ],
    }


__all__ = [
    "HIDDEN",
    "STOPS",
    "ToolOutcome",
    "TurnStopped",
    "apply_message",
    "gate",
    "offered",
    "run_action",
    "run_tool_use",
    "tool_results",
    "writes_allowed_after",
]
