"""Confirm and undo for helper writes (HB-05; architecture doc §2.3, §5.3).

A write never runs from a model or from typed text. Its card carries a **signed confirm token**:

``token = b64url(payload) + "." + b64url(HMAC-SHA256(key, payload))``, payload ``{u, a, args, ah, ph, exp, n}`` =
the user id, the action, the canonical arguments and their hash, the preview hash, the expiry (10 minutes) and a
random nonce. The key is derived from ``APP_SECRET`` with a helper-only label, so a token is useless anywhere else.
Building a card writes nothing.

:func:`confirm` (``POST /helper/actions/confirm``):

1. verify the signature (403 ``bad_token``), the user (403 ``other_user``), the expiry (410 ``expired``);
2. **claim the nonce once**: insert the ``helper_action_invocations`` row; its unique key turns a replay or a double
   click into 409 ``already_done``;
3. re-check access and **re-run the preview**; a different preview hash (the slot was taken, the request was decided
   meanwhile) answers 409 ``changed`` with the new card, never a silent different result;
4. execute through the page's service with the person's ``Access``, record ``helper.action.<name>`` in the audit log
   and answer a ``result`` card with an ``undo_token`` when the change can be reversed.

Rejected tokens are audited as ``helper.confirm_rejected``. :func:`undo` reverses a done invocation through
``app/services/bookings_undo.py`` (24 h or until the booking starts, conflict-checked).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.registry import ActionRefused, Ctx
from app.core.config import get_settings
from app.models.base import utcnow
from app.models.helper import HelperActionInvocation
from app.services import audit
from app.services.bookings_perms import Access

TOKEN_TTL = timedelta(minutes=10)
UNDO_TTL = timedelta(hours=24)
_LABEL = b"smartsched/helper/confirm/v1"


def _key() -> bytes:
    return hmac.new(get_settings().app_secret.encode("utf-8"), _LABEL, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(data: Any) -> str:
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def sign(payload: dict[str, Any]) -> str:
    body = canonical(payload).encode("utf-8")
    return f"{_b64(body)}.{_b64(hmac.new(_key(), body, hashlib.sha256).digest())}"


def verify(token: str) -> dict[str, Any]:
    """The payload of a token this server signed; :class:`ActionRefused` 403 otherwise."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _unb64(body_b64)
        good = hmac.compare_digest(_unb64(sig_b64), hmac.new(_key(), body, hashlib.sha256).digest())
        payload = json.loads(body) if good else None
    except (ValueError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict):
        raise ActionRefused(403, "bad_token", "Bu onay geçerli değil.", "This confirmation is not valid.")
    return payload


def confirm_token(user_id: int, action: str, args: dict[str, Any], preview_hash: str, now: datetime) -> tuple[str, datetime]:
    exp = now + TOKEN_TTL
    payload = {
        "k": "confirm",
        "u": user_id,
        "a": action,
        "args": args,
        "ah": digest(args),
        "ph": preview_hash,
        "exp": int(exp.timestamp()),
        "n": secrets.token_hex(16),
    }
    return sign(payload), exp


def undo_token(user_id: int, invocation_id: int, until: datetime) -> str:
    return sign({"k": "undo", "u": user_id, "i": invocation_id, "exp": int(until.timestamp()), "n": secrets.token_hex(8)})


@dataclass
class Executed:
    """What a write did: the entity, the result line, the service's reversible audit event, the follow-ups."""

    entity: s.Entity | None
    message: s.Txt
    undo_event_id: int | None = None
    #: until when the undo makes sense (the booking's start); ``None`` = no undo
    undo_until: datetime | None = None
    follow_ups: list[s.FollowUp] | None = None


async def _reject(session: AsyncSession, access: Access, code: str, action: str | None) -> None:
    await audit.record(
        session,
        "helper.confirm_rejected",
        "helper_action",
        action or "unknown",
        after={"code": code, "via": "helper"},
        actor=access.user,
    )
    await session.commit()


def _ts(value: Any) -> datetime:
    return datetime.fromtimestamp(int(value))


async def confirm(session: AsyncSession, access: Access, token: str) -> dict[str, Any]:
    from app.ai.helper.actions import writes

    try:
        p = verify(token)
    except ActionRefused:
        await _reject(session, access, "bad_token", None)
        raise
    action = str(p.get("a") or "")
    if p.get("k") != "confirm" or action not in writes.WRITES:
        await _reject(session, access, "bad_token", action)
        raise ActionRefused(403, "bad_token", "Bu onay geçerli değil.", "This confirmation is not valid.")
    if p.get("u") != access.user_id:
        await _reject(session, access, "other_user", action)
        raise ActionRefused(403, "other_user", "Bu onay başka bir hesaba ait.", "This confirmation belongs to another account.")
    now = utcnow()
    if _ts(p["exp"]) <= now.replace(tzinfo=None):
        await _reject(session, access, "expired", action)
        raise ActionRefused(410, "expired", "Bu öneri eskidi. Yenileyin.", "This suggestion is out of date. Refresh it.")
    spec = writes.WRITES[action]
    if spec.action.name != action or not spec.action.allowed(access):
        await _reject(session, access, "not_allowed", action)
        raise ActionRefused(403, "not_allowed", "Bu işlem hesabınızda yok.", "This isn't available on your account.")
    inv = HelperActionInvocation(
        user_id=access.user_id,
        action=action,
        args_hash=str(p["ah"]),
        preview_hash=str(p["ph"]),
        nonce=str(p["n"]),
        status="confirmed",
        created_at=now,
        expires_at=_ts(p["exp"]),
    )
    session.add(inv)
    try:
        await session.commit()  # the once-only claim: a second confirm of the same token hits the unique nonce
    except IntegrityError as exc:
        await session.rollback()
        await _reject(session, access, "already_done", action)
        raise ActionRefused(409, "already_done", "Bu işlem zaten yapıldı.", "This was already done.") from exc
    ctx = Ctx(session, access)
    args = spec.action.args.model_validate(p["args"])
    try:
        fresh = await spec.preview(ctx, args)
    except ActionRefused as exc:
        await _fail(session, inv, exc.code)
        raise
    if not isinstance(fresh, writes.Preview) or fresh.hash != inv.preview_hash:
        await _fail(session, inv, "changed")
        card = await spec.action.run(ctx, args)  # the new card (a fresh preview with a new token, or a form)
        raise ActionRefused(
            409,
            "changed",
            "Durum değişti; yeni öneriyi kontrol edin.",
            "Things changed; check the new suggestion.",
            card=cards.dump(card),
        )
    try:
        done = await spec.execute(ctx, args, fresh)
    except ActionRefused as exc:
        await session.rollback()
        await _fail(session, inv, exc.code)
        raise
    ev = await audit.record(
        session,
        f"helper.action.{action}",
        "helper_action",
        inv.id,
        after={
            "via": "helper",
            "invocation_id": inv.id,
            "entity": done.entity.model_dump() if done.entity else None,
            "args": p["args"],
        },
        actor=access.user,
    )
    inv = await session.get(HelperActionInvocation, inv.id) or inv
    inv.status, inv.done_at, inv.audit_id = "done", utcnow(), ev.id
    inv.entity_type = done.entity.kind if done.entity else None
    inv.entity_id = done.entity.id if done.entity else None
    inv.undo_event_id = done.undo_event_id
    await session.commit()
    token_out = until = None
    if done.undo_event_id is not None and done.undo_until is not None:
        until = min(utcnow() + UNDO_TTL, done.undo_until)
        if until > utcnow():
            token_out = undo_token(access.user_id, inv.id, until)
    return cards.dump(
        s.ResultCard(
            id=cards.new_id(),
            action=action,
            ok=True,
            message=done.message,
            entity=done.entity,
            undo_token=token_out,
            undo_expires_at=until if token_out else None,
            follow_ups=(done.follow_ups or [])[:2],
        )
    )


async def _fail(session: AsyncSession, inv: HelperActionInvocation, code: str) -> None:
    await session.execute(
        update(HelperActionInvocation)
        .where(HelperActionInvocation.id == inv.id)
        .values(status="failed", error_code=code[:48], done_at=utcnow())
    )
    await session.commit()


async def last_undoable(session: AsyncSession, access: Access) -> HelperActionInvocation | None:
    q = (
        select(HelperActionInvocation)
        .where(
            HelperActionInvocation.user_id == access.user_id,
            HelperActionInvocation.status == "done",
            HelperActionInvocation.undo_event_id.is_not(None),
            HelperActionInvocation.undo_of.is_(None),
        )
        .order_by(HelperActionInvocation.id.desc())
    )
    return (await session.execute(q)).scalars().first()


async def undo_invocation(session: AsyncSession, access: Access, inv: HelperActionInvocation) -> dict[str, Any]:
    """Reverse a done helper write through ``bookings_undo`` (which re-checks the window, later changes and the slot)."""
    from app.services import bookings as bsvc
    from app.services import bookings_undo

    if inv.user_id != access.user_id:
        raise ActionRefused(403, "other_user", "Bu işlem başka bir hesaba ait.", "This belongs to another account.")
    if inv.status != "done" or inv.undo_event_id is None:
        raise ActionRefused(409, "not_undoable", "Bu işlem geri alınamaz.", "This cannot be undone.")
    claimed = await session.execute(
        update(HelperActionInvocation)
        .where(HelperActionInvocation.id == inv.id, HelperActionInvocation.status == "done")
        .values(status="undone")
    )
    if getattr(claimed, "rowcount", 0) != 1:
        await session.rollback()
        raise ActionRefused(409, "already_undone", "Bu işlem zaten geri alındı.", "This was already undone.")
    try:
        out = await bookings_undo.undo(session, access, inv.undo_event_id)
    except bsvc.BookingError as exc:
        await session.rollback()
        d = exc.data
        raise ActionRefused(
            exc.status, exc.code, str(d.get("message_tr") or exc.message), exc.message,
            **{k: v for k, v in d.items() if k in ("alternatives", "later")},
        ) from exc
    now = utcnow()
    undo_row = HelperActionInvocation(
        user_id=access.user_id,
        action="undo_last_helper_action",
        args_hash=digest({"invocation": inv.id}),
        preview_hash=digest({"event": inv.undo_event_id}),
        nonce=secrets.token_hex(16),
        status="done",
        entity_type=inv.entity_type,
        entity_id=inv.entity_id,
        undo_of=inv.id,
        created_at=now,
        expires_at=now,
        done_at=now,
    )
    session.add(undo_row)
    await session.flush()
    ev = await audit.record(
        session,
        "helper.action.undo_last_helper_action",
        "helper_action",
        undo_row.id,
        after={"via": "helper", "invocation_id": undo_row.id, "undo_of": inv.id, "result": out},
        actor=access.user,
    )
    undo_row.audit_id = ev.id
    await session.commit()
    return cards.dump(
        s.ResultCard(
            id=cards.new_id(),
            action="undo_last_helper_action",
            ok=True,
            message=cards.txt("Geri alındı.", "Undone."),
            entity=s.Entity(kind="booking", id=inv.entity_id, feature_id="my_bookings") if inv.entity_id else None,
        )
    )


async def undo(session: AsyncSession, access: Access, token: str) -> dict[str, Any]:
    """``POST /helper/actions/undo`` with the ``undo_token`` of a result card."""
    p = verify(token)
    if p.get("k") != "undo":
        raise ActionRefused(403, "bad_token", "Bu geri alma geçerli değil.", "This undo is not valid.")
    if p.get("u") != access.user_id:
        raise ActionRefused(403, "other_user", "Bu işlem başka bir hesaba ait.", "This belongs to another account.")
    if _ts(p["exp"]) <= utcnow().replace(tzinfo=None):
        raise ActionRefused(
            410, "too_old", "Geri alma süresi doldu.", "The time to undo this has passed."
        )
    inv = await session.get(HelperActionInvocation, int(p["i"]))
    if inv is None:
        raise ActionRefused(404, "not_found", "İşlem bulunamadı.", "The action was not found.")
    return await undo_invocation(session, access, inv)


__all__ = [
    "Executed",
    "TOKEN_TTL",
    "UNDO_TTL",
    "canonical",
    "confirm",
    "confirm_token",
    "digest",
    "last_undoable",
    "sign",
    "undo",
    "undo_invocation",
    "undo_token",
    "verify",
]
