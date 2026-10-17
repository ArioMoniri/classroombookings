"""Row-level security context for PostgreSQL (wave 3 W3-SEC; alembic 0035_rls_policies, docs/SECURITY.md §4).

Every transaction of a session carries who is asking, as transaction-local settings read by the policies:

* ``app.user_id`` / ``app.role`` / ``app.perms`` (comma list) and ``app.system = off`` for a signed-in user. The
  transaction also runs as the ``NOLOGIN`` role ``smartsched_rls`` (``set_config('role', ...)``), so the policies
  apply even when the application logs in as the table owner or a superuser;
* the **system** context (``app.system = on``, the login role itself) for everything else: workers, the CLI,
  migrations, start-up jobs and unauthenticated routes (token feeds, the public schedule, sign-in). It is the
  default of every session; :func:`bind_user` (called by ``app.api.deps.get_current_user``) narrows a request's
  session to its user, :func:`system_scope` widens one transaction back for a deliberate cross-user step.

The settings are written in SQLAlchemy's ``after_begin`` hook (one ``SELECT set_config(...)`` per transaction) and
are dropped by PostgreSQL at commit / rollback, so a pooled connection never keeps them. On SQLite (tests, dev)
everything here is a no-op. ``SMARTSCHED_RLS=off`` switches the hook off (emergency switch; the policies then let
only the owner and system contexts through).

Fan-out inserts: the app writes a notification (or an AI usage row) for *someone else* in the actor's request (an
approver's decision notifies the requester). PostgreSQL checks ``INSERT ... RETURNING`` against the SELECT policy,
so the single INSERT statement into :data:`FANOUT_INSERT_TABLES` runs with ``app.system = on``; reads, updates and
deletes of those rows stay scoped to the owner.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

#: the NOLOGIN role a signed-in user's transactions run as (created by alembic 0035_rls_policies)
RLS_ROLE = "smartsched_rls"
#: key of the context in ``Session.info``
INFO_KEY = "smartsched.rls"
#: tables the app inserts into on behalf of other people; their single INSERT statement runs as system
FANOUT_INSERT_TABLES = ("inapp_notifications", "ai_usage")
_FANOUT_RX = re.compile(r"^\s*INSERT\s+INTO\s+\"?(" + "|".join(FANOUT_INSERT_TABLES) + r")\"?[\s(]", re.IGNORECASE)

#: ``connection.info`` keys (per pooled DB-API connection)
_PROBE = "smartsched.rls.probe"
_BOUND = "smartsched.rls.bound"


@dataclass(frozen=True)
class RlsContext:
    """Who a transaction acts for. ``system`` = workers, migrations, unauthenticated routes."""

    user_id: int | None = None
    role: str = ""
    perms: frozenset[str] = field(default_factory=frozenset)
    system: bool = True

    def settings(self) -> dict[str, str]:
        """The transaction-local settings the policies read (``app.*``)."""
        return {
            "app.user_id": "" if self.system or self.user_id is None else str(int(self.user_id)),
            "app.role": "" if self.system else _clean(self.role),
            "app.perms": "" if self.system else ",".join(sorted(_clean(p) for p in self.perms if _clean(p))),
            "app.system": "on" if self.system else "off",
        }


SYSTEM = RlsContext()


def _clean(value: str) -> str:
    """Permission / role names never carry a comma or a quote (they are list separators in ``app.perms``)."""
    return re.sub(r"[^A-Za-z0-9_.:\-]", "", value or "")


def enabled() -> bool:
    return os.environ.get("SMARTSCHED_RLS", "on").strip().lower() not in {"off", "0", "false", "no"}


def user_context(user: Any, perms: Iterable[str]) -> RlsContext:
    return RlsContext(user_id=int(user.id), role=str(user.role or ""), perms=frozenset(perms), system=False)


def context_of(session: Session | AsyncSession) -> RlsContext:
    ctx = session.info.get(INFO_KEY)
    return ctx if isinstance(ctx, RlsContext) else SYSTEM


def applies(session: AsyncSession) -> bool:
    """True when the session talks to PostgreSQL and the hook is on (callers skip loading permissions otherwise)."""
    if not enabled():
        return False
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:  # unbound session
        return False


# --------------------------------------------------------------------------------------------------
# applying a context to the current transaction
# --------------------------------------------------------------------------------------------------


def _probe(conn: Connection) -> dict[str, bool]:
    """Once per pooled connection: may the login role switch to :data:`RLS_ROLE`, and is it exempt from the
    policies anyway (superuser, ``BYPASSRLS`` or owner of the tables without ``FORCE``)?"""
    info = conn.info.get(_PROBE)
    if isinstance(info, dict):
        return info
    row = conn.exec_driver_sql(
        "SELECT coalesce(pg_has_role(r.oid, (SELECT oid FROM pg_roles WHERE rolname = %(role)s), 'MEMBER'), false), "
        "r.rolsuper OR r.rolbypassrls OR EXISTS (SELECT 1 FROM pg_class c WHERE c.relname = 'inapp_notifications' "
        "AND c.relowner = r.oid AND NOT c.relforcerowsecurity) "
        "FROM pg_roles r WHERE r.rolname = current_user",
        {"role": RLS_ROLE},
    ).first()
    info = {"can_switch": bool(row and row[0]), "exempt": bool(row and row[1])}
    if info["can_switch"]:  # the role exists from now on: cache; otherwise ask again on the next transaction
        conn.info[_PROBE] = info
    return info


def _apply(conn: Connection, ctx: RlsContext, *, force: bool = False) -> None:
    if conn.dialect.name != "postgresql" or not enabled():
        return
    probe = _probe(conn)
    bound = not ctx.system
    if not bound and not force and probe["exempt"]:
        conn.info[_BOUND] = False
        return  # system context on an exempt login: nothing to set (no round trip)
    params = dict(ctx.settings())
    sets = [f"set_config('{k}', %({k.replace('.', '_')})s, true)" for k in params]
    values = {k.replace(".", "_"): v for k, v in params.items()}
    if probe["can_switch"]:
        sets.append("set_config('role', %(role_name)s, true)")
        values["role_name"] = RLS_ROLE if bound else "none"
    conn.exec_driver_sql("SELECT " + ", ".join(sets), values)
    conn.info[_BOUND] = bound


async def _apply_now(session: AsyncSession, ctx: RlsContext) -> None:
    if session.in_transaction():
        conn = await session.connection()
        await conn.run_sync(lambda c: _apply(c, ctx, force=True))


async def bind_user(session: AsyncSession, user: Any, perms: Iterable[str]) -> RlsContext:
    """Narrow ``session`` (a request's) to ``user``: every later transaction, and the open one, runs under the
    policies as that user. No-op on SQLite."""
    ctx = user_context(user, perms)
    session.info[INFO_KEY] = ctx
    if applies(session):
        await _apply_now(session, ctx)
    return ctx


@asynccontextmanager
async def system_scope(session: AsyncSession) -> AsyncIterator[None]:
    """A deliberate cross-user step inside a user's request (an org-wide aggregate, a sweep): the open transaction
    and those begun inside the block run as system; the user context comes back afterwards."""
    previous = session.info.get(INFO_KEY)
    session.info[INFO_KEY] = SYSTEM
    try:
        if applies(session):
            await _apply_now(session, SYSTEM)
        yield
    finally:
        if previous is None:
            session.info.pop(INFO_KEY, None)
        else:
            session.info[INFO_KEY] = previous
        if applies(session) and isinstance(previous, RlsContext):
            await _apply_now(session, previous)


# --------------------------------------------------------------------------------------------------
# hooks (installed once, from app.core.db)
# --------------------------------------------------------------------------------------------------


def _after_begin(session: Session, _transaction: SessionTransaction, connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    _apply(connection, context_of(session))


def _before_cursor_execute(
    conn: Connection, cursor: Any, statement: str, _params: Any, _context: Any, _executemany: bool
) -> None:
    if conn.info.get(_BOUND) and conn.dialect.name == "postgresql" and _FANOUT_RX.match(statement):
        _side_execute(conn, "SELECT set_config('app.system', 'on', true)")
        conn.info["smartsched.rls.fanout"] = True


def _after_cursor_execute(
    conn: Connection, cursor: Any, _statement: str, _params: Any, _context: Any, _executemany: bool
) -> None:
    if conn.info.pop("smartsched.rls.fanout", False):
        _side_execute(conn, "SELECT set_config('app.system', 'off', true)")


def _side_execute(conn: Connection, sql: str) -> None:
    """Run ``sql`` on its own cursor of the same DB-API connection (the statement's cursor keeps its rows)."""
    cur = conn.connection.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()


def _checkin(_dbapi_conn: Any, record: Any) -> None:
    record.info.pop(_BOUND, None)
    record.info.pop("smartsched.rls.fanout", None)


_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    event.listen(Session, "after_begin", _after_begin)
    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", _after_cursor_execute)
    from sqlalchemy.pool import Pool

    event.listen(Pool, "checkin", _checkin)
    _installed = True


__all__ = [
    "FANOUT_INSERT_TABLES",
    "RLS_ROLE",
    "SYSTEM",
    "RlsContext",
    "applies",
    "bind_user",
    "context_of",
    "enabled",
    "install",
    "system_scope",
    "user_context",
]
