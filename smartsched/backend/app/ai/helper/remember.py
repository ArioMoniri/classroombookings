""""Bunu hatırla: …" (HB-D; helper.md §5.1): a note is saved only by the person's click on a confirm card.

* :func:`detect` finds a request to remember at the **start** of what the person typed ("bunu hatırla: …",
  "hatırla: …", "aklında tut: …", "remember (this|that): …") and returns their own words after it. The turn loop
  (:func:`app.ai.helper_turn.run_turn`) then makes **no model call**: the note is never the model's paraphrase.
* :func:`card` runs every rule of "Not ekle" (:func:`app.ai.helper.memory.check_note`: the institution's and the
  person's memory switches, the ``ai_personal`` consent, ≤ 200 characters, ≤ 20 notes, no other person's name) plus
  the helper's note guard (:func:`app.ai.helper.guard.check_note`: no instruction, no role hand-off) and answers a
  ``confirm`` card (action ``remember_note``, R1) with a signed token, or a ``refusal`` card. It writes nothing.
* :func:`execute` runs from :func:`app.ai.helper.confirm.confirm` (the card's button, ``POST
  /helper/actions/confirm``) after the token, user, expiry and once-only claim checks: the rules again, then the note
  (``source = user_button``) and the ``helper.action.remember_note`` audit row (no note text in the audit).
* :func:`undo` ("Geri al", ``POST /helper/actions/undo``, 24 h) deletes that note again
  (audit ``helper.action.remember_note.undo``).

The note reaches later prompts only as the spotlighted ``user_notes`` block (HB-06), like every other note.
``remember_note`` is not a registry action: the model is never offered it as a tool.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.registry import Action, ActionRefused, Args
from app.models.base import utcnow
from app.models.helper import HelperActionInvocation, HelperNote
from app.services import audit
from app.services.bookings_perms import Access

ACTION = "remember_note"
FEATURE = "profile.helper_memory"
SUMMARY = ("Bunu hatırla", "Remember this")
#: "bunu hatırla:", "şunu hatırla -", "hatırla:", "aklında tut:", "remember:", "remember this:", "remember that …"
_TR = r"(?:(?:bunu|şunu|sunu)\s+)?(?:hat[ıi]rla|akl[ıi]nda\s+tut)\s*[:\-–—]"
_EN = r"remember(?:\s+this)?\s*[:\-–—]|remember\s+that\b"
_ASK = re.compile(rf"^\s*(?:{_TR}|{_EN})\s*(?P<text>.*)$", re.IGNORECASE | re.DOTALL)
_QUESTION = re.compile(r"\?\s*$")


class RememberArgs(Args):
    text: str = ""


async def _no_run(_ctx: Any, _args: Any) -> s.CardBase:  # never offered, never run through the registry
    raise ActionRefused(404, "unknown_action", "Böyle bir işlem yok.", "There is no such action.")


#: not in the registry (the model never gets it as a tool); used for the rate limit and the labels
SPEC = Action(
    name=ACTION,
    kind="write",
    permission=(),
    args=RememberArgs,
    summary_tr=SUMMARY[0],
    summary_en=SUMMARY[1],
    description="Save a helper note the person typed after 'bunu hatırla:'.",
    route="POST /helper/notes",
    card="confirm",
    run=_no_run,
    risk="R1",
    rate=(10, 60),
)


def _fold_i(text: str) -> str:
    """``İ`` lower-cases to two characters in Python; map the Turkish capitals first so the match keeps positions."""
    return text.replace("İ", "i").replace("I", "ı")


def detect(text: str) -> str | None:
    """The person's own words after a "remember" request at the start of ``text`` (``""`` when nothing follows), or
    ``None`` when the text is not one (a question about the past is not: "… hatırla: hangi salondu?")."""
    raw = text or ""
    m = _ASK.match(_fold_i(raw)) or _ASK.match(raw)
    if m is None:
        return None
    note = " ".join(raw[m.start("text") :].split())
    if note and _QUESTION.search(note):
        return None
    return note


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _refusal(code: str, tr: str, en: str, fallback: list[s.NavCard]) -> dict[str, Any]:
    kind = "limit" if code == "rate_limited" else "refusal"
    return cards.dump(cards.status(kind, code, tr, en, fallback, action=ACTION))


async def _memory_nav(access: Access) -> list[s.NavCard]:
    from app.ai.helper.index import get_index, visible

    entry = next((e for e in get_index().entries if e.id == FEATURE), None)
    return [cards.nav(entry)] if entry is not None and visible(entry, access.perms) else []


async def card(session: AsyncSession, access: Access, text: str) -> dict[str, Any]:
    """The ``confirm`` card for "bunu hatırla: ``text``", or a ``refusal`` card naming the rule (with the
    Profil › Yardımcı row). Writes nothing."""
    from app.ai.helper import confirm as cf
    from app.ai.helper import guard, memory

    fallback = await _memory_nav(access)
    verdict = guard.check_note(text)
    if not verdict.allowed:
        code = re.sub(r"[^a-z_]", "", (verdict.code or "refused").lower())[:48] or "refused"
        return _refusal(code, verdict.message_tr, verdict.message_en, fallback)
    try:
        clean, _ = await memory.check_note(session, access.user, text, require_consent=True)
    except ActionRefused as exc:
        return _refusal(exc.code, exc.tr, exc.en, fallback)
    args = {"text": clean}
    token, exp = cf.confirm_token(access.user_id, ACTION, args, cf.digest({"action": ACTION, **args}), utcnow())
    return cards.dump(
        s.ConfirmCard(
            id=cards.new_id(),
            action=ACTION,
            title=cards.txt("Bunu hatırlayayım mı?", "Shall I remember this?"),
            risk="R1",
            token=token,
            expires_at=exp,
            preview=[s.PreviewLine(label=cards.txt("Not", "Note"), value=cards.txt(clean))],
            warnings=[
                cards.txt(
                    "Notlarınızı Profil › Yardımcı'da görebilir ve silebilirsiniz.",
                    "You can see and delete your notes in Profile › Helper.",
                )
            ],
            button=cards.txt(f"Hatırla: {_short(clean)}", f"Remember: {_short(clean)}"),
            undoable=True,
            args=args,
        )
    )


async def execute(session: AsyncSession, access: Access, args: dict[str, Any], inv_id: int) -> dict[str, Any]:
    """The click (after :func:`app.ai.helper.confirm.confirm`'s token checks and the once-only claim): the rules
    again, the note, the audit row, the ``result`` card with its undo token."""
    from app.ai.helper import confirm as cf
    from app.ai.helper import guard, memory

    text = str(args.get("text") or "")
    verdict = guard.check_note(text)
    if not verdict.allowed:
        raise ActionRefused(422, verdict.code or "refused", verdict.message_tr, verdict.message_en)
    note = await memory.add_note(session, access.user, text, "user_button", require_consent=True)
    ev = await audit.record(
        session,
        f"helper.action.{ACTION}",
        "helper_action",
        inv_id,
        after={"via": "helper", "invocation_id": inv_id, "entity": {"kind": "note", "id": note["id"]}},
        actor=access.user,
    )
    now = utcnow()
    inv = await session.get(HelperActionInvocation, inv_id)
    assert inv is not None
    inv.status, inv.done_at, inv.audit_id = "done", now, ev.id
    inv.entity_type, inv.entity_id = "note", int(note["id"])
    await session.commit()
    until = now + cf.UNDO_TTL
    return cards.dump(
        s.ResultCard(
            id=cards.new_id(),
            action=ACTION,
            ok=True,
            message=cards.txt(f"Not kaydedildi: {_short(note['text'])}", f"Note saved: {_short(note['text'])}"),
            entity=s.Entity(kind="note", id=int(note["id"]), feature_id=FEATURE),
            undo_token=cf.undo_token(access.user_id, inv_id, until),
            undo_expires_at=until,
            follow_ups=[s.FollowUp(label=cards.txt("Notlarım", "My notes"), feature_id=FEATURE)],
        )
    )


async def undo(session: AsyncSession, access: Access, inv: HelperActionInvocation) -> dict[str, Any]:
    """ "Geri al" on the result: delete the note this click saved (409 ``already_undone`` the second time; a note
    the person already deleted with "Unut" just stays deleted)."""
    if inv.user_id != access.user_id:
        raise ActionRefused(403, "other_user", "Bu işlem başka bir hesaba ait.", "This belongs to another account.")
    claimed = await session.execute(
        update(HelperActionInvocation)
        .where(HelperActionInvocation.id == inv.id, HelperActionInvocation.status == "done")
        .values(status="undone")
    )
    if getattr(claimed, "rowcount", 0) != 1:
        await session.rollback()
        raise ActionRefused(409, "already_undone", "Bu işlem zaten geri alındı.", "This was already undone.")
    removed = 0
    if inv.entity_id is not None:
        res = await session.execute(
            delete(HelperNote)
            .where(HelperNote.id == inv.entity_id, HelperNote.user_id == access.user_id)
            .execution_options(synchronize_session=False)
        )
        removed = int(getattr(res, "rowcount", 0) or 0)
    await audit.record(
        session,
        f"helper.action.{ACTION}.undo",
        "helper_action",
        inv.id,
        after={"via": "helper", "invocation_id": inv.id, "removed": removed},
        actor=access.user,
    )
    await session.commit()
    return cards.dump(
        s.ResultCard(
            id=cards.new_id(),
            action=ACTION,
            ok=True,
            message=cards.txt("Geri alındı; not silindi.", "Undone; the note was deleted."),
        )
    )


__all__ = ["ACTION", "FEATURE", "SPEC", "card", "detect", "execute", "undo"]
