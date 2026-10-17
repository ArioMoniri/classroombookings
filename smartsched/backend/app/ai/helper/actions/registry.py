"""Action registry (HB-03): the only things the helper can do, each one typed, permission-checked and tied to the
REST route that does the same on the page.

* :func:`action` registers an async function as an action: ``name``, ``kind`` (read / write), ``permission``
  (any-of, role level, empty = any signed-in person), a pydantic ``args`` model (``extra="forbid"``), the REST twin
  ``route`` (the drift test proves the route exists with the same guard and the mapped fields), the wire ``card``
  type, a per-user ``rate`` and, for writes, the risk class.
* Every action runs with the signed-in person's own :class:`~app.services.bookings_perms.Access` and calls the same
  service as its REST route, which re-checks permissions. Ids the model passes are resolved again.
* :func:`tools_for` gives the person's tool list for a model turn (≤ 10, strict JSON schemas, every property
  required, sentinels instead of null, the ``catalog.py`` structured-output budget). :func:`parse_args` validates a
  tool input (or the client's partial args) before anything runs; the model's output is never trusted.
"""

from __future__ import annotations

import copy
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import schema as s
from app.services.bookings_perms import Access

Kind = Literal["read", "write"]
Risk = Literal["R0", "R1", "R2"]
#: helper tool lists stay small for local models (architecture doc §5.2)
MAX_TOOLS = 10


class Args(BaseModel):
    """Base of every action's arguments: unknown fields are refused, strings are stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ArgsInvalid(ValueError):
    def __init__(self, action: str, issues: list[str]) -> None:
        super().__init__(f"{action}: " + "; ".join(issues))
        self.action, self.issues = action, issues


class ActionRefused(Exception):
    """A business refusal with a TR/EN message (403 / 404 / 409 / 422); the API maps it to a status card."""

    def __init__(self, status: int, code: str, tr: str, en: str, **data: Any) -> None:
        super().__init__(en)
        self.status, self.code, self.tr, self.en, self.data = status, code, tr, en, data


@dataclass
class Ctx:
    session: AsyncSession
    access: Access
    lang: str = "tr"


Runner = Callable[[Ctx, Any], Awaitable[s.CardBase]]


@dataclass(frozen=True)
class Action:
    name: str
    kind: Kind
    permission: tuple[str, ...]
    args: type[Args]
    summary_tr: str
    summary_en: str
    #: what the model reads (English, short); the tool description
    description: str
    #: the REST twin "METHOD /path" (under /api/v1)
    route: str
    card: str
    run: Runner
    #: action arg -> the REST twin's field (body, query or path) it feeds; args not listed are resolved by the
    #: registry from the database (e.g. a room code -> ``room_id``) and named in ``resolved``
    route_args: dict[str, str] = field(default_factory=dict)
    resolved: tuple[str, ...] = ()
    risk: Risk = "R0"
    #: per user: (calls, seconds)
    rate: tuple[int, int] = (30, 60)
    #: holders of this permission do not get the action (the nav's hideWith, e.g. my requests for planners)
    hide_with: str | None = None

    def allowed(self, access: Access) -> bool:
        if self.hide_with and self.hide_with in access.perms:
            return False
        return not self.permission or any(p in access.perms for p in self.permission)


REGISTRY: dict[str, Action] = {}


def action(
    *,
    name: str,
    kind: Kind,
    permission: Iterable[str] = (),
    args: type[Args],
    summary_tr: str,
    summary_en: str,
    description: str,
    route: str,
    card: str,
    route_args: dict[str, str] | None = None,
    resolved: Iterable[str] = (),
    risk: Risk = "R0",
    rate: tuple[int, int] = (30, 60),
    hide_with: str | None = None,
) -> Callable[[Runner], Runner]:
    if card not in s.CARD_TYPES:
        raise ValueError(f"{name}: unknown card type {card}")

    def deco(fn: Runner) -> Runner:
        if name in REGISTRY:
            raise ValueError(f"duplicate helper action {name}")
        REGISTRY[name] = Action(
            name=name,
            kind=kind,
            permission=tuple(permission),
            args=args,
            summary_tr=summary_tr,
            summary_en=summary_en,
            description=description,
            route=route,
            card=card,
            run=fn,
            route_args=dict(route_args or {}),
            resolved=tuple(resolved),
            risk=risk,
            rate=rate,
            hide_with=hide_with,
        )
        return fn

    return deco


def get(name: str) -> Action | None:
    _load()
    return REGISTRY.get(name)


def all_actions() -> list[Action]:
    _load()
    return list(REGISTRY.values())


def permitted(access: Access, enabled: Iterable[str] | None = None) -> list[Action]:
    """Actions the person holds (and, when given, the admin enabled for their audience; HB-15)."""
    on = set(enabled) if enabled is not None else None
    return [a for a in all_actions() if a.allowed(access) and (on is None or a.name in on)]


def permitted_names(access: Access) -> list[str]:
    return [a.name for a in permitted(access)]


# ------------------------------------------------------------------------------------------- strict schema


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _strip(v) for k, v in node.items() if k not in ("title", "default", "examples")}
        if out.get("type") == "object" or "properties" in out:
            props = out.get("properties", {})
            out["required"] = list(props)
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The tool ``input_schema`` of an args model: every property required (the model sends a sentinel such as
    ``""`` or ``0`` for "none"), no extra properties, no titles or defaults. Nested models are inlined."""
    raw = copy.deepcopy(model.model_json_schema())
    defs = raw.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].rsplit("/", 1)[1]])
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    schema = _strip(inline(raw))
    schema.pop("description", None)
    return schema


def tool(a: Action) -> dict[str, Any]:
    """Anthropic tool definition (``strict: true``); the provider adapters translate it for other servers."""
    return {"name": a.name, "description": a.description, "strict": True, "input_schema": strict_schema(a.args)}


def tools_for(
    access: Access,
    hits: Iterable[str] = (),
    enabled: Iterable[str] | None = None,
    *,
    limit: int = MAX_TOOLS,
    allow_writes: bool = True,
) -> list[dict[str, Any]]:
    """The person's tools for one model turn: what they hold ∩ what the admin enabled, the index pre-route's
    candidate actions first, ``open_feature`` always; writes dropped when the turn is tainted (§2.4)."""
    pool = [a for a in permitted(access, enabled) if allow_writes or a.kind == "read"]
    by_name = {a.name: a for a in pool}
    order: list[str] = []
    for n in ("open_feature", *hits):
        if n in by_name and n not in order:
            order.append(n)
    order += [a.name for a in pool if a.name not in order]
    return [tool(by_name[n]) for n in order[: max(1, min(limit, MAX_TOOLS))]]


def parse_args(a: Action, data: Any) -> Args:
    """Validate a tool input / partial client args against the action's model (``extra="forbid"``)."""
    if not isinstance(data, dict):
        raise ArgsInvalid(a.name, ["arguments must be an object"])
    try:
        return a.args.model_validate(data)
    except ValidationError as exc:
        raise ArgsInvalid(
            a.name, [f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors()]
        ) from exc


# ------------------------------------------------------------------------------------------------- rate


class RateLimit:
    """Per user and action, in-process (one per worker, like ``app.core.throttle``; HB-10 moves the gateway's own
    limits into PostgreSQL)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, a: Action, now: float | None = None) -> bool:
        """Count one call; ``True`` when over the action's limit (the call is refused and not counted)."""
        t = time.monotonic() if now is None else now
        n, window = a.rate
        q = self._hits[(user_id, a.name)]
        while q and q[0] <= t - window:
            q.popleft()
        if len(q) >= n:
            return True
        q.append(t)
        return False

    def reset(self) -> None:
        self._hits.clear()


RATE = RateLimit()

_loaded = False


def _load() -> None:
    """Import the action modules once (they register themselves)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from app.ai.helper.actions import approvals, bookings, nav, planning, usage  # noqa: F401


__all__ = [
    "Action",
    "ActionRefused",
    "Args",
    "ArgsInvalid",
    "Ctx",
    "MAX_TOOLS",
    "RATE",
    "REGISTRY",
    "action",
    "all_actions",
    "get",
    "parse_args",
    "permitted",
    "permitted_names",
    "strict_schema",
    "tool",
    "tools_for",
]
