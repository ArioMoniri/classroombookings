"""Who is calling the model, for which feature, with which typed text (wave 3 W3-AI).

The gateway (:mod:`app.ai.client`) meters every call per user and feature and runs the input guard on the text a
person typed. The entry points of the AI layer declare that with :func:`ai_scope`::

    with ai_scope("chat", user_id=user.id, user_text=message):
        ...  # every model call in here is metered as chat for that user; the text is checked once

Resolution order for the user: the ``user_id`` of the scope, then :func:`set_actor`, then the request's audit
context on the caller's session (``session.info["audit_ctx"].actor_id``, set for every ``/api/v1`` request), then
the only ``User`` in the session's identity map, else ``None`` (a background job: org budget only).

Features (research R-AI-01): ``rules`` (rules from text), ``chat`` (chat edits), ``intake`` (uploads / the
Ingestion Council), ``vision`` (scans and images), ``explain`` (explanations), ``booking_nl`` (booking requests in
plain language), ``voice_stt`` (speech to text before any of them: the transcript returns to the person for
review and is sent through the feature it was spoken for; VO-01), plus ``guard`` (the optional model-based scope
check) and ``test`` (the admin's test call).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

FEATURES = ("rules", "chat", "intake", "vision", "explain", "booking_nl", "voice_stt")
#: features served by a speech model (never routed to a text model, never following the text default)
VOICE_FEATURES = ("voice_stt",)
INTERNAL_FEATURES = ("guard", "test", "other")
FEATURE_LABELS: dict[str, tuple[str, str]] = {
    "rules": ("Metinden kural", "Rules from text"),
    "chat": ("Sohbetle düzenleme", "Chat edits"),
    "intake": ("Dosyadan veri aktarımı", "File intake"),
    "vision": ("Taranmış belge / görüntü", "Scans and images"),
    "explain": ("Açıklamalar", "Explanations"),
    "booking_nl": ("Doğal dille rezervasyon", "Bookings in plain language"),
    "voice_stt": ("Sesle yazma", "Voice input"),
    "guard": ("Kapsam denetimi", "Scope check"),
    "test": ("Bağlantı testi", "Connection test"),
    "other": ("Diğer", "Other"),
}


@dataclass
class Interaction:
    """One user request (one chat message, one rules-from-text submission). ``rounds`` counts model calls."""

    feature: str
    user_id: int | None = None
    user_text: str | None = None
    checked: bool = False
    rounds: int = 0
    flags: list[str] = field(default_factory=list)


_scope: ContextVar[Interaction | None] = ContextVar("ai_scope", default=None)
_actor: ContextVar[int | None] = ContextVar("ai_actor", default=None)


@contextmanager
def ai_scope(feature: str, *, user_id: int | None = None, user_text: str | None = None) -> Iterator[Interaction]:
    """Declare the feature, the user and the typed text for every model call inside. A nested scope keeps the
    outer feature (an upload that reuses rule extraction stays ``intake``) and the outer text."""
    outer = _scope.get()
    if outer is not None:
        if user_id is not None and outer.user_id is None:
            outer.user_id = user_id
        yield outer
        return
    inter = Interaction(feature=feature, user_id=user_id, user_text=user_text)
    token = _scope.set(inter)
    try:
        yield inter
    finally:
        _scope.reset(token)


def current_scope() -> Interaction | None:
    return _scope.get()


def set_actor(user_id: int | None) -> None:
    """The request's signed-in user (called by the API dependency that loads the user; see the module docstring)."""
    _actor.set(user_id)


def current_actor() -> int | None:
    inter = _scope.get()
    if inter is not None and inter.user_id is not None:
        return inter.user_id
    return _actor.get()


def actor_from_session(session: Any) -> int | None:
    """The signed-in user of the request this session belongs to: the audit context every ``/api/v1`` request sets
    (``app.api.v1.audit.audit_context`` -> ``session.info["audit_ctx"].actor_id``), else the only ``User`` in the
    session's identity map, else ``None``."""
    if session is None:
        return None
    try:
        ctx = session.info.get("audit_ctx")
        if ctx is not None and getattr(ctx, "actor_id", None):
            return int(ctx.actor_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.models import User

        users = {o.id for o in session.sync_session.identity_map.values() if isinstance(o, User)}
    except Exception:  # noqa: BLE001 - best effort only
        return None
    return next(iter(users)) if len(users) == 1 else None


#: (module, function) of a caller -> feature, for the callers outside ``app/ai`` that do not declare a scope
_FRAME_FEATURES: list[tuple[str, str | None, str]] = [
    ("app.api.v1.chat", "post_chat", "chat"),
    ("app.api.v1.chat", "post_chat_stream", "chat"),
    ("app.api.v1.chat", "post_explain", "explain"),
    ("app.api.v1.chat", "post_elicit", "rules"),
    ("app.api.v1.chat", "post_preferences_upload", "intake"),
    ("app.api.v1.calendar", None, "explain"),
    ("app.services.calendar_views", None, "explain"),
    ("app.council", None, "intake"),
]


def infer_feature(max_depth: int = 40) -> str:
    """The feature from the declared scope, else from the call stack (module / function of the callers)."""
    inter = _scope.get()
    if inter is not None:
        return inter.feature
    frame = sys._getframe(1)
    depth = 0
    while frame is not None and depth < max_depth:
        mod = str(frame.f_globals.get("__name__", ""))
        fn = frame.f_code.co_name
        for prefix, name, feature in _FRAME_FEATURES:
            if (mod == prefix or mod.startswith(prefix + ".")) and (name is None or name == fn):
                return feature
        frame = frame.f_back  # type: ignore[assignment]
        depth += 1
    return "other"


__all__ = [
    "FEATURES",
    "FEATURE_LABELS",
    "INTERNAL_FEATURES",
    "VOICE_FEATURES",
    "Interaction",
    "actor_from_session",
    "ai_scope",
    "current_actor",
    "current_scope",
    "infer_feature",
    "set_actor",
]
