"""The helper ("Yardımcı") API: search, the card contract, the action cards, confirm / undo and memory.

* ``GET  /helper/search``                  pages, "Nerede?" answers and data hits; no AI, no metering (HB-02)
* ``GET  /helper/schema``                  ``helper.card.v1`` JSON Schema + the action argument schemas (HB-07)
* ``GET  /helper/status``                  what the status chip shows (helper.md A6)
* ``GET  /helper/actions``                 the actions the caller may run (shortcuts, "Burada yap")
* ``GET  /helper/actions/recent``          the caller's own last confirmed helper actions with "Geri al" (HB-D)
* ``POST /helper/actions/{name}/card``     a card for an action with partial args, **no model call** (A4): a read
  runs; a write is previewed and answers ``confirm`` (all args resolved, A1), ``form`` or ``choice`` (HB-05)
* ``POST /helper/actions/confirm`` / ``/undo``                                                     (HB-05)
* ``GET / POST / DELETE /helper/notes``, ``PUT /helper/memory``                                    (HB-09)
* ``POST /helper/feedback``, ``POST /helper/events``; ``GET /helper/search?final=true`` records one query (HB-14)

The admin's ``ai.helper`` switches (HB-15, :mod:`app.ai.helper.settings`) filter the actions everywhere here; the
write steps and submitted searches are counted (:mod:`app.ai.helper.telemetry`, aggregates only).

Everything runs as the signed-in person (``CurrentAccess``), through the same services as the pages.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.ai.helper import cards
from app.ai.helper import schema as cs
from app.ai.helper.actions import registry as reg
from app.ai.helper.search import search as run_search
from app.api.deps import DB, CurrentAccess, CurrentUser, require_permission
from app.models import User

router = APIRouter(prefix="/helper", tags=["helper"])
log = logging.getLogger(__name__)


def refused(status: int, code: str, tr: str, en: str, **data: Any) -> HTTPException:
    """The project's error shape (``code``, ``message`` = English, ``message_tr``, ``message_en``) plus the card the
    helper shows for it."""
    kind = "limit" if status == 429 else ("refusal" if status in (403, 404) else "error")
    # a 409 "changed" brings the fresh card to show instead (a new preview with a new token, or a form)
    card = data.pop("card", None) or cards.dump(
        cards.status(kind, code if code.replace("_", "").isalpha() else "error", tr, en)
    )
    return HTTPException(
        status, {"code": code, "message": en, "message_en": en, "message_tr": tr, "card": card, **data}
    )


def _action_out(a: reg.Action) -> dict[str, Any]:
    return {
        "name": a.name,
        "kind": a.kind,
        "risk": a.risk,
        "card": a.card,
        "summary": {"tr": a.summary_tr, "en": a.summary_en},
    }


async def _enabled(db: DB, access: CurrentAccess) -> list[str]:
    """The action names the admin switched on for this person's audiences (HB-15)."""
    from app.ai.helper import settings as hs

    return (await hs.policy(db, access)).actions


async def _track(db: DB, step: Awaitable[None]) -> None:
    """Write one telemetry step and commit; a failure is logged and never reaches the person."""
    try:
        await step
        await db.commit()
    except Exception:  # noqa: BLE001 - telemetry must never break a route
        await db.rollback()
        log.warning("helper telemetry failed", exc_info=True)


@router.get("/search")
async def search(
    db: DB,
    access: CurrentAccess,
    q: str = Query("", max_length=200),
    limit: int = Query(6, ge=1, le=6),
    term_id: int | None = None,
    final: bool = False,
) -> dict[str, Any]:
    """``final=true`` when the person submits the search (Enter, "Nerede?"), never per keystroke: one ``query``
    event (HB-14); an index miss keeps only the folded words."""
    from app.ai.helper import telemetry
    from app.ai.helper.index import get_index

    t0 = time.perf_counter()
    allowed = reg.permitted_names(access, await _enabled(db, access))
    out = await run_search(db, access, q, limit=limit, term_id=term_id, allowed_actions=allowed)
    if final and q.strip():
        top = get_index().search(q, access.perms, limit=1)
        await _track(
            db,
            telemetry.record_query(
                db,
                access.user_id,
                text=q,
                mode="index",
                outcome="index",
                top_feature=top[0].entry.id if top else None,
                latency_s=time.perf_counter() - t0,
            ),
        )
    return out


@router.get("/schema")
async def schema(_: CurrentAccess) -> dict[str, Any]:
    return {
        "card": cs.card_json_schema(),
        "actions": {a.name: {**_action_out(a), "args": reg.strict_schema(a.args)} for a in reg.all_actions()},
    }


@router.get("/status")
async def status(request: Request, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """helper.md A6: ``{mode: ai | index, reason, provider_kind: local | cloud, provider_label, fallback_active,
    message}``. Index-only until an admin routes ``helper`` (owner default); see :mod:`app.ai.helper.status`."""
    from app.ai.helper import status as st

    return await st.helper_status(db, access.user_id, turn_available=st.turn_registered(request.app))


@router.get("/actions")
async def actions(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    return [_action_out(a) for a in reg.permitted(access, await _enabled(db, access))]


@router.get("/actions/recent")
async def recent_actions(
    db: DB, access: CurrentAccess, limit: int = Query(5, ge=1, le=20)
) -> list[dict[str, Any]]:
    """The person's own last confirmed helper actions (HB-D): ``[{id, action, kind, entity_id, feature_id,
    label {tr,en}, at, status: done | undone, undoable, undo_token?, undo_expires_at?}]``, newest first."""
    from app.ai.helper import recent

    return await recent.recent(db, access, limit)


class CardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    args: dict[str, Any] = Field(default_factory=dict)


async def build_card(name: str, args: dict[str, Any], db: DB, access: CurrentAccess) -> dict[str, Any]:
    """The same checks as a model's tool call (:func:`app.ai.helper.tooluse.run_action`), with no model call."""
    from app.ai.helper import tooluse

    a = reg.get(name)
    if a is None:
        raise refused(404, "unknown_action", "Böyle bir işlem yok.", "There is no such action.")
    try:
        card = await tooluse.run_action(reg.Ctx(db, access), a, args)
    except reg.ArgsInvalid as exc:
        raise refused(
            422,
            "invalid_args",
            "İşlemin bilgileri eksik ya da hatalı.",
            "The action's details are missing or invalid.",
            issues=exc.issues,
        ) from exc
    except reg.ActionRefused as exc:
        raise refused(exc.status, exc.code, exc.tr, exc.en, **exc.data) from exc
    out = cards.dump(card)
    if out.get("type") == "confirm":
        from app.ai.helper import telemetry

        await _track(db, telemetry.record_action(db, access.user_id, a.name, "preview"))
    return out


@router.post("/actions/{name}/card")
async def action_card(name: str, body: CardIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    return await build_card(name, body.args, db, access)


# ------------------------------------------------------------------------------------- confirm / undo (HB-05)


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=4000)


@router.post("/actions/confirm")
async def confirm(body: TokenIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """The card's button: verify the token, claim it once, re-run the preview, then write through the service.
    403 bad / other user's token, 410 expired, 409 already done or changed (with the new card)."""
    from app.ai.helper import confirm as cf
    from app.ai.helper import remember, telemetry, tooluse
    from app.ai.helper import settings as hs
    from app.ai.helper.actions import writes

    name: str | None = None
    try:
        try:
            p = cf.verify(body.token)
        except reg.ActionRefused:
            p = {}  # cf.confirm refuses it again and writes the audit row
        spec = writes.WRITES.get(str(p.get("a")))
        if spec is not None:
            name = spec.action.name
            if name not in await _enabled(db, access):  # switched off since the preview (HB-15)
                raise reg.ActionRefused(403, "action_off", *hs.ACTION_OFF)
            if reg.RATE.hit(access.user_id, spec.action):
                raise reg.ActionRefused(429, "rate_limited", tooluse.RATE_TR, tooluse.RATE_EN)
            await tooluse.gate(spec.action, reg.Ctx(db, access))
        elif str(p.get("a")) == remember.ACTION:  # "Bunu hatırla" (HB-D): memory rules, not an admin action switch
            name = remember.ACTION
            if reg.RATE.hit(access.user_id, remember.SPEC):
                raise reg.ActionRefused(429, "rate_limited", tooluse.RATE_TR, tooluse.RATE_EN)
        out = await cf.confirm(db, access, body.token)
    except reg.ActionRefused as exc:
        if name is not None:
            await _track(db, telemetry.record_action(db, access.user_id, name, "confirm", exc.code))
        raise refused(exc.status, exc.code, exc.tr, exc.en, **exc.data) from exc
    if name is not None:
        await _track(db, telemetry.record_action(db, access.user_id, name, "confirm"))
    return out


@router.post("/actions/undo")
async def undo(body: TokenIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """ "Geri al" on a result card (24 h, and only before the booking starts; ``bookings_undo`` decides)."""
    from app.ai.helper import confirm as cf
    from app.ai.helper import telemetry
    from app.models.helper import HelperActionInvocation

    name: str | None = None
    try:
        p = cf.verify(body.token)
        inv = await db.get(HelperActionInvocation, int(p.get("i") or 0)) if p.get("u") == access.user_id else None
        name = inv.action if inv is not None else None
    except (reg.ActionRefused, ValueError, TypeError):
        pass  # cf.undo refuses it with the right code
    try:
        out = await cf.undo(db, access, body.token)
    except reg.ActionRefused as exc:
        if name is not None:
            await _track(db, telemetry.record_action(db, access.user_id, name, "undo", exc.code))
        raise refused(exc.status, exc.code, exc.tr, exc.en, **exc.data) from exc
    if name is not None:
        await _track(db, telemetry.record_action(db, access.user_id, name, "undo"))
    return out


# ------------------------------------------------------------------------------------------- memory (HB-09)

HelperAdmin = Annotated[User, Depends(require_permission("setup.settings", "planning.admin"))]


def _refusal(exc: reg.ActionRefused) -> HTTPException:
    return refused(exc.status, exc.code, exc.tr, exc.en, **exc.data)


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=400)
    #: ``user_button`` = "Bunu hatırla" on a card, ``user_confirmed`` = "Not ekle" in Profil › Yardımcı
    source: Literal["user_button", "user_confirmed"]


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("/memory")
async def memory_state(db: DB, user: CurrentUser) -> dict[str, Any]:
    from app.ai.helper import memory

    return await memory.state(db, user)


@router.put("/memory")
async def memory_switch(body: MemoryIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    """The person's own switch "Yardımcı notlarımı kullansın" (off keeps the notes; "Tümünü sil" deletes them)."""
    from app.ai.helper import memory

    await memory.set_user_enabled(db, user, body.enabled)
    return await memory.state(db, user)


@router.get("/notes")
async def notes(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    from app.ai.helper import memory

    return await memory.list_notes(db, user)


@router.post("/notes", status_code=201)
async def add_note(body: NoteIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    from app.ai.helper import memory

    try:
        return await memory.add_note(db, user, body.text, body.source)
    except reg.ActionRefused as exc:
        raise _refusal(exc) from exc


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, db: DB, user: CurrentUser) -> None:
    from app.ai.helper import memory

    try:
        await memory.delete_note(db, user, note_id)
    except reg.ActionRefused as exc:
        raise _refusal(exc) from exc


@router.delete("/notes")
async def delete_notes(db: DB, user: CurrentUser, history: bool = False) -> dict[str, int]:
    """ "Tümünü sil" (notes); with ``history=true`` also "Geçmişi sil" (the conversation threads)."""
    from app.ai.helper import memory

    return await memory.delete_all(db, user, history=history)


class AdminSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_enabled: bool | None = None
    retention_days: int | None = Field(default=None, ge=1, le=365)
    history_days: int | None = Field(default=None, ge=1, le=365)


@router.get("/admin/settings")
async def admin_settings(db: DB, _: HelperAdmin) -> dict[str, Any]:
    from app.ai.helper import memory

    return await memory.settings(db)


@router.put("/admin/settings")
async def admin_settings_put(body: AdminSettingsIn, db: DB, user: HelperAdmin) -> dict[str, Any]:
    """The institution's memory switch and retention (audited ``ai.helper``). HB-15 adds modes and actions."""
    from app.ai.helper import memory
    from app.services import audit

    before = await memory.settings(db)
    patch: dict[str, Any] = {"memory": {}}
    if body.memory_enabled is not None:
        patch["memory"]["enabled"] = body.memory_enabled
    if body.retention_days is not None:
        patch["memory"]["retention_days"] = body.retention_days
    if body.history_days is not None:
        patch["history_days"] = body.history_days
    after = await memory.save_settings(db, patch)
    await audit.record(db, "ai.helper", "setting", "ai.helper", before=before, after=after, actor=user)
    await db.commit()
    return after


# --------------------------------------------------------------------------------------------- telemetry (HB-14)

TurnId = Annotated[str, Field(pattern=r"^[a-f0-9]{16}$")]
FeedbackReason = Literal["wrong_page", "wrong_answer", "not_helpful", "too_slow", "other"]


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: ``run_started.turn_id`` of the answer
    turn_id: TurnId
    thumb: Literal["up", "down"]
    #: a thumbs-down's reason (ignored with a thumbs-up)
    reason: FeedbackReason | None = None
    #: the person's own words (≤ 300), kept only with a thumbs-down and when the institution allows notes
    note: str | None = Field(default=None, max_length=300)


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["nav_click", "form_open", "cancel"]
    turn_id: TurnId | None = None
    feature_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.\-]{0,63}$")
    action: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")


def _telemetry_refusal(exc: Any) -> HTTPException:
    return HTTPException(
        exc.status, {"code": exc.code, "message": exc.en, "message_en": exc.en, "message_tr": exc.tr, **exc.data}
    )


@router.post("/feedback")
async def feedback(body: FeedbackIn, db: DB, access: CurrentAccess) -> dict[str, bool]:
    """Thumbs up / down on an answer (one per person and turn; a second answer replaces it). Aggregates only."""
    from app.ai.helper import telemetry

    try:
        out = await telemetry.feedback(db, access.user_id, body.turn_id, body.thumb, body.reason, body.note)
    except telemetry.TelemetryError as exc:
        raise _telemetry_refusal(exc) from exc
    await db.commit()
    return out


@router.post("/events", status_code=204)
async def events(body: EventIn, db: DB, access: CurrentAccess) -> None:
    """The client's steps the server cannot see: "Sayfayı aç" on a nav card (deflection), a form opened, a confirm
    card dismissed with "Vazgeç"."""
    from app.ai.helper import telemetry

    try:
        await telemetry.client_event(
            db, access.user_id, body.kind, turn_id=body.turn_id, feature_id=body.feature_id, action=body.action
        )
    except telemetry.TelemetryError as exc:
        raise _telemetry_refusal(exc) from exc
    await db.commit()
