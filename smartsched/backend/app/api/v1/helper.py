"""The helper ("Yardımcı") API: search, the card contract, the action cards, confirm / undo and memory.

* ``GET  /helper/search``                  pages, "Nerede?" answers and data hits; no AI, no metering (HB-02)
* ``GET  /helper/schema``                  ``helper.card.v1`` JSON Schema + the action argument schemas (HB-07)
* ``GET  /helper/status``                  what the status chip shows (helper.md A6)
* ``GET  /helper/actions``                 the actions the caller may run (shortcuts, "Burada yap")
* ``POST /helper/actions/{name}/card``     a card for an action with partial args, **no model call** (A4): a read
  runs; a write is previewed and answers ``confirm`` (all args resolved, A1), ``form`` or ``choice`` (HB-05)
* ``POST /helper/actions/confirm`` / ``/undo``                                                     (HB-05)
* ``GET / POST / DELETE /helper/notes``, ``PUT /helper/memory``                                    (HB-09)

Everything runs as the signed-in person (``CurrentAccess``), through the same services as the pages.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.ai.helper import cards
from app.ai.helper import schema as cs
from app.ai.helper.actions import registry as reg
from app.ai.helper.search import search as run_search
from app.api.deps import DB, CurrentAccess, CurrentUser, require_permission
from app.models import User

router = APIRouter(prefix="/helper", tags=["helper"])


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


@router.get("/search")
async def search(
    db: DB,
    access: CurrentAccess,
    q: str = Query("", max_length=200),
    limit: int = Query(6, ge=1, le=6),
    term_id: int | None = None,
) -> dict[str, Any]:
    return await run_search(db, access, q, limit=limit, term_id=term_id, allowed_actions=reg.permitted_names(access))


@router.get("/schema")
async def schema(_: CurrentAccess) -> dict[str, Any]:
    return {
        "card": cs.card_json_schema(),
        "actions": {a.name: {**_action_out(a), "args": reg.strict_schema(a.args)} for a in reg.all_actions()},
    }


@router.get("/status")
async def status(_: CurrentAccess) -> dict[str, Any]:
    """helper.md A6. Until the model turn loop lands (HB-06, after VO-01) the helper answers from the index only, so
    the chip reads "Yapay zekâ kapalı" and nothing is sent to any model."""
    return {"mode": "index", "provider_kind": None, "provider_label": None, "fallback_active": False}


@router.get("/actions")
async def actions(access: CurrentAccess) -> list[dict[str, Any]]:
    return [_action_out(a) for a in reg.permitted(access)]


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
    return cards.dump(card)


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
    from app.ai.helper import tooluse
    from app.ai.helper.actions import writes

    try:
        try:
            p = cf.verify(body.token)
        except reg.ActionRefused:
            p = {}  # cf.confirm refuses it again and writes the audit row
        spec = writes.WRITES.get(str(p.get("a")))
        if spec is not None:
            if reg.RATE.hit(access.user_id, spec.action):
                raise reg.ActionRefused(429, "rate_limited", tooluse.RATE_TR, tooluse.RATE_EN)
            await tooluse.gate(spec.action, reg.Ctx(db, access))
        return await cf.confirm(db, access, body.token)
    except reg.ActionRefused as exc:
        raise refused(exc.status, exc.code, exc.tr, exc.en, **exc.data) from exc


@router.post("/actions/undo")
async def undo(body: TokenIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """ "Geri al" on a result card (24 h, and only before the booking starts; ``bookings_undo`` decides)."""
    from app.ai.helper import confirm as cf

    try:
        return await cf.undo(db, access, body.token)
    except reg.ActionRefused as exc:
        raise refused(exc.status, exc.code, exc.tr, exc.en, **exc.data) from exc


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
