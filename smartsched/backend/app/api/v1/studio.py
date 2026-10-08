"""Generator Studio endpoints (PLANNER+, see docs/design/generator-studio.md §7).

Drafts are per user, term and kind; everything a planner shapes in the studio (left-out classes, pins,
per-draft rule switches) lives in the draft. Class-list edits write through to the real meeting /
section rows, with an imported snapshot so each field can be reverted.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, Planner
from app.models import StudioDraft, User
from app.schemas.studio import (
    AcceptIn,
    BulkEditIn,
    BulkEditOut,
    BulkRevertIn,
    ClassPage,
    ClassRow,
    CopyIn,
    CopyOut,
    DraftIn,
    DraftOut,
    FixIn,
    FixResultOut,
    GenerateIn,
    GenerateOut,
    PrecheckOut,
    PreviewIn,
    PreviewOut,
    RevertIn,
    RulesOut,
)
from app.services import precheck as pc
from app.services import studio as st
from app.services import studio_classes as sc
from app.services import studio_rules as sr

router = APIRouter(tags=["studio"])


def _http(exc: st.StudioError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


def _etag(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise HTTPException(400, 'If-Match must be the draft etag, e.g. "3"') from exc


async def _draft(db: AsyncSession, term_id: int, user: User | int, kind: str) -> StudioDraft:
    """``user`` may be the id: after a rollback the ``User`` row is expired and must not be touched."""
    try:
        return await st.get_draft(db, term_id, user if isinstance(user, int) else user.id, kind)
    except st.StudioError as exc:
        raise _http(exc) from exc


# --------------------------------------------------------------------------- meta


@router.get("/studio/meta")
async def studio_meta(_: Planner) -> dict[str, Any]:
    """Weight scale (Low/Normal/High = 2/5/8), the 14 rule templates, built-in rules, sources and the full
    TR/EN constraint catalogue (``app.ai.catalog.catalog_dict()``)."""
    return sr.meta()


# --------------------------------------------------------------------------- draft


@router.get("/terms/{term_id}/studio", response_model=DraftOut)
async def get_studio(term_id: int, db: DB, user: Planner, kind: str = "COURSE") -> dict[str, Any]:
    draft = await _draft(db, term_id, user, kind)
    return await st.draft_out(db, draft)


@router.put("/terms/{term_id}/studio", response_model=DraftOut)
async def put_studio(
    term_id: int, body: DraftIn, db: DB, user: Planner, if_match: str | None = Header(default=None)
) -> Any:
    """Partial update with optimistic concurrency: send ``version`` (or ``If-Match: "<version>"``). Sending
    the same values again is a no-op (version unchanged); a stale version answers 409 with ``current``."""
    uid = user.id
    draft = await _draft(db, term_id, uid, body.kind)
    expected = body.version if body.version is not None else _etag(if_match)
    try:
        draft = await st.update_draft(db, draft, body, user, expected_version=expected)
    except st.StudioError as exc:
        await db.rollback()
        if exc.status == 409:
            current = await st.draft_out(db, await _draft(db, term_id, uid, body.kind))
            return JSONResponse(
                status_code=409,
                content={
                    "detail": {
                        "message": "the draft changed since you loaded it",
                        "current": json.loads(DraftOut.model_validate(current).model_dump_json()),
                    }
                },
            )
        raise _http(exc) from exc
    return await st.draft_out(db, draft)


@router.get("/terms/{term_id}/studio/summary")
async def studio_summary(term_id: int, db: DB, user: Planner, kind: str = "COURSE") -> dict[str, Any]:
    draft = await _draft(db, term_id, user, kind)
    return await st.summary(db, draft)


# --------------------------------------------------------------------------- class list + edits


@router.get("/terms/{term_id}/studio/classes", response_model=ClassPage)
async def studio_classes(
    term_id: int,
    db: DB,
    user: Planner,
    kind: str = "COURSE",
    faculty_id: int | None = None,
    program_id: int | None = None,
    class_year: int | None = None,
    day: int | None = None,
    building: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    changed: bool | None = None,
    included: bool | None = None,
    needs_room: bool | None = None,
    pinned: bool | None = None,
    rule_id: int | None = None,
    ids: str | None = Query(None, description="comma-separated class ids"),
    q: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    draft = await _draft(db, term_id, user, kind)
    filters = sc.ClassFilters(
        faculty_id=faculty_id,
        program_id=program_id,
        class_year=class_year,
        day=day,
        building=building,
        mode=mode,
        status=status,
        changed=changed,
        included=included,
        needs_room=needs_room,
        pinned=pinned,
        rule_id=rule_id,
        ids=[int(x) for x in ids.split(",") if x.strip()] if ids else None,
        q=q,
    )
    try:
        return await sc.class_page(db, draft, filters, limit=limit, offset=offset)
    except st.StudioError as exc:
        raise _http(exc) from exc


@router.put("/studio/meetings/bulk", response_model=BulkEditOut)
async def bulk_edit(body: BulkEditIn, db: DB, user: Planner) -> dict[str, Any]:
    """Edit meeting requests (and their section's enrolment / mode) with per-row validation. Valid rows are
    written (the imported values are snapshotted first), invalid rows are reported and left unchanged."""
    try:
        return await sc.bulk_edit(db, body, user)
    except st.StudioError as exc:
        raise _http(exc) from exc


@router.post("/studio/meetings/{mr_id}/revert", response_model=ClassRow)
async def revert_meeting(mr_id: int, body: RevertIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        rows = await sc.revert(db, [mr_id], body.fields, user)
    except st.StudioError as exc:
        raise _http(exc) from exc
    return rows[0]


@router.post("/studio/meetings/revert", response_model=list[ClassRow])
async def revert_meetings(body: BulkRevertIn, db: DB, user: Planner) -> list[dict[str, Any]]:
    """Revert several rows ("Revert all" in the changes sheet)."""
    try:
        return await sc.revert(db, body.ids, body.fields, user)
    except st.StudioError as exc:
        raise _http(exc) from exc


# --------------------------------------------------------------------------- pre-check


@router.post("/terms/{term_id}/studio/precheck", response_model=PrecheckOut)
async def studio_precheck(term_id: int, db: DB, user: Planner, kind: str = "COURSE") -> dict[str, Any]:
    draft = await _draft(db, term_id, user, kind)
    return await pc.run_precheck(db, draft)


@router.post("/terms/{term_id}/studio/precheck/fix", response_model=FixResultOut)
async def studio_precheck_fix(term_id: int, body: FixIn, db: DB, user: Planner, kind: str = "COURSE") -> dict[str, Any]:
    """Apply one fix option of a pre-check item into the draft (exclusion, class edit, per-draft rule
    switch, built-in switch for ADMIN), then re-run the pre-check."""
    uid = user.id
    draft = await _draft(db, term_id, uid, kind)
    try:
        applied = await pc.apply_fix(db, draft, body.item_id, body.option, user)
    except st.StudioError as exc:
        await db.rollback()
        raise _http(exc) from exc
    draft = await _draft(db, term_id, uid, kind)
    return {"applied": applied, "draft": await st.draft_out(db, draft), "precheck": await pc.run_precheck(db, draft)}


# --------------------------------------------------------------------------- rules


@router.get("/terms/{term_id}/studio/rules", response_model=RulesOut)
async def studio_rules(term_id: int, db: DB, user: Planner, kind: str = "COURSE") -> dict[str, Any]:
    """Term rules with ``source_ref``, per-draft state (in play / override) and affected counts, plus the
    built-in cards."""
    draft = await _draft(db, term_id, user, kind)
    return await sr.rules_for_draft(db, draft)


@router.post("/studio/constraints/preview", response_model=PreviewOut)
async def preview_constraint(body: PreviewIn, db: DB, user: Planner) -> dict[str, Any]:
    draft = await _draft(db, body.term_id, user, body.draft_kind)
    return await sr.preview(db, draft, body)


@router.post("/studio/constraints/copy", response_model=CopyOut)
async def copy_constraints(body: CopyIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        return await sr.copy_rules(db, body, user)
    except st.StudioError as exc:
        raise _http(exc) from exc


@router.post("/terms/{term_id}/studio/proposals/accept")
async def accept_studio_proposals(term_id: int, body: AcceptIn, db: DB, user: Planner) -> dict[str, Any]:
    """``/elicit/accept`` for the studio review tray: same validation, and the upload provenance is stored
    in ``constraints.source_ref`` (column) instead of ``params._source_ref``."""
    try:
        return await sr.accept(db, term_id, body, user)
    except st.StudioError as exc:
        raise _http(exc) from exc


@router.post("/terms/{term_id}/studio/preferences/mapping")
async def preferences_mapping(
    term_id: int,
    db: DB,
    _: Planner,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    lang: str = Form("tr"),
) -> dict[str, Any]:
    """No-AI fallback for Excel/CSV preference sheets. Without ``mapping``: detected columns, sample values
    and a suggested mapping. With ``mapping`` (JSON ``{"columns": {"course": 0, "room": 3, ...},
    "room_rule": "prefer"|"pin"|"forbid", "hardness": "soft"|"hard", "weight": 5, "header_row": 1}``):
    proposals (rule cards) and section edits, each with ``source_ref {file, sheet, row}``. Accept them
    with ``POST /terms/{id}/studio/proposals/accept``."""
    data = await file.read(sr.MAX_MAPPING_BYTES + 1)
    if len(data) > sr.MAX_MAPPING_BYTES:
        raise HTTPException(413, "file too large (max 5 MiB)")
    try:
        parsed = json.loads(mapping) if mapping else None
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"mapping is not valid JSON: {exc.msg}") from exc
    try:
        return await sr.mapping_fallback(db, term_id, data, file.filename or "upload", parsed, lang)
    except st.StudioError as exc:
        raise _http(exc) from exc


# --------------------------------------------------------------------------- generate


@router.post("/terms/{term_id}/studio/generate", response_model=GenerateOut, status_code=202)
async def studio_generate(
    term_id: int, body: GenerateIn, db: DB, user: Planner, kind: str = "COURSE"
) -> dict[str, Any]:
    """Create a schedule run from the draft and queue it (progress: ``GET /runs/{id}/events``)."""
    draft = await _draft(db, term_id, user, kind)
    try:
        return await st.generate(db, draft, body, user)
    except st.StudioError as exc:
        raise _http(exc) from exc
