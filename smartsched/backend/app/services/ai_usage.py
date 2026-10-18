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
* Voice (VO-02): a speech-to-text call is a row with ``modality=audio_in`` and ``audio_ms``. :func:`reserve_audio`
  checks the org cost budget, the org's monthly audio seconds and the person's daily / monthly audio seconds
  (``user_daily_audio_s`` 600, ``user_monthly_audio_s`` 6000 by default; ``roles`` / ``users`` overrides with
  ``audio_daily`` / ``audio_monthly``); the reports carry ``audio_minutes``.
* Row-level security (docs/SECURITY.md §4, R12): ``ai_usage`` rows are owner-scoped for a teacher on PostgreSQL. The
  org-wide aggregates (the budget check in :func:`reserve`, the budget ratio of :func:`org_state`, the admin reports
  and refusals) are deliberate cross-user reads and run inside ``rls.system_scope``; a per-user total stays scoped.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, delete, func, or_, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway as gw
from app.core import rls
from app.core.db import get_session_factory
from app.models import User
from app.models.ai_usage import AIReservation, AIUsage
from app.models.catalog import Program
from app.services import notify_dispatch as nd

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Istanbul")
ALERT_EVENT = "ai.usage_alert"

ALERT_LABEL = ("Yapay zekâ kullanım uyarıları", "AI usage alerts")


async def _deliver(session: AsyncSession, user: User, notice: nd.Notice) -> bool:
    """The dispatcher's built-in channels (in-app bell + e-mail outbox) with its at-most-once ledger
    (``notification_deliveries``). Administrators' budget alerts bypass the
    per-event switches here (always-on); the person's own notice goes through
    :func:`app.services.notify_dispatch.dispatch` instead (:func:`_notify_self`), where their switches apply."""
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
            units: dict[int, tuple[int | None, int | None]] = {}
            for r in rows:
                uid = r.get("user_id")
                if uid is not None and "faculty_id" not in r:  # the unit snapshot at record time (HB-10)
                    if uid not in units:
                        units[uid] = await units_of(s, int(uid))
                    r["department_id"], r["faculty_id"] = units[uid]
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

#: a call's reservation outlives its timeout by this much before other workers ignore it (a crashed worker)
RESERVATION_GRACE_S = 60
#: kept per-minute rows are swept after this long
RATE_KEEP_S = 120
_LOCK_KEY = "smartsched_ai_budget"


@dataclass
class Reservation:
    #: the ``ai_reservations`` row id (``0`` = a process-local fallback reservation, old schema)
    id: int
    user_id: int | None
    tokens: int
    cost: float
    audio_ms: int = 0
    local: bool = False


#: the fallback when ``ai_reservations`` does not exist yet (a schema behind the code): the old in-process ledger
_RESERVED: dict[int, Reservation] = {}
_NEXT = [0]
#: row ids this worker settled whose DELETE has not run yet: excluded from every count at once
_PENDING: set[int] = set()
_TASKS: set[asyncio.Task[None]] = set()
#: tests: rows created before the last :func:`reset_state` are not counted (per-minute rows: also before
#: :func:`reset_rate_window`)
_RESET_AT = [datetime.min]
_RATE_RESET_AT = [datetime.min]
#: one asyncio lock per engine (a worker); PostgreSQL's advisory lock serialises the workers
_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def utc_naive(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now


def _local_reserved(user_id: int | None = None) -> tuple[int, float, int]:
    items = [r for r in _RESERVED.values() if user_id is None or r.user_id == user_id]
    return sum(r.tokens for r in items), sum(r.cost for r in items), sum(r.audio_ms for r in items)


def _engine_key(session: AsyncSession) -> int:
    try:
        return id(session.bind)
    except Exception:  # noqa: BLE001
        return 0


@asynccontextmanager
async def _budget_lock(session: AsyncSession) -> AsyncIterator[None]:
    """Serialise the check-then-insert of every reservation: an asyncio lock for this worker's coroutines and, on
    PostgreSQL, ``pg_advisory_xact_lock`` for every worker (held until the caller's commit / rollback)."""
    key = (id(asyncio.get_running_loop()), _engine_key(session))
    lock = _LOCKS.get(key)
    if lock is None:
        if len(_LOCKS) > 32:
            _LOCKS.clear()
        lock = _LOCKS[key] = asyncio.Lock()
    async with lock:
        if not _is_sqlite(session):
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _LOCK_KEY})
        yield


async def _sweep(session: AsyncSession, moment: datetime) -> set[int]:
    """Delete this worker's settled rows, expired calls and old per-minute rows (inside the budget lock). Returns
    the settled ids it deleted; the caller forgets them only after its commit."""
    done = set(_PENDING)
    cond = or_(
        (AIReservation.kind == "call") & (AIReservation.expires_at <= moment),
        (AIReservation.kind == "rate") & (AIReservation.created_at < moment - timedelta(seconds=RATE_KEEP_S)),
    )
    if done:
        cond = or_(cond, AIReservation.id.in_(done))
    await session.execute(delete(AIReservation).where(cond))
    return done


def _live(moment: datetime, kind: str = "call") -> list[Any]:
    since = max(_RESET_AT[0], _RATE_RESET_AT[0]) if kind == "rate" else _RESET_AT[0]
    conds: list[Any] = [AIReservation.kind == kind, AIReservation.created_at >= since]
    if kind == "call":
        conds.append(AIReservation.expires_at > moment)
    if _PENDING:
        conds.append(AIReservation.id.not_in(set(_PENDING)))
    return conds


async def _held(session: AsyncSession, moment: datetime, *where: Any) -> tuple[int, float, int, int]:
    """``(tokens, cost, audio_ms, rows)`` of the open call reservations matching ``where`` (every worker's)."""
    q = select(
        func.coalesce(func.sum(AIReservation.tokens), 0),
        func.coalesce(func.sum(AIReservation.cost_usd), 0.0),
        func.coalesce(func.sum(AIReservation.audio_ms), 0),
        func.count(AIReservation.id),
    ).where(*_live(moment), *where)
    tokens, cost, audio_ms, rows = (await session.execute(q)).one()
    return int(tokens), float(cost), int(audio_ms), int(rows)


async def _delete_pending() -> None:
    if not _PENDING:
        return
    ids = set(_PENDING)
    try:
        async with get_session_factory()() as s:
            await s.execute(delete(AIReservation).where(AIReservation.id.in_(ids)))
            await s.commit()
        _PENDING.difference_update(ids)
    except Exception:  # noqa: BLE001 - the next reserve sweeps them; never break the call that settles
        log.debug("ai reservation release deferred", exc_info=True)


def settle(reservation: Reservation | None) -> None:
    """Release a reservation. Synchronous for old callers: this worker stops counting it at once and the row is
    deleted in the background (``await`` :func:`release` to wait for the DELETE)."""
    if reservation is None:
        return
    if reservation.local:
        _RESERVED.pop(reservation.id, None)
        return
    _PENDING.add(reservation.id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop: the next reserve sweeps it
    task = loop.create_task(_delete_pending())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def release(reservation: Reservation | None) -> None:
    """:func:`settle` and wait until the row is gone (the gateway pipeline's path)."""
    settle(reservation)
    if reservation is not None and not reservation.local:
        await _delete_pending()


def forget_local_state() -> None:
    """Drop this process's in-memory reservation state (tests: what another worker would see)."""
    _RESERVED.clear()
    _LOCKS.clear()


def reset_rate_window() -> None:
    """Tests (``pipeline.reset_state``): earlier per-minute rows no longer count."""
    _RATE_RESET_AT[0] = utc_naive()


def reset_state() -> None:
    """Tests: forget reservations, per-minute rows and the outbox of earlier tests."""
    _RESERVED.clear()
    _OUTBOX.clear()
    _PENDING.clear()
    _LOCKS.clear()
    _RESET_AT[0] = utc_naive()


class LimitRefusal(Exception):
    def __init__(self, code: str, scope: str, used: float, limit: float) -> None:
        super().__init__(code)
        self.code, self.scope, self.used, self.limit = code, scope, used, limit


_MISSING = (OperationalError, ProgrammingError)


async def rate_hit(user_id: int | None, *, per_minute: int, now: datetime | None = None) -> bool:
    """Count one request of ``user_id`` against ``per_minute`` over every worker (``ai_reservations`` rows of kind
    ``rate`` in the last 60 s). ``False`` = over the limit (not counted). Own session; a schema without the table
    falls back to allowing the call (the per-call checks still run)."""
    if user_id is None or per_minute <= 0:
        return True
    moment = utc_naive(now)
    try:
        async with get_session_factory()() as s:
            async with _budget_lock(s):
                q = select(func.count(AIReservation.id)).where(
                    *_live(moment, "rate"),
                    AIReservation.user_id == user_id,
                    AIReservation.created_at > moment - timedelta(seconds=60),
                )
                if int((await s.execute(q)).scalar_one()) >= per_minute:
                    await s.rollback()
                    return False
                s.add(
                    AIReservation(
                        kind="rate",
                        user_id=user_id,
                        created_at=moment,
                        expires_at=moment + timedelta(seconds=RATE_KEEP_S),
                    )
                )
                await s.commit()
    except _MISSING:
        log.warning("ai_reservations table missing; run the migrations (alembic upgrade head)")
    return True


# ---------------------------------------------------------------------------------------------- totals


async def totals(session: AsyncSession, *, user_id: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Tokens / cost / calls today and this month (org-wide, or for ``user_id``), recorded rows + the outbox."""
    b = period_bounds(now)
    out: dict[str, Any] = {}
    for name, (start, end) in b.items():
        q = select(
            func.coalesce(func.sum(_TOKENS), 0),
            func.coalesce(func.sum(AIUsage.cost_usd), 0.0),
            func.count(AIUsage.id),
            func.coalesce(func.sum(AIUsage.audio_ms), 0),
        ).where(AIUsage.created_at >= start, AIUsage.created_at < end)
        if user_id is not None:
            q = q.where(AIUsage.user_id == user_id)
        try:
            if user_id is None:  # the org's total: everyone's rows, also inside a teacher's request (RLS)
                async with rls.system_scope(session):
                    tokens, cost, calls, audio_ms = (await session.execute(q)).one()
            else:
                tokens, cost, calls, audio_ms = (await session.execute(q)).one()
        except (OperationalError, ProgrammingError):  # an old schema without ai_usage: count nothing, never block
            log.warning("ai_usage table missing; run the migrations (alembic upgrade head)")
            await session.rollback()
            tokens, cost, calls, audio_ms = 0, 0.0, 0, 0
        for r in _OUTBOX:
            if start <= r["created_at"] < end and (user_id is None or r.get("user_id") == user_id):
                tokens += sum(
                    int(r.get(k) or 0)
                    for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
                )
                cost += float(r.get("cost_usd") or 0)
                audio_ms += int(r.get("audio_ms") or 0)
        out[f"{name}_tokens"] = int(tokens)
        out[f"{name}_cost_usd"] = round(float(cost), 6)
        out[f"{name}_calls"] = int(calls)
        out[f"{name}_audio_ms"] = int(audio_ms)
    return out


def _role_entry(limits: dict[str, Any], user: User | None) -> dict[str, Any]:
    """The role's limits: keyed by ``role_id`` first (every custom role its own), else by the role code."""
    if user is None:
        return {}
    roles = limits.get("roles") or {}
    for key in (str(user.role_id) if user.role_id is not None else None, str(user.role or "")):
        if key and isinstance(roles.get(key), dict):
            return dict(roles[key])
    return {}


def user_limits(limits: dict[str, Any], user: User | None) -> dict[str, int]:
    """Daily / monthly token limit of ``user``: the per-user override, else the role's (by ``role_id``, then the
    role code), else the default (0 = none)."""
    daily = int(limits.get("user_daily_tokens") or 0)
    monthly = int(limits.get("user_monthly_tokens") or 0)
    if user is not None:
        role = _role_entry(limits, user)
        if role:
            daily = int(role.get("daily", daily) or 0)
            monthly = int(role.get("monthly", monthly) or 0)
        own = (limits.get("users") or {}).get(str(user.id)) or {}
        if own:
            daily = int(own.get("daily", daily) or 0)
            monthly = int(own.get("monthly", monthly) or 0)
    return {"daily": daily, "monthly": monthly}


def user_audio_limits(limits: dict[str, Any], user: User | None) -> dict[str, int]:
    """Daily / monthly audio seconds of ``user``: the per-user override, else the role's, else the default
    (0 = no limit)."""
    daily = int(limits.get("user_daily_audio_s") or 0)
    monthly = int(limits.get("user_monthly_audio_s") or 0)
    if user is not None:
        role = _role_entry(limits, user)
        person = (limits.get("users") or {}).get(str(user.id))
        for own in (role, person):
            if isinstance(own, dict):
                daily = int(own.get("audio_daily", daily) or 0)
                monthly = int(own.get("audio_monthly", monthly) or 0)
    return {"daily_s": daily, "monthly_s": monthly}


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


async def units_of(session: AsyncSession, user_id: int | None) -> tuple[int | None, int | None]:
    """``(department_id, faculty_id)`` of a person now: ``User.department_id`` (a programme) and its faculty."""
    if user_id is None:
        return None, None
    row = (
        await session.execute(
            select(User.department_id, Program.faculty_id)
            .outerjoin(Program, Program.id == User.department_id)
            .where(User.id == user_id)
        )
    ).first()
    return (row[0], row[1]) if row is not None else (None, None)


async def unit_totals(session: AsyncSession, *where: Any, now: datetime | None = None) -> tuple[int, float]:
    """This month's tokens / cost of the rows matching ``where`` (everyone's: a cross-user aggregate)."""
    start, end = period_bounds(now)["month"]
    q = select(func.coalesce(func.sum(_TOKENS), 0), func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).where(
        AIUsage.created_at >= start, AIUsage.created_at < end, *where
    )
    async with rls.system_scope(session):
        tokens, cost = (await session.execute(q)).one()
    for r in _OUTBOX:  # rows not written yet (a busy SQLite): counted for the org level only
        if not where and start <= r["created_at"] < end:
            tokens += sum(int(r.get(k) or 0) for k in ("input_tokens", "output_tokens"))
            cost += float(r.get("cost_usd") or 0)
    return int(tokens), float(cost)


def _cap(entry: Any) -> tuple[int, float]:
    if not isinstance(entry, dict):
        return 0, 0.0
    return int(entry.get("monthly_tokens") or 0), float(entry.get("monthly_cost_usd") or 0)


async def _check_unit(
    session: AsyncSession,
    moment: datetime,
    entry: Any,
    usage_where: list[Any],
    held_where: list[Any],
    est_tokens: int,
    est_cost: float,
    code: str,
    scope: str,
    now: datetime | None,
) -> None:
    cap_tokens, cap_cost = _cap(entry)
    if not cap_tokens and not cap_cost:
        return
    used_tokens, used_cost = await unit_totals(session, *usage_where, now=now)
    h_tokens, h_cost, _, _ = await _held(session, moment, *held_where)
    if cap_tokens and used_tokens + h_tokens + est_tokens > cap_tokens:
        raise LimitRefusal(code, scope, used_tokens, cap_tokens)
    if cap_cost and used_cost + h_cost + est_cost > cap_cost:
        raise LimitRefusal(code, scope, round(used_cost, 6), cap_cost)


async def reserve(
    session: AsyncSession,
    *,
    user_id: int | None,
    est_tokens: int,
    est_cost: float,
    now: datetime | None = None,
    feature: str | None = None,
    max_concurrent: int = 0,
    timeout_s: float = 300,
) -> Reservation:
    """Check the quota chain with this call's estimate and hold it until :func:`settle` / :func:`release`;
    raises :class:`LimitRefusal`. Commits ``session`` (use a session of its own).

    Order (HB-10): the person's open calls (``max_concurrent``) → org tokens / cost → the feature's cap → the
    faculty (or ``unassigned``) → the department → the role (by ``role_id``, then the code) and the person's own
    daily / monthly limit. A level without a configured cap is skipped, so nothing configured means the old
    behaviour. In-flight reservations of every worker count (``ai_reservations``), under one lock."""
    moment = utc_naive(now)
    limits = await gw.get_limits(session)
    try:
        async with _budget_lock(session):
            done = await _sweep(session, moment)
            try:
                res = await _reserve_locked(
                    session, limits, moment, user_id, est_tokens, est_cost, now, feature, max_concurrent, timeout_s
                )
            finally:  # a refusal inserted nothing: commit the sweep either way
                await session.commit()
                _PENDING.difference_update(done)
            return res
    except _MISSING:
        await session.rollback()
        log.warning("ai_reservations table missing; run the migrations (alembic upgrade head)")
        return await _reserve_local(session, limits, user_id, est_tokens, est_cost, now)


async def _reserve_locked(
    session: AsyncSession,
    limits: dict[str, Any],
    moment: datetime,
    user_id: int | None,
    est_tokens: int,
    est_cost: float,
    now: datetime | None,
    feature: str | None,
    max_concurrent: int,
    timeout_s: float,
) -> Reservation:
    if user_id is not None and max_concurrent > 0:
        _, _, _, open_calls = await _held(session, moment, AIReservation.user_id == user_id)
        if open_calls >= max_concurrent:
            raise LimitRefusal("too_many_concurrent", "concurrent", open_calls, max_concurrent)
    budget = org_budget(limits, now)
    org = await totals(session, now=now)
    r_tokens, r_cost, _, _ = await _held(session, moment)
    if budget["tokens"] and org["month_tokens"] + r_tokens + est_tokens > budget["tokens"]:
        raise LimitRefusal("ai_budget_exceeded", "org_tokens", org["month_tokens"], budget["tokens"])
    if budget["cost_usd"] and org["month_cost_usd"] + r_cost + est_cost > budget["cost_usd"]:
        raise LimitRefusal("ai_budget_exceeded", "org_cost", org["month_cost_usd"], budget["cost_usd"])
    if feature:
        await _check_unit(
            session, moment, (limits.get("features") or {}).get(feature), [AIUsage.feature == feature],
            [AIReservation.feature == feature], est_tokens, est_cost, "ai_feature_limit_reached",
            "feature_monthly", now,
        )  # fmt: skip
    user = await session.get(User, user_id) if user_id is not None else None
    department_id, faculty_id = await units_of(session, user_id) if user is not None else (None, None)
    if user is not None:
        if faculty_id is not None:
            await _check_unit(
                session, moment, (limits.get("faculties") or {}).get(str(faculty_id)),
                [AIUsage.faculty_id == faculty_id], [AIReservation.faculty_id == faculty_id], est_tokens, est_cost,
                "ai_faculty_limit_reached", "faculty_monthly", now,
            )  # fmt: skip
        else:
            await _check_unit(
                session, moment, limits.get("unassigned"),
                [AIUsage.user_id.is_not(None), AIUsage.faculty_id.is_(None)],
                [AIReservation.user_id.is_not(None), AIReservation.faculty_id.is_(None)], est_tokens, est_cost,
                "ai_unit_limit_reached", "unassigned_monthly", now,
            )  # fmt: skip
        if department_id is not None:
            await _check_unit(
                session, moment, (limits.get("departments") or {}).get(str(department_id)),
                [AIUsage.department_id == department_id], [AIReservation.department_id == department_id],
                est_tokens, est_cost, "ai_department_limit_reached", "department_monthly", now,
            )  # fmt: skip
        lim = user_limits(limits, user)
        if lim["daily"] or lim["monthly"]:
            mine = await totals(session, user_id=user_id, now=now)
            u_tokens, _, _, _ = await _held(session, moment, AIReservation.user_id == user_id)
            if lim["daily"] and mine["day_tokens"] + u_tokens + est_tokens > lim["daily"]:
                raise LimitRefusal("ai_limit_reached", "user_daily", mine["day_tokens"], lim["daily"])
            if lim["monthly"] and mine["month_tokens"] + u_tokens + est_tokens > lim["monthly"]:
                raise LimitRefusal("ai_limit_reached", "user_monthly", mine["month_tokens"], lim["monthly"])
    row = AIReservation(
        kind="call",
        user_id=user_id,
        feature=(feature or None) and str(feature)[:16],
        role_key=(str(user.role_id) if user is not None and user.role_id is not None else None),
        faculty_id=faculty_id,
        department_id=department_id,
        tokens=int(est_tokens),
        cost_usd=float(est_cost),
        created_at=moment,
        expires_at=moment + timedelta(seconds=float(timeout_s) + RESERVATION_GRACE_S),
    )
    session.add(row)
    await session.flush()
    return Reservation(int(row.id), user_id, int(est_tokens), float(est_cost))


async def _reserve_local(
    session: AsyncSession,
    limits: dict[str, Any],
    user_id: int | None,
    est_tokens: int,
    est_cost: float,
    now: datetime | None,
) -> Reservation:
    """The pre-0046 in-process ledger (org + person only), for a schema behind the code."""
    budget = org_budget(limits, now)
    org = await totals(session, now=now)
    r_tokens, r_cost, _ = _local_reserved()
    if budget["tokens"] and org["month_tokens"] + r_tokens + est_tokens > budget["tokens"]:
        raise LimitRefusal("ai_budget_exceeded", "org_tokens", org["month_tokens"], budget["tokens"])
    if budget["cost_usd"] and org["month_cost_usd"] + r_cost + est_cost > budget["cost_usd"]:
        raise LimitRefusal("ai_budget_exceeded", "org_cost", org["month_cost_usd"], budget["cost_usd"])
    if user_id is not None:
        lim = user_limits(limits, await session.get(User, user_id))
        if lim["daily"] or lim["monthly"]:
            mine = await totals(session, user_id=user_id, now=now)
            u_tokens, _, _ = _local_reserved(user_id)
            if lim["daily"] and mine["day_tokens"] + u_tokens + est_tokens > lim["daily"]:
                raise LimitRefusal("ai_limit_reached", "user_daily", mine["day_tokens"], lim["daily"])
            if lim["monthly"] and mine["month_tokens"] + u_tokens + est_tokens > lim["monthly"]:
                raise LimitRefusal("ai_limit_reached", "user_monthly", mine["month_tokens"], lim["monthly"])
    _NEXT[0] += 1
    res = Reservation(_NEXT[0], user_id, int(est_tokens), float(est_cost), local=True)
    _RESERVED[res.id] = res
    return res


async def reserve_audio(
    session: AsyncSession, *, user_id: int | None, est_audio_s: float, est_cost: float, now: datetime | None = None
) -> Reservation:
    """Before a speech-to-text call: the org cost budget (voice counts toward it), the org's monthly audio seconds
    and the person's daily / monthly audio seconds, with this clip's estimate; raises :class:`LimitRefusal`
    (``ai_budget_exceeded`` | ``ai_voice_limit_reached``; ``used`` / ``limit`` in seconds for audio). Held in
    ``ai_reservations`` like a text call, so every worker sees it."""
    moment = utc_naive(now)
    limits = await gw.get_limits(session)
    est_ms = int(round(est_audio_s * 1000))
    try:
        async with _budget_lock(session):
            done = await _sweep(session, moment)
            try:
                _, r_cost, r_ms, _ = await _held(session, moment)
                mine_ms = (await _held(session, moment, AIReservation.user_id == user_id))[2] if user_id else 0
                await _check_audio(session, limits, user_id, est_ms, est_cost, r_cost, r_ms, mine_ms, now)
                row = AIReservation(
                    kind="call",
                    user_id=user_id,
                    feature="voice_stt",
                    cost_usd=float(est_cost),
                    audio_ms=est_ms,
                    created_at=moment,
                    expires_at=moment + timedelta(seconds=300 + RESERVATION_GRACE_S),
                )
                session.add(row)
                await session.flush()
                res = Reservation(int(row.id), user_id, 0, float(est_cost), est_ms)
            finally:  # a refusal inserted nothing: commit the sweep either way
                await session.commit()
                _PENDING.difference_update(done)
            return res
    except _MISSING:
        await session.rollback()
        _, r_cost, r_ms = _local_reserved()
        await _check_audio(session, limits, user_id, est_ms, est_cost, r_cost, r_ms, _local_reserved(user_id)[2], now)
        _NEXT[0] += 1
        res = Reservation(_NEXT[0], user_id, 0, float(est_cost), est_ms, local=True)
        _RESERVED[res.id] = res
        return res


async def _check_audio(
    session: AsyncSession,
    limits: dict[str, Any],
    user_id: int | None,
    est_ms: int,
    est_cost: float,
    r_cost: float,
    r_ms: int,
    mine_ms: int,
    now: datetime | None,
) -> None:
    budget = org_budget(limits, now)
    org = await totals(session, now=now)
    if budget["cost_usd"] and org["month_cost_usd"] + r_cost + est_cost > budget["cost_usd"]:
        raise LimitRefusal("ai_budget_exceeded", "org_cost", org["month_cost_usd"], budget["cost_usd"])
    org_audio = int(limits.get("org_monthly_audio_s") or 0)
    if org_audio and org["month_audio_ms"] + r_ms + est_ms > org_audio * 1000:
        raise LimitRefusal("ai_voice_limit_reached", "org_audio", org["month_audio_ms"] / 1000, org_audio)
    if user_id is not None:
        lim = user_audio_limits(limits, await session.get(User, user_id))
        if lim["daily_s"] or lim["monthly_s"]:
            mine = await totals(session, user_id=user_id, now=now)
            if lim["daily_s"] and mine["day_audio_ms"] + mine_ms + est_ms > lim["daily_s"] * 1000:
                raise LimitRefusal("ai_voice_limit_reached", "user_daily", mine["day_audio_ms"] / 1000, lim["daily_s"])
            if lim["monthly_s"] and mine["month_audio_ms"] + mine_ms + est_ms > lim["monthly_s"] * 1000:
                raise LimitRefusal(
                    "ai_voice_limit_reached", "user_monthly", mine["month_audio_ms"] / 1000, lim["monthly_s"]
                )


# ---------------------------------------------------------------------------------------------- allocations

#: keys of one unit allocation in ``ai.limits`` (``faculties`` add ``managers`` and ``show_people``, HB-11)
UNIT_KEYS = ("monthly_tokens", "monthly_cost_usd")


def _issue(code: str, tr: str, en: str, fld: str) -> dict[str, str]:
    return {"code": code, "message_tr": tr, "message_en": en, "field": fld}


async def faculty_of_programs(session: AsyncSession, program_ids: list[int]) -> dict[int, int | None]:
    if not program_ids:
        return {}
    rows = (await session.execute(select(Program.id, Program.faculty_id).where(Program.id.in_(program_ids)))).all()
    return {int(pid): fid for pid, fid in rows}


async def check_allocations(
    session: AsyncSession, limits: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """``(errors, warnings)`` of the unit allocations in ``limits`` (HB-10 / HB-11):

    * a faculty / department id that does not exist → ``unknown_unit``;
    * the departments of a faculty allocate more than the faculty (tokens or cost) → ``department_sum_exceeds_faculty``;
    * the faculties allocate more than the org budget → the warning ``faculty_sum_exceeds_org`` (overbooking is
      allowed: units rarely all reach 100 %), an error when ``strict`` is on."""
    from app.models import Faculty

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    faculties = {k: v for k, v in (limits.get("faculties") or {}).items() if isinstance(v, dict)}
    departments = {k: v for k, v in (limits.get("departments") or {}).items() if isinstance(v, dict)}
    fac_ids = [int(k) for k in faculties if str(k).isdigit()]
    dep_ids = [int(k) for k in departments if str(k).isdigit()]
    known_fac = set((await session.execute(select(Faculty.id).where(Faculty.id.in_(fac_ids)))).scalars())
    dep_fac = await faculty_of_programs(session, dep_ids)
    for k in faculties:
        if not str(k).isdigit() or int(k) not in known_fac:
            errors.append(_issue("unknown_unit", "Böyle bir fakülte yok.", "No such faculty.", f"faculties.{k}"))
    for k in departments:
        if not str(k).isdigit() or int(k) not in dep_fac:
            errors.append(_issue("unknown_unit", "Böyle bir bölüm yok.", "No such department.", f"departments.{k}"))
    if errors:
        return errors, warnings
    for fk, fentry in faculties.items():
        f_tokens, f_cost = _cap(fentry)
        mine = [departments[str(d)] for d in dep_ids if dep_fac.get(d) == int(fk)]
        d_tokens = sum(_cap(d)[0] for d in mine)
        d_cost = sum(_cap(d)[1] for d in mine)
        if (f_tokens and d_tokens > f_tokens) or (f_cost and d_cost > f_cost + 1e-9):
            errors.append(
                _issue(
                    "department_sum_exceeds_faculty",
                    f"Bölümlere dağıtılan pay ({d_tokens} jeton) fakültenin payını ({f_tokens} jeton) aşıyor.",
                    f"The departments' allocations ({d_tokens} tokens) exceed the faculty's ({f_tokens} tokens).",
                    f"faculties.{fk}",
                )
            )
    budget = org_budget(limits)
    s_tokens = sum(_cap(v)[0] for v in faculties.values())
    s_cost = sum(_cap(v)[1] for v in faculties.values())
    if (budget["tokens"] and s_tokens > budget["tokens"]) or (budget["cost_usd"] and s_cost > budget["cost_usd"]):
        issue = _issue(
            "faculty_sum_exceeds_org",
            f"Fakültelere dağıtılan pay ({s_tokens} jeton) kurumun aylık bütçesini ({budget['tokens']} jeton) aşıyor.",
            f"The faculties' allocations ({s_tokens} tokens) exceed the org's monthly budget "
            f"({budget['tokens']} tokens).",
            "faculties",
        )
        (errors if limits.get("strict") else warnings).append(issue)
    return errors, warnings


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
    audio = user_audio_limits(limits, user)
    return {
        **t,
        "day_audio_s": round(t["day_audio_ms"] / 1000),
        "month_audio_s": round(t["month_audio_ms"] / 1000),
        "audio_daily_limit_s": audio["daily_s"],
        "audio_monthly_limit_s": audio["monthly_s"],
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


async def _notify_self(session: AsyncSession, user_id: int, level: str, pct: float, key: str) -> None:
    user = await session.get(User, user_id)
    if user is None:
        return
    if (user.language or "tr").startswith("en"):
        title = f"You used {pct:.0f} % of your AI limit" + (" (limit reached)" if level == "hard" else "")
        body = ("New AI requests are refused until it resets. " if level == "hard" else "") + "Profile > My AI usage."
    else:
        title = f"Yapay zekâ sınırınızın %{pct:.0f} kadarını kullandınız" + (
            " (sınır doldu)" if level == "hard" else ""
        )
        body = (
            "Sınır yenilenene kadar yeni yapay zekâ istekleri reddedilir. " if level == "hard" else ""
        ) + "Profil > Yapay zekâ kullanımım."
    notice = nd.Notice(
        event=ALERT_EVENT,
        key=key,
        title=title,
        body=body,
        link="/profile",
        data={"scope": "self", "level": level, "pct": pct},
    )
    try:
        async with session.begin_nested():
            await nd.dispatch(session, user, notice)
    except Exception:  # noqa: BLE001 - a broken channel never breaks the call that triggered the alert
        log.exception("ai self alert failed")


async def _unit_alerts(
    session: AsyncSession, limits: dict[str, Any], user_id: int, soft: int, now: datetime | None
) -> list[tuple[str, str, float, str | None, str, list[User]]]:
    """The faculty / department thresholds the caller's units crossed this month (HB-10): ``(scope, level, pct,
    unit name, notice key, the faculty's quota managers)``."""
    from app.models import Faculty

    department_id, faculty_id = await units_of(session, user_id)
    out: list[tuple[str, str, float, str | None, str, list[User]]] = []
    fentry = (limits.get("faculties") or {}).get(str(faculty_id)) if faculty_id is not None else None
    manager_ids = [int(i) for i in (fentry or {}).get("managers") or [] if str(i).isdigit()]
    managers = (
        list((await session.execute(select(User).where(User.id.in_(manager_ids), User.is_active.is_(True)))).scalars())
        if manager_ids
        else []
    )
    checks: list[tuple[str, Any, Any, int | None]] = [
        ("faculty", fentry, AIUsage.faculty_id == faculty_id, faculty_id),
        (
            "department",
            (limits.get("departments") or {}).get(str(department_id)) if department_id is not None else None,
            AIUsage.department_id == department_id,
            department_id,
        ),
    ]
    for scope, entry, where, unit_id in checks:
        cap_tokens, cap_cost = _cap(entry)
        if unit_id is None or (not cap_tokens and not cap_cost):
            continue
        tokens, cost = await unit_totals(session, where, now=now)
        pcts = [p for p in (_pct(tokens, cap_tokens), _pct(cost, cap_cost)) if p is not None]
        pct = max(pcts) if pcts else None
        if pct is None or pct < soft:
            continue
        level = "hard" if pct >= 100 else "soft"
        model = Faculty if scope == "faculty" else Program
        name = (await session.execute(select(model.name).where(model.id == unit_id))).scalar_one_or_none()
        out.append((scope, level, float(pct), name, f"ai_usage:{scope}:{unit_id}:{month_key(now)}:{level}", managers))
    return out


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
            unit_due = await _unit_alerts(s, limits, user_id, soft, now) if user_id is not None else []
            if not due and not unit_due:
                return sent
            recipients = await _recipients(s, limits)
            for scope, level, pct, who, key, managers in unit_due:  # faculty / department: managers + admins
                extra = [u for u in managers if u.id not in {r.id for r in recipients}]
                for r in [*recipients, *extra]:
                    title, body = _alert_texts(scope, level, pct, who, r.language or "tr")
                    notice = nd.Notice(
                        event=ALERT_EVENT,
                        key=key,
                        title=title,
                        body=body,
                        link="/admin/ai?tab=limits",
                        data={"scope": scope, "level": level, "pct": pct},
                    )
                    if await _deliver(s, r, notice):
                        sent.append(key)
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
                if scope == "user" and user_id is not None:
                    # the person concerned: their own notice through the dispatcher, so their per-event switches
                    # (Profil > Bildirimler) apply; the administrators' path above stays always-on
                    await _notify_self(s, user_id, level, pct, key)
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
            func.coalesce(func.sum(AIUsage.audio_ms), 0).label("audio_ms"),
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
    async with rls.system_scope(session):  # an admin report (the route checks the right); RLS would hide rows
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
            "audio_minutes": round(int(r.audio_ms or 0) / 60000, 3),
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
    async with rls.system_scope(session):  # org-wide (admin report)
        rows = (
            await session.execute(
                select(
                    AIUsage.created_at,
                    _TOKENS.label("tokens"),
                    AIUsage.cost_usd,
                    AIUsage.outcome,
                    AIUsage.feature,
                    AIUsage.audio_ms,
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
            "audio_minutes": 0.0,
            "features": {},
        }
        d += timedelta(days=1)
    for created, tokens, cost, outcome, feature, audio_ms in rows:
        k = _local(created.replace(tzinfo=UTC)).date().isoformat()
        item = days.setdefault(
            k,
            {"key": k, "calls": 0, "tokens": 0, "cost_usd": 0.0, "refused": 0, "audio_minutes": 0.0, "features": {}},
        )
        item["audio_minutes"] = round(item["audio_minutes"] + int(audio_ms or 0) / 60000, 3)
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
    async with rls.system_scope(session):  # org-wide (admin report)
        found = (await session.execute(stmt)).all()
    out = []
    for row, user in found:
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
    "UNIT_KEYS",
    "check_alerts",
    "check_allocations",
    "faculty_of_programs",
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
    "reserve_audio",
    "release",
    "rate_hit",
    "reset_rate_window",
    "reset_state",
    "settle",
    "forget_local_state",
    "unit_totals",
    "units_of",
    "utc_naive",
    "totals",
    "user_audio_limits",
    "user_limits",
    "user_state",
]
