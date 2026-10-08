"""P7 audit log API (docs/product/wave1-api.md §3) and the per-request audit context.

``audit_context`` runs for every ``/api/v1`` request (router-level dependency): it names the actor (from the
bearer token, without failing unauthenticated routes), the request id (``X-Request-ID`` or a new one, echoed in
the response) and the hashed client network, and attaches them to the request's DB session, so that
:mod:`app.services.audit` can write who did what.

* ``GET /audit`` -- filters: entity_type, entity_id, actor_id, action (prefix), from, to, cursor (older than this
  id), limit. ``audit.view`` sees everything; anyone else only events they made or that touched their own
  bookings, without request ids and network hashes.
* ``GET /audit/{id}`` -- one event with its children (bulk operations).
* ``POST /audit/{id}/undo`` -- reverse a booking create, move or cancel (see ``app.services.bookings_undo``).
* ``GET /audit/export.csv`` -- ``audit.view``.

There is no route that edits or deletes an audit event; the table refuses UPDATE and DELETE itself."""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentAccess, require_permission
from app.core.security import decode_access_token
from app.models import AuditEvent, Booking, User
from app.schemas.audit import AuditEventOut, AuditPage, UndoOut
from app.services import audit as audit_svc
from app.services import bookings as bsvc
from app.services import bookings_undo
from app.services.bookings_perms import Access

router = APIRouter(prefix="/audit", tags=["audit"])
_RID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


async def audit_context(request: Request, response: Response, db: DB) -> None:
    rid = request.headers.get("x-request-id") or ""
    if not _RID.match(rid):
        rid = uuid.uuid4().hex
    response.headers["X-Request-ID"] = rid
    address = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    actor: User | None = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:
            uid = int(decode_access_token(auth[7:].strip()).get("uid", 0))
        except (jwt.PyJWTError, TypeError, ValueError):
            uid = 0
        actor = await db.get(User, uid) if uid else None
    audit_svc.set_context(
        db,
        audit_svc.AuditContext(
            actor_id=actor.id if actor else None,
            actor_label=audit_svc.user_label(actor),
            actor_type="user" if actor else "anonymous",
            request_id=rid,
            ip_hash=audit_svc.hash_ip(address),
        ),
    )


def _out(ev: AuditEvent, full: bool) -> dict[str, Any]:
    d = {
        "id": ev.id,
        "ts": ev.ts.isoformat() if ev.ts else None,
        "actor_type": ev.actor_type,
        "actor_id": ev.actor_id,
        "actor_label": ev.actor_label,
        "action": ev.action,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
        "term_id": ev.term_id,
        "before": ev.before,
        "after": ev.after,
        "diff": ev.diff,
        "reason": ev.reason,
        "reversible": ev.reversible,
        "undo_of": ev.undo_of,
        "parent_id": ev.parent_id,
    }
    if full:
        d["request_id"] = ev.request_id
        d["ip_hash"] = ev.ip_hash
    return d


async def _own_scope(db: DB, access: Access) -> Any:
    """Events a user without ``audit.view`` may read: their own actions and events of their own bookings."""
    own = [str(i) for i in (await db.execute(select(Booking.id).where(Booking.user_id == access.user_id))).scalars()]
    cond = AuditEvent.actor_id == access.user_id
    if own:
        cond = or_(cond, (AuditEvent.entity_type == "booking") & AuditEvent.entity_id.in_(own))
    return cond


@router.get("", response_model=AuditPage)
async def list_events(
    db: DB,
    access: CurrentAccess,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: int | None = None,
    action: str | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    cursor: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    full = access.can("audit.view")
    q = select(AuditEvent).order_by(AuditEvent.id.desc())
    if not full:
        q = q.where(await _own_scope(db, access))
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if actor_id is not None:
        q = q.where(AuditEvent.actor_id == actor_id)
    if action:
        q = q.where(AuditEvent.action.startswith(action.strip()))
    if from_ is not None:
        q = q.where(AuditEvent.ts >= datetime.combine(from_, time()))
    if to is not None:
        q = q.where(AuditEvent.ts < datetime.combine(to + timedelta(days=1), time()))
    if cursor is not None:
        q = q.where(AuditEvent.id < cursor)
    rows = list((await db.execute(q.limit(limit + 1))).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    undone = set()
    if rows:
        undone = set(
            (await db.execute(select(AuditEvent.undo_of).where(AuditEvent.undo_of.in_([r.id for r in rows])))).scalars()
        )
    items = [{**_out(r, full), "undone": r.id in undone} for r in rows]
    return {"items": items, "next_cursor": rows[-1].id if more and rows else None}


@router.get("/export.csv", dependencies=[Depends(require_permission("audit.view"))])
async def export_csv(
    db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    entity_type: str | None = None,
) -> Response:
    q = select(AuditEvent).order_by(AuditEvent.id)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if from_ is not None:
        q = q.where(AuditEvent.ts >= datetime.combine(from_, time()))
    if to is not None:
        q = q.where(AuditEvent.ts < datetime.combine(to + timedelta(days=1), time()))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "ts", "actor", "action", "entity_type", "entity_id", "diff", "reason", "undo_of", "parent_id"])

    def safe(v: Any) -> str:  # spreadsheet formula injection (CRBS export rule, audit B9)
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

    import json

    for ev in (await db.execute(q)).scalars():
        w.writerow(
            [
                ev.id,
                ev.ts.isoformat() if ev.ts else "",
                safe(ev.actor_label),
                ev.action,
                ev.entity_type,
                safe(ev.entity_id),
                safe(json.dumps(ev.diff, ensure_ascii=False) if ev.diff else ""),
                safe(ev.reason),
                ev.undo_of or "",
                ev.parent_id or "",
            ]
        )
    return Response(
        buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )


@router.get("/{event_id}", response_model=AuditEventOut)
async def get_event(event_id: int, db: DB, access: CurrentAccess) -> dict[str, Any]:
    full = access.can("audit.view")
    q = select(AuditEvent).where(AuditEvent.id == event_id)
    if not full:
        q = q.where(await _own_scope(db, access))
    ev = (await db.execute(q)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "audit event not found")
    children = (
        await db.execute(select(AuditEvent).where(AuditEvent.parent_id == ev.id).order_by(AuditEvent.id))
    ).scalars()
    undone = (await db.execute(select(AuditEvent.id).where(AuditEvent.undo_of == ev.id))).first()
    return {**_out(ev, full), "undone": undone is not None, "children": [_out(c, full) for c in children]}


@router.post("/{event_id}/undo", response_model=UndoOut)
async def undo(event_id: int, db: DB, access: CurrentAccess) -> dict[str, Any]:
    # the caller must see the event (audit.view, or their own action / booking) before undoing it
    q = select(AuditEvent.id).where(AuditEvent.id == event_id)
    if not access.can("audit.view"):
        q = q.where(await _own_scope(db, access))
    if (await db.execute(q)).first() is None:
        raise HTTPException(404, "audit event not found")
    try:
        return await bookings_undo.undo(db, access, event_id)
    except bsvc.BookingError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.as_detail()) from exc
