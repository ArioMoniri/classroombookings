"""AI usage metering, limits and alerts (wave 3 W3-AI; table ``ai_usage``, settings ``ai.limits``).

* :func:`record` writes one ``ai_usage`` row in its **own** session and commits it at once, so a refused call is
  recorded even when the request that caused it rolls back. On SQLite a busy database is not waited for (the
  request's own session may hold the write lock): the row goes to an in-process outbox and is written by the next
  :func:`record` / :func:`flush_outbox`.
* :func:`reserve` checks the limits **before** a call with the estimated tokens / cost of the request and keeps a
  reservation until :func:`settle` (research R-AI-05: reserve, then settle; two calls in flight cannot both pass the
  last 1 % of a budget). Tokens = input + output + cache reads + cache writes.
* Periods are calendar days and months in Europe/Istanbul.
* :func:`check_alerts` sends the soft (``soft_pct``, default 80 %) and hard (100 %) alerts for the org budget and a
  user's limits to the alert recipients (in-app bell + e-mail through :mod:`app.services.notify_dispatch`, at most once
  per period and threshold). The user sees a banner from ``GET /ai/me/usage``.
* Reports: by user / feature / model / provider / day, period totals, recent refusals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway as gw
from app.core.db import get_session_factory
from app.models import User
from app.models.ai_usage import AIUsage
from app.services import notify_dispatch as nd

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Istanbul")
ALERT_EVENT = "ai.usage_alert"

ALERT_LABEL = ("Yapay zekâ kullanım uyarıları", "AI usage alerts")


async def _deliver(session: AsyncSession, user: User, notice: nd.Notice) -> bool:
    """The dispatcher's built-in channels (in-app bell + e-mail outbox) with its at-most-once ledger
    (``notification_deliveries``). ``ai.usage_alert`` is listed in
    :data:`app.services.notify_dispatch.EVENTS` (so it has a label in the preferences screen), but budget alerts
    bypass the per-event switches here: administrators always get them."""
    from app.models import NotificationDelivery

    sent = False
    for adapter in nd.channels():
        if adapter.name not in {"in_app", "email"}:
            continue
        q = select(NotificationDelivery.id).where(
            NotificationDelivery.event_key == notice.key[:160],
            NotificationDelivery.user_id == user.id,
            NotificationDelivery.channel == adapter.name,
        )
        if (await session.execute(q)).first() is not None:
            continue
        if not await adapter.available_for(session, user):
            continue
        try:
            # one savepoint per channel: a failing channel (an outbox schema behind the code, a broken adapter)
            # never takes the other channel's notice down with it
            async with session.begin_nested():
                ledger = NotificationDelivery(
                    event=notice.event, event_key=notice.key[:160], user_id=user.id, channel=adapter.name, status="sent"
                )
                session.add(ledger)
                await session.flush()
                result = await adapter.send(session, user, notice)
                ledger.status, ledger.ref_id, ledger.detail = result.status, result.ref_id, result.detail
                await session.flush()
        except Exception:  # noqa: BLE001 - a broken channel never breaks the call that triggered the alert
            log.exception("ai alert channel %s failed", adapter.name)
            continue
        sent = sent or result.status == "sent"
    await session.flush()
    return sent


# ---------------------------------------------------------------------------------------------- periods


def _local(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(TZ)


def period_bounds(now: datetime | None = None) -> dict[str, tuple[datetime, datetime]]:
    """UTC-naive ``[start, end)`` of today and this month in Europe/Istanbul (rows store naive UTC)."""
    loc = _local(now)
    day0 = loc.replace(hour=0, minute=0, second=0, microsecond=0)
    month0 = day0.replace(day=1)
    next_month = (month0 + timedelta(days=32)).replace(day=1)

    def utc(d: datetime) -> datetime:
        return d.astimezone(UTC).replace(tzinfo=None)

    return {"day": (utc(day0), utc(day0 + timedelta(days=1))), "month": (utc(month0), utc(next_month))}


def month_key(now: datetime | None = None) -> str:
    return _local(now).strftime("%Y-%m")


def day_key(now: datetime | None = None) -> str:
    return _local(now).strftime("%Y-%m-%d")


_TOKENS = AIUsage.input_tokens + AIUsage.output_tokens + AIUsage.cache_read_tokens + AIUsage.cache_write_tokens


# ---------------------------------------------------------------------------------------------- recording

_OUTBOX: list[dict[str, Any]] = []


def _is_sqlite(session: AsyncSession) -> bool:
    try:
        return session.bind.dialect.name == "sqlite"  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        return False


async def _write(rows: list[dict[str, Any]]) -> None:
    async with get_session_factory()() as s:
        if _is_sqlite(s):
            conn = await s.connection()
            await conn.exec_driver_sql("PRAGMA busy_timeout=250")
        try:
            for r in rows:
                s.add(AIUsage(**r))
            await s.commit()
        finally:
            if _is_sqlite(s):
                from app.core.config import get_settings

                try:
                    conn = await s.connection()
                    await conn.exec_driver_sql(f"PRAGMA busy_timeout={int(get_settings().sqlite_busy_timeout_ms)}")
                except Exception:  # noqa: BLE001
                    pass


_OPS_OUTCOME = {"ok": "ok", "provider_error": "error", "refused_by_guardrail": "blocked", "limit_reached": "limited"}


def _ops_metric(fields: dict[str, Any]) -> None:
    """The aggregated Prometheus counters of W3-OPS (``app.core.observability.record_ai_call``; no user label)."""
    try:
        from app.core import observability

        hook = getattr(observability, "record_ai_call", None)
        if hook is None:
            return
        detail = str(fields.get("detail") or "")
        outcome = _OPS_OUTCOME.get(str(fields.get("outcome")), "error")
        if outcome == "error" and "in time" in detail:
            outcome = "timeout"
        hook(
            provider=str(fields.get("provider") or ""),
            model=str(fields.get("model") or ""),
            feature=str(fields.get("feature") or "other"),
            outcome=outcome,
            input_tokens=int(fields.get("input_tokens") or 0),
            output_tokens=int(fields.get("output_tokens") or 0),
            latency_s=(int(fields.get("latency_ms") or 0) / 1000.0),
            cost_usd=float(fields.get("cost_usd") or 0.0),
        )
        refusal = getattr(observability, "record_guard_refusal", None)
        if refusal is not None and fields.get("outcome") == "refused_by_guardrail":
            code = str(fields.get("reason_code") or "")
            refusal(
                "ai_injection"
                if code.startswith("prompt_injection")
                else "ai_scope"
                if code.startswith(("out_of_scope", "model_scope"))
                else "ai_output"
                if code.startswith("output_")
                else "ai_other"
            )
    except Exception:  # noqa: BLE001 - metrics never break a call
        return


def _ops_budget(org: dict[str, Any]) -> None:
    """The org budget ratio for the W3-OPS alerts (scope ``global``; never a user label)."""
    try:
        from app.core import observability

        hook = getattr(observability, "set_ai_budget_ratio", None)
        if hook is not None and org.get("pct") is not None:
            hook("global", float(org["pct"]) / 100.0)
    except Exception:  # noqa: BLE001
        return


async def record(**fields: Any) -> None:
    """Write one usage row (never raises: metering must not break a call) and count it for W3-OPS."""
    _ops_metric(fields)
    fields.setdefault("created_at", datetime.now(UTC).replace(tzinfo=None))
    for key in ("detail", "reason_code", "model", "feature", "provider"):
        if isinstance(fields.get(key), str):
            fields[key] = fields[key][
                : {"detail": 255, "reason_code": 48, "model": 128, "feature": 16, "provider": 24}[key]
            ]
    rows = [*_OUTBOX, fields]
    try:
        await _write(rows)
        _OUTBOX.clear()
    except OperationalError as exc:  # database busy / locked: keep it for the next write
        log.info("ai usage row queued (%s)", type(exc).__name__)
        _OUTBOX.append(fields)
    except Exception:  # noqa: BLE001 - a missing table on an old schema, a closed engine: log, never fail the call
        log.exception("ai usage row could not be written")


async def flush_outbox() -> int:
    if not _OUTBOX:
        return 0
    rows = list(_OUTBOX)
    try:
        await _write(rows)
    except Exception:  # noqa: BLE001
        return 0
    del _OUTBOX[: len(rows)]
    return len(rows)


def pending_outbox() -> list[dict[str, Any]]:
    return list(_OUTBOX)


# ---------------------------------------------------------------------------------------------- reservations


@dataclass
class Reservation:
    id: int
    user_id: int | None
    tokens: int
    cost: float


_RESERVED: dict[int, Reservation] = {}
_NEXT = [0]


def _reserved(user_id: int | None = None) -> tuple[int, float]:
    items = [r for r in _RESERVED.values() if user_id is None or r.user_id == user_id]
    return sum(r.tokens for r in items), sum(r.cost for r in items)


def settle(reservation: Reservation | None) -> None:
    if reservation is not None:
        _RESERVED.pop(reservation.id, None)


def reset_state() -> None:
    """Tests: forget reservations and the outbox."""
    _RESERVED.clear()
    _OUTBOX.clear()


class LimitRefusal(Exception):
    def __init__(self, code: str, scope: str, used: float, limit: float) -> None:
        super().__init__(code)
        self.code, self.scope, self.used, self.limit = code, scope, used, limit


# ---------------------------------------------------------------------------------------------- totals


async def totals(session: AsyncSession, *, user_id: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Tokens / cost / calls today and this month (org-wide, or for ``user_id``), recorded rows + the outbox."""
    b = period_bounds(now)
    out: dict[str, Any] = {}
    for name, (start, end) in b.items():
        q = select(
            func.coalesce(func.sum(_TOKENS), 0), func.coalesce(func.sum(AIUsage.cost_usd), 0.0), func.count(AIUsage.id)
        ).where(AIUsage.created_at >= start, AIUsage.created_at < end)
        if user_id is not None:
            q = q.where(AIUsage.user_id == user_id)
        try:
            tokens, cost, calls = (await session.execute(q)).one()
        except (OperationalError, ProgrammingError):  # an old schema without ai_usage: count nothing, never block
            log.warning("ai_usage table missing; run the migrations (alembic upgrade head)")
            await session.rollback()
            tokens, cost, calls = 0, 0.0, 0
        for r in _OUTBOX:
            if start <= r["created_at"] < end and (user_id is None or r.get("user_id") == user_id):
                tokens += sum(
                    int(r.get(k) or 0)
                    for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
                )
                cost += float(r.get("cost_usd") or 0)
        out[f"{name}_tokens"] = int(tokens)
        out[f"{name}_cost_usd"] = round(float(cost), 6)
        out[f"{name}_calls"] = int(calls)
    return out


def user_limits(limits: dict[str, Any], user: User | None) -> dict[str, int]:
    """Daily / monthly token limit of ``user``: the per-user override, else the role's, else the default (0 = none)."""
    daily = int(limits.get("user_daily_tokens") or 0)
    monthly = int(limits.get("user_monthly_tokens") or 0)
    if user is not None:
        role = (limits.get("roles") or {}).get(str(user.role or "")) or {}
        if role:
            daily = int(role.get("daily", daily) or 0)
            monthly = int(role.get("monthly", monthly) or 0)
        own = (limits.get("users") or {}).get(str(user.id)) or {}
        if own:
            daily = int(own.get("daily", daily) or 0)
            monthly = int(own.get("monthly", monthly) or 0)
    return {"daily": daily, "monthly": monthly}


def org_budget(limits: dict[str, Any], now: datetime | None = None) -> dict[str, float]:
    """This month's org budget including the audited top-ups of this month (0 = no budget)."""
    tokens = int(limits.get("org_monthly_tokens") or 0)
    cost = float(limits.get("org_monthly_cost_usd") or 0)
    key = month_key(now)
    for t in limits.get("topups") or []:
        if t.get("month") == key:
            tokens += int(t.get("tokens") or 0) if tokens else 0
            cost += float(t.get("cost_usd") or 0) if cost else 0
    return {"tokens": tokens, "cost_usd": round(cost, 6)}


async def reserve(
    session: AsyncSession, *, user_id: int | None, est_tokens: int, est_cost: float, now: datetime | None = None
) -> Reservation:
    """Check the org budget and the user's limits with this call's estimate; raises :class:`LimitRefusal`."""
    limits = await gw.get_limits(session)
    budget = org_budget(limits, now)
    org = await totals(session, now=now)
    r_tokens, r_cost = _reserved()
    if budget["tokens"] and org["month_tokens"] + r_tokens + est_tokens > budget["tokens"]:
        raise LimitRefusal("ai_budget_exceeded", "org_tokens", org["month_tokens"], budget["tokens"])
    if budget["cost_usd"] and org["month_cost_usd"] + r_cost + est_cost > budget["cost_usd"]:
        raise LimitRefusal("ai_budget_exceeded", "org_cost", org["month_cost_usd"], budget["cost_usd"])
    if user_id is not None:
        user = await session.get(User, user_id)
        lim = user_limits(limits, user)
        if lim["daily"] or lim["monthly"]:
            mine = await totals(session, user_id=user_id, now=now)
            u_tokens, _ = _reserved(user_id)
            if lim["daily"] and mine["day_tokens"] + u_tokens + est_tokens > lim["daily"]:
                raise LimitRefusal("ai_limit_reached", "user_daily", mine["day_tokens"], lim["daily"])
            if lim["monthly"] and mine["month_tokens"] + u_tokens + est_tokens > lim["monthly"]:
                raise LimitRefusal("ai_limit_reached", "user_monthly", mine["month_tokens"], lim["monthly"])
    _NEXT[0] += 1
    res = Reservation(_NEXT[0], user_id, int(est_tokens), float(est_cost))
    _RESERVED[res.id] = res
    return res


# ---------------------------------------------------------------------------------------------- state / alerts


def _pct(used: float, limit: float) -> float | None:
    return round(100.0 * used / limit, 1) if limit else None


def _state(pct: float | None, soft: int) -> str:
    if pct is None:
        return "none"
    if pct >= 100:
        return "hard"
    if pct >= soft:
        return "soft"
    return "ok"


async def org_state(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    limits = await gw.get_limits(session)
    budget = org_budget(limits, now)
    t = await totals(session, now=now)
    pcts = [
        p
        for p in (_pct(t["month_tokens"], budget["tokens"]), _pct(t["month_cost_usd"], budget["cost_usd"]))
        if p is not None
    ]
    pct = max(pcts) if pcts else None
    return {
        **t,
        "budget_tokens": budget["tokens"],
        "budget_cost_usd": budget["cost_usd"],
        "pct": pct,
        "state": _state(pct, int(limits.get("soft_pct") or 80)),
        "soft_pct": int(limits.get("soft_pct") or 80),
        "month": month_key(now),
    }


async def user_state(session: AsyncSession, user: User, now: datetime | None = None) -> dict[str, Any]:
    limits = await gw.get_limits(session)
    lim = user_limits(limits, user)
    t = await totals(session, user_id=user.id, now=now)
    pd = _pct(t["day_tokens"], lim["daily"])
    pm = _pct(t["month_tokens"], lim["monthly"])
    pcts = [p for p in (pd, pm) if p is not None]
    pct = max(pcts) if pcts else None
    soft = int(limits.get("soft_pct") or 80)
    org = await org_state(session, now)
    state = _state(pct, soft)
    if org["state"] == "hard":
        state = "hard"
    elif org["state"] == "soft" and state in {"ok", "none"}:
        state = "org_soft"
    return {
        **t,
        "daily_limit": lim["daily"],
        "monthly_limit": lim["monthly"],
        "daily_pct": pd,
        "monthly_pct": pm,
        "pct": pct,
        "state": state,
        "soft_pct": soft,
        "org_state": org["state"],
    }


async def _recipients(session: AsyncSession, limits: dict[str, Any]) -> list[User]:
    ids = [int(i) for i in limits.get("alert_recipients") or [] if str(i).isdigit()]
    q = select(User).where(User.is_active.is_(True))
    q = q.where(User.id.in_(ids)) if ids else q.where(User.role == "ADMIN")
    return list((await session.execute(q)).scalars())


def _alert_texts(scope: str, level: str, pct: float, who: str | None, lang: str) -> tuple[str, str]:
    if lang.startswith("en"):
        subject = "AI budget" if scope == "org" else f"AI limit of {who}"
        title = f"{subject}: {pct:.0f} % used" + (" (limit reached)" if level == "hard" else "")
        body = (
            f"{subject} is at {pct:.0f} %. "
            + ("New AI requests are refused until the limit resets or is raised. " if level == "hard" else "")
            + "Details: Administration > AI > Usage."
        )
        return title, body
    subject = "Yapay zekâ bütçesi" if scope == "org" else f"{who} için yapay zekâ sınırı"
    title = f"{subject}: %{pct:.0f} kullanıldı" + (" (sınır doldu)" if level == "hard" else "")
    body = (
        f"{subject} %{pct:.0f} düzeyinde. "
        + ("Sınır yenilenene ya da artırılana kadar yeni yapay zekâ istekleri reddedilir. " if level == "hard" else "")
        + "Ayrıntılar: Yönetim > Yapay zekâ > Kullanım."
    )
    return title, body


async def check_alerts(user_id: int | None, now: datetime | None = None) -> list[str]:
    """Send the threshold alerts that became due (own session; never raises). Returns the notice keys sent."""
    sent: list[str] = []
    try:
        async with get_session_factory()() as s:
            limits = await gw.get_limits(s)
            soft = int(limits.get("soft_pct") or 80)
            due: list[tuple[str, str, float, str | None, str]] = []
            org = await org_state(s, now)
            _ops_budget(org)
            if org["pct"] is not None and org["pct"] >= soft:
                level = "hard" if org["pct"] >= 100 else "soft"
                due.append(("org", level, float(org["pct"]), None, f"ai_usage:org:{org['month']}:{level}"))
            if user_id is not None:
                user = await s.get(User, user_id)
                if user is not None:
                    st = await user_state(s, user, now)
                    if st["pct"] is not None and st["pct"] >= soft:
                        level = "hard" if st["pct"] >= 100 else "soft"
                        period = day_key(now) if (st["daily_pct"] or 0) >= (st["monthly_pct"] or 0) else month_key(now)
                        label = user.full_name or user.email or f"#{user.id}"
                        due.append(
                            ("user", level, float(st["pct"]), label, f"ai_usage:user:{user.id}:{period}:{level}")
                        )
            if not due:
                return sent
            recipients = await _recipients(s, limits)
            for scope, level, pct, who, key in due:
                for r in recipients:
                    title, body = _alert_texts(scope, level, pct, who, r.language or "tr")
                    notice = nd.Notice(
                        event=ALERT_EVENT,
                        key=key,
                        title=title,
                        body=body,
                        link="/admin/ai?tab=usage",
                        data={"scope": scope, "level": level, "pct": pct},
                    )
                    if await _deliver(s, r, notice):
                        sent.append(key)
            await s.commit()
    except Exception:  # noqa: BLE001 - an alert must never break the call that triggered it
        log.exception("ai usage alerts failed")
    return sent


# ---------------------------------------------------------------------------------------------- reports

GROUPS = {"user", "feature", "model", "provider", "day", "outcome"}


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    b = period_bounds()
    s, e = start or b["month"][0], end or b["month"][1]
    return s.replace(tzinfo=None) if s.tzinfo else s, e.replace(tzinfo=None) if e.tzinfo else e


async def report(
    session: AsyncSession,
    group: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    q: str | None = None,
    limit: int = 500,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Usage grouped by ``group`` within ``[start, end)`` (default: this month)."""
    if group not in GROUPS:
        raise ValueError(f"unknown group {group!r}")
    s, e = _range(start, end)
    if group == "day":
        return await _report_days(session, s, e)
    key = AIUsage.user_id if group == "user" else getattr(AIUsage, group)
    stmt = (
        select(
            key.label("key"),
            func.count(AIUsage.id).label("calls"),
            func.coalesce(func.sum(AIUsage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AIUsage.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AIUsage.cache_read_tokens + AIUsage.cache_write_tokens), 0).label("cache_tokens"),
            func.coalesce(func.sum(_TOKENS), 0).label("tokens"),
            func.coalesce(func.sum(AIUsage.cost_usd), 0.0).label("cost_usd"),
            func.coalesce(func.sum(AIUsage.latency_ms), 0).label("latency_ms_sum"),
            func.coalesce(func.sum(case((AIUsage.outcome != "ok", 1), else_=0)), 0).label("refused"),
        )
        .where(AIUsage.created_at >= s, AIUsage.created_at < e)
        .group_by(key)
    )
    if user_id is not None:
        stmt = stmt.where(AIUsage.user_id == user_id)
    if group == "user" and q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.join(User, User.id == AIUsage.user_id).where(
            or_(func.lower(User.email).like(like), func.lower(func.coalesce(User.full_name, "")).like(like))
        )
    rows = (await session.execute(stmt.order_by(func.coalesce(func.sum(_TOKENS), 0).desc()).limit(limit))).all()
    out: list[dict[str, Any]] = []
    users: dict[int, User] = {}
    if group == "user":
        ids = [r.key for r in rows if r.key is not None]
        if ids:
            users = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars()}
    limits = await gw.get_limits(session) if group == "user" else {}
    for r in rows:
        item: dict[str, Any] = {
            "key": r.key if r.key is not None else None,
            "calls": int(r.calls),
            "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens),
            "cache_tokens": int(r.cache_tokens),
            "tokens": int(r.tokens),
            "cost_usd": round(float(r.cost_usd), 6),
            "avg_latency_ms": int(r.latency_ms_sum / r.calls) if r.calls else 0,
            "refused": int(r.refused or 0),
        }
        if group == "user":
            u = users.get(r.key) if r.key is not None else None
            item["label"] = (u.full_name or u.email) if u else None
            item["email"] = u.email if u else None
            item["role"] = u.role if u else None
            item["limits"] = user_limits(limits, u) if u else None
        out.append(item)
    return out


async def _report_days(session: AsyncSession, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Per local (Europe/Istanbul) day, every day of the range present (0 for a quiet day)."""
    rows = (
        await session.execute(
            select(
                AIUsage.created_at, _TOKENS.label("tokens"), AIUsage.cost_usd, AIUsage.outcome, AIUsage.feature
            ).where(AIUsage.created_at >= start, AIUsage.created_at < end)
        )
    ).all()
    days: dict[str, dict[str, Any]] = {}
    d = _local(start.replace(tzinfo=UTC)).date()
    last = _local(end.replace(tzinfo=UTC) - timedelta(seconds=1)).date()
    while d <= last and len(days) < 400:
        days[d.isoformat()] = {
            "key": d.isoformat(),
            "calls": 0,
            "tokens": 0,
            "cost_usd": 0.0,
            "refused": 0,
            "features": {},
        }
        d += timedelta(days=1)
    for created, tokens, cost, outcome, feature in rows:
        k = _local(created.replace(tzinfo=UTC)).date().isoformat()
        item = days.setdefault(k, {"key": k, "calls": 0, "tokens": 0, "cost_usd": 0.0, "refused": 0, "features": {}})
        item["features"][feature] = item["features"].get(feature, 0) + int(tokens or 0)
        item["calls"] += 1
        item["tokens"] += int(tokens or 0)
        item["cost_usd"] = round(item["cost_usd"] + float(cost or 0), 6)
        item["refused"] += int(outcome != "ok")
    return [days[k] for k in sorted(days)]


async def refusals(session: AsyncSession, *, limit: int = 100) -> list[dict[str, Any]]:
    stmt = (
        select(AIUsage, User)
        .outerjoin(User, User.id == AIUsage.user_id)
        .where(AIUsage.outcome != "ok")
        .order_by(AIUsage.created_at.desc(), AIUsage.id.desc())
        .limit(limit)
    )
    out = []
    for row, user in (await session.execute(stmt)).all():
        out.append(
            {
                "id": row.id,
                "at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
                "user_id": row.user_id,
                "user_label": (user.full_name or user.email) if user else None,
                "feature": row.feature,
                "provider": row.provider,
                "model": row.model,
                "outcome": row.outcome,
                "reason_code": row.reason_code,
                "detail": row.detail,
                "prompt_chars": row.prompt_chars,
            }
        )
    return out


__all__ = [
    "ALERT_EVENT",
    "GROUPS",
    "LimitRefusal",
    "Reservation",
    "check_alerts",
    "day_key",
    "flush_outbox",
    "month_key",
    "org_budget",
    "org_state",
    "pending_outbox",
    "period_bounds",
    "record",
    "refusals",
    "report",
    "reserve",
    "reset_state",
    "settle",
    "totals",
    "user_limits",
    "user_state",
]
