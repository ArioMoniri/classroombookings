"""Helper telemetry and feedback (HB-14; architecture doc §2.7, §5.7). Product numbers, never prompt text.

Rows of ``helper_events`` (owner-only RLS; written in the system scope, read only as aggregates):

* ``query``: one per helper turn (:func:`record_turn`, called by ``POST /helper/turn``) and per submitted search
  (``GET /helper/search?final=true``): the answering ``mode`` (``ai`` / ``index``), the turn ``outcome``, the
  fallback code in ``reason``, ``latency_ms``, the top index hit in ``feature_id``, provider / model for AI turns.
  When the index found nothing, ``query`` keeps the Turkish-folded words without digits or e-mail-like words (64
  characters at most); the admin summary shows such a query only after ≥ :data:`K_MIN` different people typed it.
* ``preview`` / ``confirm`` / ``undo``: a write's steps with ``action`` and ``outcome`` (``ok`` or the refusal code);
* ``nav_click`` / ``form_open`` / ``cancel``: sent by the client (``POST /helper/events``);
* ``thumb_up`` / ``thumb_down``: ``POST /helper/feedback``; one per person and turn; a thumbs-down may carry a
  ``reason`` and, when the institution allows notes (``ai.helper.feedback_notes``), the person's own ``note``
  (≤ 300). Notes are never shown to admins; the DSR export lists them; erasure and the 90-day purge delete them.

Prometheus (no user label): ``smartsched_helper_turns{mode,outcome}``,
``smartsched_helper_actions{action,stage,outcome}``, ``smartsched_helper_latency_seconds{mode}``. The ``helper turn``
log line uses the OpenTelemetry GenAI attribute names (``gen_ai.operation.name`` ...), so an exporter can be added
later without renaming.

:func:`summary` is ``GET /ai/admin/helper/summary``: counts, shares, the action funnel, p50 / p95, cost per feature
from ``ai_usage``, k-anonymous unanswered queries and four sentence tiles (simplicity principle).
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import guardrails as g
from app.ai.helper import schema as s
from app.core import observability as obs
from app.core import rls
from app.models.base import utcnow
from app.models.helper import HelperEvent
from app.services.bookings_perms import Access

log = logging.getLogger("smartsched.helper")

CLIENT_KINDS = ("nav_click", "form_open", "cancel")
THUMBS = ("thumb_up", "thumb_down")
OUTCOMES = ("answered", "confirm", "refused", "index", "fallback", "rounds_exhausted")
FEEDBACK_REASONS: dict[str, tuple[str, str]] = {
    "wrong_page": ("Yanlış sayfa", "Wrong page"),
    "wrong_answer": ("Yanlış bilgi", "Wrong information"),
    "not_helpful": ("İşime yaramadı", "Not helpful"),
    "too_slow": ("Çok yavaş", "Too slow"),
    "other": ("Başka", "Other"),
}
#: a query shows in the unanswered list only after this many different people typed it
K_MIN = 5
MAX_DAYS = 90
MISSES = 10
NOTE_CHARS = 300
RATE_PER_MINUTE = 30
TURN_ID = re.compile(r"^[a-f0-9]{16}$")
_LETTERS = re.compile(r"[^a-z]")


class TelemetryError(Exception):
    def __init__(self, status: int, code: str, tr: str, en: str, **data: Any) -> None:
        super().__init__(en)
        self.status, self.code, self.tr, self.en, self.data = status, code, tr, en, data


class _Rate:
    """Per person, in-process: feedback and client events (like ``registry.RATE``)."""

    def __init__(self) -> None:
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def hit(self, user_id: int) -> bool:
        now = time.monotonic()
        q = self._hits[user_id]
        while q and q[0] <= now - 60:
            q.popleft()
        if len(q) >= RATE_PER_MINUTE:
            return True
        q.append(now)
        return False

    def reset(self) -> None:
        self._hits.clear()


RATE = _Rate()


def _limited(user_id: int) -> None:
    if RATE.hit(user_id):
        raise TelemetryError(
            429, "rate_limited", "Çok sık gönderdiniz; bir dakika sonra yeniden deneyin.", "Too many; try in a minute."
        )


def fold_miss(text: str) -> str | None:
    """The words of an unanswered query as the summary may show them: Turkish-folded, letters only, without words
    that carry digits or look like an address; ≤ 64 characters."""
    out = ""
    for w in g.fold(text or "").split():
        if any(ch.isdigit() for ch in w) or "@" in w or "/" in w:
            continue
        w = _LETTERS.sub("", w)
        if len(w) < 2:
            continue
        if len(f"{out} {w}") > 65:
            break
        out = f"{out} {w}".strip()
    return out or None


async def _write(session: AsyncSession, *rows: HelperEvent) -> None:
    """Add rows in the system scope (telemetry is written for the person, read only as aggregates). No commit."""
    async with rls.system_scope(session):
        session.add_all(rows)
        await session.flush()


def observe_action(action: str, stage: str, outcome: str) -> None:
    obs.record_helper_action(action, stage, outcome)


async def record_action(
    session: AsyncSession, user_id: int, action: str, stage: str, outcome: str = "ok", turn_id: str | None = None
) -> None:
    """One write step (``preview`` / ``confirm`` / ``undo``) with its outcome; no commit."""
    observe_action(action, stage, outcome)
    await _write(
        session,
        HelperEvent(ts=utcnow(), user_id=user_id, turn_id=turn_id, kind=stage, action=action, outcome=outcome[:16]),
    )


async def record_query(
    session: AsyncSession,
    user_id: int,
    *,
    text: str,
    mode: str,
    outcome: str,
    top_feature: str | None,
    latency_s: float | None,
    turn_id: str | None = None,
    reason: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    keep_miss: bool = True,
) -> None:
    """One ``query`` row; the typed text is kept only as a folded miss (no index hit)."""
    obs.record_helper_turn(mode, outcome, latency_s)
    await _write(
        session,
        HelperEvent(
            ts=utcnow(),
            user_id=user_id,
            turn_id=turn_id,
            kind="query",
            mode=mode,
            outcome=outcome[:16],
            reason=(reason or None) and str(reason)[:48],
            latency_ms=int(latency_s * 1000) if latency_s is not None else None,
            feature_id=top_feature,
            provider=provider,
            model=(model or None) and str(model)[:64],
            query=fold_miss(text) if top_feature is None and keep_miss else None,
        ),
    )


async def record_turn(
    session: AsyncSession,
    access: Access,
    text: str,
    result: Any,
    *,
    latency_s: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Telemetry for one finished turn (``app.ai.helper_turn.TurnResult``): the ``query`` row, a ``preview`` row
    per ``confirm`` card, the metrics and the GenAI log line. Never raises; no commit (the turn's session commits)."""
    from app.ai.helper import guard
    from app.ai.helper.index import get_index

    try:
        hits = get_index().search(text, access.perms, limit=1)
        refusal = next((c for c in result.cards if c.get("type") == "refusal"), None)
        # an off-scope question is an index miss worth showing; an injection attempt is not
        keep = result.outcome != "refused" or (refusal is not None and refusal.get("code") == guard.OUT_OF_SCOPE)
        provider = model = None
        if result.model_calls:
            from app.ai import gateway as gw

            route = (await gw.resolve_route(session, "helper")).route
            provider, model = route.provider, route.model
        await record_query(
            session,
            access.user_id,
            text=text,
            mode=result.mode,
            outcome=result.outcome,
            top_feature=hits[0].entry.id if hits else None,
            latency_s=latency_s,
            turn_id=result.turn_id,
            reason=result.fallback,
            provider=provider,
            model=model,
            keep_miss=keep,
        )
        for c in result.cards:
            if c.get("type") == "confirm" and c.get("action"):
                await record_action(session, access.user_id, str(c["action"]), "preview", "ok", result.turn_id)
        tools = sorted({str(c["action"]) for c in result.cards if c.get("action")})
        extra: dict[str, Any] = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "helper",
            "gen_ai.provider.name": provider or "none",
            "gen_ai.request.model": model or "none",
            "gen_ai.tool.name": ",".join(tools),
            "helper.mode": result.mode,
            "helper.outcome": result.outcome,
            "helper.model_calls": int(result.model_calls),
            "helper.latency_ms": int(latency_s * 1000),
        }
        if input_tokens is not None:
            extra["gen_ai.usage.input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            extra["gen_ai.usage.output_tokens"] = int(output_tokens)
        log.info("helper turn", extra=extra)
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        log.warning("helper telemetry failed", exc_info=True)


async def feedback(
    session: AsyncSession, user_id: int, turn_id: str, thumb: str, reason: str | None, note: str | None
) -> dict[str, bool]:
    """Thumbs up / down for one turn; the second answer replaces the first. No commit."""
    from app.ai.helper import settings as hs

    _limited(user_id)
    down = thumb == "down"
    keep_note = down and bool((note or "").strip()) and bool((await hs.load(session))["feedback_notes"])
    async with rls.system_scope(session):
        await session.execute(
            delete(HelperEvent)
            .where(HelperEvent.user_id == user_id, HelperEvent.turn_id == turn_id, HelperEvent.kind.in_(THUMBS))
            .execution_options(synchronize_session=False)
        )
    await _write(
        session,
        HelperEvent(
            ts=utcnow(),
            user_id=user_id,
            turn_id=turn_id,
            kind="thumb_down" if down else "thumb_up",
            reason=reason if down else None,
            note=s.scrub(note, NOTE_CHARS) if keep_note else None,
        ),
    )
    return {"saved": True, "note_saved": keep_note}


async def client_event(
    session: AsyncSession,
    user_id: int,
    kind: str,
    *,
    turn_id: str | None = None,
    feature_id: str | None = None,
    action: str | None = None,
) -> None:
    """``nav_click`` / ``form_open`` / ``cancel`` from the client; ids must exist. No commit."""
    from app.ai.helper.actions import registry as reg
    from app.ai.helper.index import get_index

    _limited(user_id)
    if feature_id is not None and feature_id not in {e.id for e in get_index().entries}:
        raise TelemetryError(422, "unknown_feature", "Böyle bir sayfa yok.", "There is no such page.")
    if action is not None and reg.get(action) is None:
        raise TelemetryError(422, "unknown_action", "Böyle bir işlem yok.", "There is no such action.")
    await _write(
        session,
        HelperEvent(ts=utcnow(), user_id=user_id, turn_id=turn_id, kind=kind, feature_id=feature_id, action=action),
    )


# ---------------------------------------------------------------------------------------------- summary


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 2) if whole else None


def _pct(x: float | None) -> int:
    return round((x or 0) * 100)


def _rank(values: list[int], q: float) -> int:
    """Nearest-rank percentile."""
    return values[max(0, math.ceil(q * len(values)) - 1)]


def _tiles(days: int, turns: dict[str, Any], fb: dict[str, Any], defl: dict[str, Any], acts: list[dict[str, Any]],
           thumbs: dict[str, Any]) -> list[dict[str, str]]:  # fmt: skip
    n, nav = turns["total"], defl["nav_clicks"]
    if n:
        q = (
            f"Son {days} günde {n} soru; {nav} kez doğrudan sayfaya gidildi (%{_pct(defl['share'])}).",
            f"{n} questions in the last {days} days; {nav} times people went straight to a page "
            f"({_pct(defl['share'])}%).",
        )
        m = (
            f"Yanıtların {turns['ai']} tanesi yapay zekâdan, {turns['index']} tanesi dizinden geldi; "
            f"{fb['count']} kez yedeğe geçildi.",
            f"{turns['ai']} answers came from the AI and {turns['index']} from the index; it fell back "
            f"{fb['count']} times.",
        )
    else:
        q = (f"Son {days} günde yardımcıya soru sorulmadı.", f"No questions to the helper in the last {days} days.")
        m = ("Henüz yanıt yok.", "No answers yet.")
    confirmed = sum(a["confirm"] for a in acts)
    undone = sum(a["undo"] for a in acts)
    a = (
        (f"Yardımcıdan {confirmed} işlem onaylandı, {undone} tanesi geri alındı.",
         f"{confirmed} actions were confirmed through the helper and {undone} undone.")
        if confirmed or undone
        else ("Yardımcıdan henüz işlem yapılmadı.", "No actions through the helper yet.")
    )  # fmt: skip
    t = (
        (f"Yanıtlara {thumbs['up']} olumlu, {thumbs['down']} olumsuz oy verildi.",
         f"Answers got {thumbs['up']} thumbs up and {thumbs['down']} thumbs down.")
        if thumbs["up"] or thumbs["down"]
        else ("Henüz geri bildirim yok.", "No feedback yet.")
    )  # fmt: skip
    return [
        {"id": tid, "tr": tr, "en": en}
        for tid, (tr, en) in zip(("questions", "modes", "actions", "thumbs"), (q, m, a, t), strict=True)
    ]


async def summary(session: AsyncSession, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    """Aggregates of the last ``days`` (1..90): no ids, no notes, no prompt text. Reads in the system scope."""
    from app.ai.context import FEATURE_LABELS
    from app.services import ai_usage as meter

    days = max(1, min(int(days), MAX_DAYS))
    end = now or utcnow()
    since = end - timedelta(days=days)
    window = (HelperEvent.ts >= since, HelperEvent.ts < end)
    E = HelperEvent
    async with rls.system_scope(session):
        groups = (
            await session.execute(
                select(E.kind, E.mode, E.outcome, E.reason, E.action, func.count(E.id))
                .where(*window)
                .group_by(E.kind, E.mode, E.outcome, E.reason, E.action)
            )
        ).all()
        latencies = (
            await session.execute(
                select(E.mode, E.latency_ms).where(*window, E.kind == "query", E.latency_ms.is_not(None))
            )
        ).all()
        notes = (
            await session.execute(select(func.count(E.id)).where(*window, E.kind == "thumb_down", E.note.is_not(None)))
        ).scalar_one()
        users = func.count(distinct(E.user_id))
        misses = (
            await session.execute(
                select(E.query, users, func.count(E.id))
                .where(*window, E.kind == "query", E.query.is_not(None))
                .group_by(E.query)
                .having(users >= K_MIN)
                .order_by(func.count(E.id).desc(), E.query)
                .limit(MISSES)
            )
        ).all()
    turns: dict[str, Any] = {"total": 0, "ai": 0, "index": 0, "by_outcome": dict.fromkeys(OUTCOMES, 0)}
    fb_reasons: dict[str, int] = defaultdict(int)
    nav = 0
    funnel: dict[str, dict[str, int]] = {}
    thumbs: dict[str, Any] = {"up": 0, "down": 0, "reasons": {}}
    for kind, mode, outcome, reason, action, n in groups:
        n = int(n)
        if kind == "query":
            turns["total"] += n
            if mode in ("ai", "index"):
                turns[mode] += n
            if outcome in turns["by_outcome"]:
                turns["by_outcome"][outcome] += n
            if outcome == "fallback":
                fb_reasons[reason or "unknown"] += n
        elif kind == "nav_click":
            nav += n
        elif kind in ("preview", "confirm", "undo", "form_open", "cancel") and action:
            row = funnel.setdefault(
                action, {"preview": 0, "confirm": 0, "undo": 0, "form_open": 0, "cancel": 0, "failed": 0}
            )
            if kind in ("preview", "confirm", "undo") and outcome not in (None, "ok"):
                row["failed"] += n
            else:
                row[kind] += n
        elif kind == "thumb_up":
            thumbs["up"] += n
        elif kind == "thumb_down":
            thumbs["down"] += n
            if reason:
                thumbs["reasons"][reason] = thumbs["reasons"].get(reason, 0) + n
    fb_count = turns["by_outcome"]["fallback"]
    fallback = {
        "count": fb_count,
        "share": _share(fb_count, turns["ai"] + fb_count),
        "by_reason": [{"reason": r, "count": c} for r, c in sorted(fb_reasons.items(), key=lambda x: (-x[1], x[0]))],
    }
    deflection = {"queries": turns["total"], "nav_clicks": nav, "share": _share(nav, turns["total"])}
    thumbs["share_up"] = _share(thumbs["up"], thumbs["up"] + thumbs["down"])
    thumbs["notes"] = int(notes)
    by_mode: dict[str, list[int]] = {"ai": [], "index": []}
    for mode, ms in latencies:
        if mode in by_mode and ms is not None:
            by_mode[mode].append(int(ms))
    latency = {
        m: ({"p50": _rank(v, 0.5), "p95": _rank(v, 0.95), "n": len(v)} if v else {"p50": None, "p95": None, "n": 0})
        for m, v in ((m, sorted(v)) for m, v in by_mode.items())
    }
    cost = [
        {
            "feature": r["key"],
            "label": dict(zip(("tr", "en"), FEATURE_LABELS.get(r["key"], (r["key"], r["key"])), strict=True)),
            "tokens": r["tokens"],
            "cost_usd": r["cost_usd"],
            "calls": r["calls"],
        }
        for r in await meter.report(session, "feature", start=since, end=end)
        if r["key"]
    ]
    actions = [{"action": a, **funnel[a]} for a in sorted(funnel)]
    return {
        "days": days,
        "since": since.isoformat(timespec="seconds"),
        "turns": turns,
        "fallback": fallback,
        "deflection": deflection,
        "actions": actions,
        "thumbs": {k: thumbs[k] for k in ("up", "down", "share_up", "reasons", "notes")},
        "latency_ms": latency,
        "cost": cost,
        "misses": [{"query": q, "users": int(u), "count": int(c)} for q, u, c in misses],
        "k_min": K_MIN,
        "tiles": _tiles(days, turns, fallback, deflection, actions, thumbs),
    }


__all__ = [
    "CLIENT_KINDS",
    "FEEDBACK_REASONS",
    "K_MIN",
    "MAX_DAYS",
    "RATE",
    "RATE_PER_MINUTE",
    "TURN_ID",
    "TelemetryError",
    "client_event",
    "feedback",
    "fold_miss",
    "observe_action",
    "record_action",
    "record_query",
    "record_turn",
    "summary",
]
