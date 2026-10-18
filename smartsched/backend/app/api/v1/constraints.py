from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.models import ConstraintRow, ScheduleRun, Term, User
from app.schemas.runs import ConstraintIn, ConstraintOut, ConstraintUpdate
from app.services import audit
from app.services.bookings_perms import load_access
from app.services.constraint_guard import guard_rule, is_waiver, waiver_ref, without_waiver
from app.services.events import publish_event
from app.solver.model import CONSTRAINT_KINDS_V1

#: columns of a constraint row kept in its audit snapshots (review 2026-10-15 D5)
AUDIT_FIELDS = ("term_id", "run_id", "kind", "params", "hardness", "weight", "source", "nl_text", "enabled")

router = APIRouter(prefix="/constraints", tags=["constraints"])


@router.get("/kinds")
async def kinds(_: Viewer) -> list[str]:
    return list(CONSTRAINT_KINDS_V1)


@router.get("", response_model=list[ConstraintOut])
async def list_constraints(
    db: DB, _: Viewer, term_id: int | None = None, run_id: int | None = None, enabled: bool | None = None
) -> list[ConstraintRow]:
    # draft-scoped built-in switches are studio state, not term rules (review M10)
    q = select(ConstraintRow).where(ConstraintRow.source != "BUILTIN").order_by(ConstraintRow.id)
    if term_id is not None:
        q = q.where(ConstraintRow.term_id == term_id)
    if run_id is not None:
        q = q.where(ConstraintRow.run_id == run_id)
    if enabled is not None:
        q = q.where(ConstraintRow.enabled.is_(enabled))
    return list((await db.execute(q)).scalars())


@router.post("", response_model=ConstraintOut, status_code=201)
async def create_constraint(body: ConstraintIn, db: DB, user: Planner) -> ConstraintRow:
    if body.term_id is None and body.run_id is None:
        raise HTTPException(400, "term_id or run_id required")
    _validate(body.kind, body.params, body.hardness)
    if body.term_id is not None and await db.get(Term, body.term_id) is None:
        raise HTTPException(404, "term not found")
    run = await db.get(ScheduleRun, body.run_id) if body.run_id is not None else None
    if body.run_id is not None and run is None:
        raise HTTPException(404, "run not found")
    waived = await _guard(db, user, body.kind, body.params, body.hardness, body.source, body.reason)
    term_id = body.term_id if body.term_id is not None else (run.term_id if run is not None else None)
    pin_override = await _pin_guard(db, user, body.kind, body.params, body.hardness, body.reason, term_id)
    row = ConstraintRow(**body.model_dump(exclude={"reason"}), created_by=user.id)
    if waived:
        row.source_ref = waiver_ref(None, reason=body.reason or "", actor_id=user.id)
    if pin_override:
        row.source_ref = {**(row.source_ref or {}), "capacity_override": pin_override}
    db.add(row)
    await db.flush()
    after = audit.snapshot(row, AUDIT_FIELDS)
    await publish_event(
        db,
        "constraint.create",
        "constraint",
        row.id,
        after=after,
        actor=user,
        term_id=term_id,
        reason=pin_override,
    )
    if waived:
        await _audit_waiver(db, row, user, body.reason, term_id)
    await db.commit()
    await db.refresh(row)
    return row


def _keep_scope(source: str | None, before: dict[str, Any], after: dict[str, Any]) -> None:
    """E2EA-F07: ``params`` replace the whole object, so a client that sends only the field it changed would turn a
    one-exam rule into a term-wide one. ``kinds`` ("only exams") is never dropped by a replace, and a FILE row's
    rule (one row of the exam / planning list) keeps its ``event_ids``; the Studio's "Kime uygulanır" may still widen
    a planner's own rule on purpose (it rewrites the selectors)."""
    lost = [k for k in ("kinds",) if before.get(k) and not after.get(k)]
    if source == "FILE" and before.get("event_ids") and not after.get("event_ids"):
        lost.append("event_ids")
    if lost:
        raise HTTPException(
            422,
            {
                "code": "rule_scope_lost",
                "message": f"these params drop the rule's scope ({', '.join(lost)}): send them again, or add a new "
                "rule for the whole term",
                "message_tr": "Bu değişiklik kuralın kapsamını siliyor (hangi sınav / ders için olduğu). Kapsamı "
                "koruyun ya da tüm dönem için yeni bir kural ekleyin.",
                "message_en": "This change removes the rule's scope (which exam or class it is for). Keep the "
                "scope, or add a new rule for the whole term.",
                "fields": lost,
            },
        )


@router.put("/{cid}", response_model=ConstraintOut)
async def update_constraint(cid: int, body: ConstraintUpdate, db: DB, user: Planner) -> ConstraintRow:
    row = await _editable(db, cid)
    data = body.model_dump(exclude_unset=True, exclude={"reason"})
    params: dict[str, Any] = data["params"] if data.get("params") is not None else dict(row.params or {})
    hardness = data.get("hardness") or row.hardness
    if data.get("params") is not None:
        _keep_scope(row.source, row.params or {}, params)
    _validate(row.kind, params, hardness)
    enabled = data["enabled"] if data.get("enabled") is not None else row.enabled
    if row.source == "TEACHER" and enabled and not row.enabled and (row.source_ref or {}).get("review") != "accepted":
        # P19-T2: an academician's wish is switched on by its review decision (the academician is told), not here
        raise HTTPException(
            409,
            {
                "code": "review_first",
                "message": "accept the academician's preference first (POST /moderation/preferences/{id}/decide)",
                "message_tr": "Önce akademisyenin tercihini onaylayın (Tercihler › Kabul et)",
            },
        )
    was_waiver = bool(row.enabled) and is_waiver(row.kind, row.params, row.hardness)
    becomes_waiver = bool(enabled) and is_waiver(row.kind, params, hardness)
    # a waiver is (re)decided whenever the rule's reach changes: params, hardness or switching it back on
    reach_changed = any(data.get(k) is not None for k in ("params", "hardness", "enabled"))
    waived = False
    if becomes_waiver and (reach_changed or not was_waiver):
        waived = await _guard(db, user, row.kind, params, hardness, row.source, body.reason)
    pin_override = None
    if bool(enabled) and reach_changed:
        pin_override = await _pin_guard(db, user, row.kind, params, hardness, body.reason, await _term_of(db, row))
    before = audit.snapshot(row, AUDIT_FIELDS)
    for k, v in data.items():
        setattr(row, k, v)
    if waived:
        row.source_ref = waiver_ref(row.source_ref, reason=body.reason or "", actor_id=user.id)
    elif not becomes_waiver and (row.source_ref or {}).get("waiver"):
        row.source_ref = without_waiver(row.source_ref)
    if pin_override:
        row.source_ref = {**(row.source_ref or {}), "capacity_override": pin_override}
    await db.flush()
    term_id = await _term_of(db, row)
    after = audit.snapshot(row, AUDIT_FIELDS)
    await publish_event(
        db,
        "constraint.update",
        "constraint",
        row.id,
        before=before,
        after=after,
        actor=user,
        term_id=term_id,
        reason=pin_override,
    )
    if waived:
        await _audit_waiver(db, row, user, body.reason, term_id)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{cid}", status_code=204)
async def delete_constraint(cid: int, db: DB, user: Planner) -> None:
    row = await _editable(db, cid)
    before = audit.snapshot(row, AUDIT_FIELDS)
    term_id = await _term_of(db, row)
    await publish_event(db, "constraint.delete", "constraint", row.id, before=before, actor=user, term_id=term_id)
    await db.delete(row)
    await db.commit()


async def _guard(
    db: DB, user: User, kind: str, params: dict[str, Any], hardness: str | None, source: str | None, reason: str | None
) -> bool:
    """D1: refuse an untargeted soft structural rule unless a planning admin gives a reason. True = waiver."""
    if not is_waiver(kind, params, hardness):
        return False
    may_waive = "planning.admin" in (await load_access(db, user)).perms
    issues = guard_rule(kind, params, hardness, source=source, may_waive=may_waive, reason=reason)
    if issues:
        raise HTTPException(422, {"message": "structural rule cannot be waived", "issues": issues})
    return True


async def _pin_guard(
    db: DB,
    user: User,
    kind: str,
    params: dict[str, Any],
    hardness: str | None,
    reason: str | None,
    term_id: int | None,
) -> str | None:
    """Round-1 R1-M-03 (persona Q8): a hard room pin that cannot seat its class is refused (422 ``capacity``, "100
    öğrenci 30 kişilik B 201'e sığmaz") unless a planning administrator keeps it with a written ``reason``; the
    override text is returned (stored on ``source_ref`` and audited)."""
    from app.services import pin_guard

    if not pin_guard.is_hard_pin(kind, params, hardness):
        return None
    may = "planning.admin" in (await load_access(db, user)).perms
    refused, override = await pin_guard.check(
        db, kind, params, hardness, term_id=term_id, may_override=may, reason=reason
    )
    if refused is not None:
        raise HTTPException(422, refused)
    return override


async def _audit_waiver(db: DB, row: ConstraintRow, user: User, reason: str | None, term_id: int | None) -> None:
    after = audit.snapshot(row, AUDIT_FIELDS)
    await audit.record(
        db,
        "constraint.waive",
        "constraint",
        row.id,
        after=after,
        actor=user,
        reason=(reason or "").strip(),
        term_id=term_id,
    )


async def _term_of(db: DB, row: ConstraintRow) -> int | None:
    if row.term_id is not None:
        return row.term_id
    run = await db.get(ScheduleRun, row.run_id) if row.run_id is not None else None
    return run.term_id if run is not None else None


def _validate(kind: str, params: dict[str, Any], hardness: str | None) -> None:
    """Kind, params and hardness through the constraint catalogue (the same check as AI proposals)."""
    from app.ai.catalog import validate_params

    issues = validate_params(kind, dict(params or {}), hardness)
    if issues:
        raise HTTPException(422, {"message": "invalid constraint", "issues": issues[:20]})


async def _editable(db: DB, cid: int) -> ConstraintRow:
    row = await db.get(ConstraintRow, cid)
    if row is None or row.source == "BUILTIN":  # built-in switches belong to a studio draft (ADMIN only)
        if row is not None:
            raise HTTPException(403, "built-in rule switches are changed in the Generator Studio (ADMIN only)")
        raise HTTPException(404, "constraint not found")
    return row
