"""Server-side session list (AU-15, coordinator decision 2026-10-18).

Every access token carries a random ``jti`` (``app.core.security.user_token``). The first request with a token records
a :class:`app.models.mfa.UserSession` row (only the SHA-256 of the ``jti``, the browser + OS family and the client
/24); every request checks it: a revoked row answers 401 at once. Recording lazily covers every place that issues a
token (password, second factor, passkey, SSO exchange, reset link, invite) without touching them.

Cost per request: an in-process cache (:data:`TTL` 15 s) answers most checks without the database; a miss is one
indexed read; ``last_seen_at`` is written at most every :data:`SEEN_EVERY`. Writes use a short separate session, so a
read-only route never commits. A revocation clears this process's cache entry and moves ``users.sessions_epoch`` on;
a cache entry is trusted only while the epoch it saw is the user's current one, so another worker (the user row is read
on every request anyway) re-checks at once and the revoked token fails on its very next request, at no extra query.
Tokens without a ``jti`` (issued before AU-15) still pass on the token-version check only. A token carries the epoch
at issue (claim ``se``); one first seen after a later revocation is refused, so "Diğer cihazlardan çıkış yap" also ends
tokens that were issued but had not made a request yet (FIX-A F-AUB-1).
"""

from __future__ import annotations

import hashlib
import ipaddress
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.models import User
from app.models.base import utcnow
from app.models.mfa import UserSession
from app.services import audit

TTL = 15.0
SEEN_EVERY = timedelta(minutes=5)
_lock = threading.Lock()
#: jti hash -> (checked at, monotonic; revoked; session id; last seen written; the user's sessions epoch then)
_cache: dict[str, tuple[float, bool, int, datetime, int]] = {}
STATE_KEY = "au_session_id"


def jti_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def network_of(address: str | None) -> str:
    try:
        ip = ipaddress.ip_address((address or "").strip())
    except ValueError:
        return ""
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def _epoch(user: User) -> int:
    return int(getattr(user, "sessions_epoch", 0) or 0)


def _bump(user: User) -> None:
    """Every worker's cached answers for ``user`` become stale (the caller commits)."""
    user.sessions_epoch = _epoch(user) + 1


def _remember(h: str, revoked: bool, sid: int, seen: datetime, epoch: int) -> None:
    with _lock:
        if len(_cache) > 20_000:
            _cache.clear()
        _cache[h] = (time.monotonic(), revoked, sid, seen, epoch)


def forget(h: str | None = None) -> None:
    with _lock:
        if h is None:
            _cache.clear()
        else:
            _cache.pop(h, None)


def _revoked() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "session revoked")


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


async def check(request: Request, payload: dict[str, Any], user: User) -> int | None:
    """Called by ``get_current_user`` after the token-version check: the session row's id (``None`` for a token
    without ``jti``); 401 when the session was revoked."""
    jti = payload.get("jti")
    if not isinstance(jti, str) or not 8 <= len(jti) <= 128:
        return None
    h = jti_hash(jti)
    now = utcnow()
    with _lock:
        hit = _cache.get(h)
    epoch = _epoch(user)
    if hit is not None and time.monotonic() - hit[0] < TTL and hit[4] == epoch:
        _checked, revoked, sid, seen, _epoch_then = hit
        if revoked:
            raise _revoked()
        request.state.__setattr__(STATE_KEY, sid)
        return sid
    from app.core.db import get_session_factory

    async with get_session_factory()() as s:
        row = (await s.execute(select(UserSession).where(UserSession.jti_hash == h))).scalar_one_or_none()
        if row is None:
            if _issued_before(payload, epoch):
                _remember(h, True, 0, now, epoch)
                raise _revoked()
            row = await _record(s, request, payload, user, h, now)
        elif row.user_id != user.id:  # a jti reused across accounts cannot happen with random ids: refuse
            raise _revoked()
        if row.revoked_at is not None:
            _remember(h, True, row.id, row.last_seen_at, epoch)
            raise _revoked()
        dirty = _better_device(row, request)
        if now - row.last_seen_at >= SEEN_EVERY:
            row.last_seen_at = now
            dirty = True
        if dirty:
            await s.commit()
        sid, seen = row.id, row.last_seen_at
    _remember(h, False, sid, seen, epoch)
    request.state.__setattr__(STATE_KEY, sid)
    return sid


def _better_device(row: UserSession, request: Request) -> bool:
    """AUX12-F03: a token's first request may come from the Next server (Node's user agent, or none), and the row read
    "bilinmeyen tarayıcı, bilinmeyen cihaz" for ever. A later request that names more of the browser and system
    updates the label (only ever towards a better one)."""
    from app.services import mail_senders

    unknown = ("bilinmeyen tarayıcı", "bilinmeyen cihaz")
    have = sum(u in (row.device or "") for u in unknown)
    if not have:
        return False
    label = mail_senders.device_label(request.headers.get("user-agent"), "tr")[:120]
    if sum(u in label for u in unknown) >= have:
        return False
    row.device = label
    return True


def _issued_before(payload: dict[str, Any], epoch: int) -> bool:
    """FIX-A F-AUB-1: a token never seen before, issued before the user's latest revocation (its ``se`` claim is behind
    the user's sessions epoch), has no row the revocation could mark; it is refused on its first request instead.
    A ``jti`` token without the claim (issued before FIX-A) counts as epoch 0."""
    from app.core.security import SESSIONS_EPOCH_CLAIM

    claim = payload.get(SESSIONS_EPOCH_CLAIM, 0)
    if isinstance(claim, bool) or not isinstance(claim, int):
        return True
    return claim < epoch


async def _record(
    s: AsyncSession, request: Request, payload: dict[str, Any], user: User, h: str, now: datetime
) -> UserSession:
    from app.services import mail_senders

    tv = payload.get("tv", 0)
    row = UserSession(
        user_id=user.id,
        jti_hash=h,
        tv=int(tv) if isinstance(tv, int) and not isinstance(tv, bool) else 0,
        created_at=_ts(payload.get("iat")) or now,
        expires_at=_ts(payload.get("exp")) or now + timedelta(hours=12),
        last_seen_at=now,
        device=mail_senders.device_label(request.headers.get("user-agent"), "tr")[:120],
        network=network_of(request.client.host if request.client else None),
    )
    s.add(row)
    try:
        await s.commit()
    except IntegrityError:  # two first requests of one token at the same moment
        await s.rollback()
        got = (await s.execute(select(UserSession).where(UserSession.jti_hash == h))).scalar_one()
        return got
    return row


def current_id(request: Request) -> int | None:
    value = getattr(request.state, STATE_KEY, None)
    return int(value) if isinstance(value, int) else None


async def _open(db: AsyncSession, user: User) -> list[UserSession]:
    now = utcnow()
    q = (
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.tv == int(user.token_version or 0),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc(), UserSession.id.desc())
    )
    return list((await db.execute(q)).scalars())


async def list_own(db: AsyncSession, user: User, current: int | None) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "last_seen_at": r.last_seen_at,
            "expires_at": r.expires_at,
            "device": r.device,
            "network": r.network,
            "current": r.id == current,
        }
        for r in await _open(db, user)
    ]


async def _mark(db: AsyncSession, user: User, rows: list[UserSession], reason: str) -> int:
    now = utcnow()
    if rows:
        _bump(user)
    for r in rows:
        r.revoked_at, r.revoked_reason = now, reason[:32]
        forget(r.jti_hash)
    await db.flush()
    return len(rows)


async def revoke_one(db: AsyncSession, user: User, session_id: int) -> None:
    row = await db.get(UserSession, session_id)
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise HTTPException(
            404,
            {
                "code": "not_found",
                "message": "session not found",
                "message_en": "Session not found.",
                "message_tr": "Oturum bulunamadı.",
            },
        )
    await _mark(db, user, [row], "self")
    await audit.record(db, "auth.session_revoked", "user", user.id, after={"session_id": row.id, "device": row.device})


async def revoke_others(db: AsyncSession, user: User, current: int | None) -> int:
    rows = [r for r in await _open(db, user) if r.id != current]
    n = await _mark(db, user, rows, "others")
    if not rows:  # FIX-A F-AUB-1: tokens issued but not used yet have no row; the epoch still moves on
        _bump(user)
    await audit.record(db, "auth.session_revoked", "user", user.id, after={"others": True, "count": n})
    return n


async def revoke_all(db: AsyncSession, user: User, *, actor: User | None, reason: str = "admin") -> int:
    """Every session of ``user`` (an administrator, an MFA reset): the rows are marked and the token version moves on,
    so tokens without a ``jti`` end too. The caller commits."""
    from app.core.security import revoke_tokens

    async with rls.system_scope(db):
        rows = list(
            (
                await db.execute(
                    select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                )
            ).scalars()
        )
        n = await _mark(db, user, rows, reason)
    revoke_tokens(user)
    await audit.record(
        db,
        "auth.sessions_revoked_by_admin" if actor is not None and actor.id != user.id else "auth.session_revoked",
        "user",
        user.id,
        after={"all": True, "count": n, "reason": reason},
        actor=actor,
    )
    return n


async def dsr_rows(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    async with rls.system_scope(db):
        rows = (await db.execute(select(UserSession).where(UserSession.user_id == user_id))).scalars()
        return [
            {
                "created_at": r.created_at,
                "last_seen_at": r.last_seen_at,
                "device": r.device,
                "network": r.network,
                "revoked_at": r.revoked_at,
            }
            for r in rows
        ]


__all__ = ["check", "current_id", "list_own", "network_of", "revoke_all", "revoke_one", "revoke_others"]
