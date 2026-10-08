"""AI endpoints: run chat (propose -> apply), constraint elicitation, preference-file upload, explain, catalogue.

Every endpoint needs PLANNER or ADMIN. Endpoints that call the model answer 409 when no Anthropic key
is configured (Settings > AI), 422 when the model declined the request and 502 on upstream errors.
Nothing the model proposes is applied without an explicit ``.../apply`` or ``.../accept`` call.
"""

from __future__ import annotations

import logging
from pathlib import PurePath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import catalog
from app.ai.chat import ChatError, apply_diff, chat_history, explain_run, handle_chat
from app.ai.client import AIClient, AIConfigError, AIRefusal, AIUpstreamError, get_client
from app.ai.edits import apply_section_edits
from app.ai.elicit import accept_proposals, elicit_constraints
from app.ai.ingest import MAX_FILE_BYTES, SUPPORTED, IngestError, extract_preferences
from app.api.deps import DB, Planner
from app.core.safe_files import UnsafeFileError, precheck_upload
from app.core.security import redact_keys
from app.models import ScheduleRun, Term
from app.schemas.ai import (
    AcceptIn,
    AcceptOut,
    ApplyIn,
    ApplyOut,
    CatalogOut,
    ChatIn,
    ChatMessageOut,
    ChatOut,
    ElicitIn,
    ElicitOut,
    ExplainIn,
    ExplainOut,
    IngestOut,
)

router = APIRouter(tags=["ai"])
log = logging.getLogger(__name__)

NO_KEY = "No Anthropic API key is configured. An admin can add one under Settings > AI (Ayarlar > Yapay zekâ)."


async def _client(db: AsyncSession) -> AIClient:
    try:
        return await get_client(db)
    except AIConfigError as exc:
        raise HTTPException(409, NO_KEY) from exc


def _ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AIRefusal):
        return HTTPException(422, f"The model declined this request ({exc.category or 'unspecified'}).")
    if isinstance(exc, AIConfigError):
        return HTTPException(409, NO_KEY)
    if isinstance(exc, AIUpstreamError):  # our own short texts (client.py), never the upstream body
        return HTTPException(502, redact_keys(str(exc))[:300])
    return HTTPException(502, "the AI service failed; try again later")


async def _run(db: AsyncSession, run_id: int) -> ScheduleRun:
    run = await db.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


async def _term(db: AsyncSession, term_id: int) -> Term:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    return term


# --------------------------------------------------------------------- run chat


@router.post("/runs/{run_id}/chat", response_model=ChatOut)
async def post_chat(run_id: int, body: ChatIn, db: DB, user: Planner) -> ChatOut:
    await _run(db, run_id)
    client = await _client(db)
    try:
        return await handle_chat(db, run_id, body.message, body.lang, client=client, user_id=user.id)
    except (AIRefusal, AIUpstreamError) as exc:
        raise _ai_error(exc) from exc
    except ChatError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/chat/apply", response_model=ApplyOut)
async def post_chat_apply(run_id: int, body: ApplyIn, db: DB, user: Planner) -> ApplyOut:
    await _run(db, run_id)
    if body.diff_id is None and body.diff is None:
        raise HTTPException(422, "pass diff_id (from POST /runs/{id}/chat) or an edited diff")
    try:
        return await apply_diff(db, run_id, diff=body.diff, diff_id=body.diff_id, user_id=user.id, label=body.label)
    except ChatError as exc:
        status = 409 if "already applied" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc


@router.get("/runs/{run_id}/chat", response_model=list[ChatMessageOut])
async def get_chat(run_id: int, db: DB, _: Planner) -> list[ChatMessageOut]:
    await _run(db, run_id)
    return [
        ChatMessageOut(id=m.id, role=m.role, content=m.content, tool_calls=m.tool_calls or [], created_at=m.created_at)
        for m in await chat_history(db, run_id)
    ]


@router.post("/runs/{run_id}/explain", response_model=ExplainOut)
async def post_explain(run_id: int, body: ExplainIn, db: DB, _: Planner) -> ExplainOut:
    """TR/EN explanation of a run. Falls back to the deterministic template when no key is set."""
    await _run(db, run_id)
    client: AIClient | None = None
    if body.use_model:
        try:
            client = await get_client(db)
        except AIConfigError:
            client = None
    try:
        return await explain_run(db, run_id, body.lang, client=client)
    except (AIRefusal, AIUpstreamError):
        log.warning("explain: model unavailable; template rendering used")
        return await explain_run(db, run_id, body.lang, client=None)


# ------------------------------------------------------------------ elicitation


@router.post("/terms/{term_id}/elicit", response_model=ElicitOut)
async def post_elicit(term_id: int, body: ElicitIn, db: DB, _: Planner) -> ElicitOut:
    await _term(db, term_id)
    client = await _client(db)
    try:
        return await elicit_constraints(db, term_id, body.text, body.lang, client=client)
    except (AIRefusal, AIUpstreamError) as exc:
        raise _ai_error(exc) from exc


@router.post("/terms/{term_id}/elicit/accept", response_model=AcceptOut)
async def post_elicit_accept(term_id: int, body: AcceptIn, db: DB, user: Planner) -> AcceptOut:
    """Persist reviewed proposals (constraints, source AI/UPLOAD) and section edits; ids re-verified."""
    await _term(db, term_id)
    if body.run_id is not None:
        run = await _run(db, body.run_id)
        if run.term_id != term_id:
            raise HTTPException(400, "run belongs to another term")
    created, rejected = await accept_proposals(
        db, term_id, body.proposals, user_id=user.id, run_id=body.run_id, commit=False
    )
    applied, rejected_edits = await apply_section_edits(
        db, term_id, body.section_edits, commit=False, draft_user_id=user.id
    )
    await db.commit()
    return AcceptOut(
        created=created,
        rejected=rejected + [{**r, "section_edit": True} for r in rejected_edits],
        section_edits_applied=applied,
    )


@router.post("/terms/{term_id}/preferences/upload", response_model=IngestOut)
async def post_preferences_upload(
    term_id: int,
    db: DB,
    _: Planner,
    file: UploadFile = File(...),
    lang: str = Form("tr"),
) -> IngestOut:
    """Preference file (.xlsx/.csv/.docx/.pdf/.txt/.md) -> proposals + section edits with source refs."""
    await _term(db, term_id)
    if PurePath(file.filename or "").suffix.lower() not in SUPPORTED:
        raise HTTPException(400, "unsupported file type; use .xlsx, .csv, .docx, .pdf, .txt or .md")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"file too large (max {MAX_FILE_BYTES // (1024 * 1024)} MiB)")
    try:  # refuse zip bombs before anything else (no key needed to be rejected)
        await precheck_upload(data, file.filename)
    except UnsafeFileError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    client = await _client(db)
    try:
        return await extract_preferences(
            db, term_id, data, file.filename or "upload", "en" if lang == "en" else "tr", client=client
        )
    except UnsafeFileError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (AIRefusal, AIUpstreamError) as exc:
        raise _ai_error(exc) from exc


# -------------------------------------------------------------------- catalogue


@router.get("/ai/catalog", response_model=CatalogOut)
async def get_catalog(_: Planner) -> CatalogOut:
    """Full TR/EN constraint catalogue + the strict tool schemas the model may use."""
    return CatalogOut.model_validate(catalog.catalog_dict())
