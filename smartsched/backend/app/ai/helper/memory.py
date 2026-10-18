"""Helper memory with consent (HB-09; architecture doc §2.6, §5.4; helper.md §5.1).

* A note is saved **only by the person's own action**: the "Bunu hatırla" / "Hatırla" button on a card
  (``source=user_button``) or "Not ekle" in Profil › Yardımcı (``source=user_confirmed``). Nothing is ever saved from
  inference, from the model, or from typed "evet".
* At most 20 notes of ≤ 200 characters. A note that names another person (any account or instructor of the
  institution other than the author) is refused: notes are about the person's own preferences. A note is plain text:
  it never changes a permission (RA-12) and goes to a model only as one spotlighted ``user_notes`` block (HB-06).
* Retention: notes 180 days since last use, threads 30 days, telemetry loses its ``user_id`` after 90 days
  (:func:`purge`, run by the daily KVKK purge).
* Switches: the institution's ``ai.helper`` setting (``memory.enabled``, admin only) and the person's own
  ``user.<id>.helper_memory`` (Profil › Yardımcı). Withdrawing the ``ai_personal`` consent deletes the notes and turns
  the person's memory off (:func:`on_ai_personal_withdrawn`, called by ``kvkk.withdraw``).
* KVKK: :func:`dsr_rows` for the export, :func:`erase` for the erasure.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper.actions.registry import ActionRefused
from app.core import rls
from app.importers import normalize as n
from app.models import Instructor, User
from app.models.base import utcnow
from app.models.helper import HelperActionInvocation, HelperEvent, HelperMessage, HelperNote, HelperThread
from app.services import settings_service
from app.services.bookings_settings import get_user_value, set_user_value

SETTINGS_KEY = "ai.helper"
USER_KEY = "helper_memory"
MAX_NOTES = 20
MAX_CHARS = 200
DEFAULTS: dict[str, Any] = {"memory": {"enabled": True, "retention_days": 180}, "history_days": 30}
EVENTS_ANONYMOUS_AFTER = timedelta(days=90)


async def settings(session: AsyncSession) -> dict[str, Any]:
    raw = await settings_service.get_value(session, SETTINGS_KEY)
    try:
        stored = json.loads(raw) if isinstance(raw, str) and raw else {}
    except json.JSONDecodeError:
        stored = {}
    mem = {**DEFAULTS["memory"], **(stored.get("memory") or {})}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k != "memory"}, "memory": mem}


async def save_settings(session: AsyncSession, value: dict[str, Any]) -> dict[str, Any]:
    current = await settings(session)
    current["memory"] = {**current["memory"], **(value.get("memory") or {})}
    if "history_days" in value:
        current["history_days"] = value["history_days"]
    await settings_service.set_value(session, SETTINGS_KEY, json.dumps(current, sort_keys=True))
    return current


async def user_enabled(session: AsyncSession, user_id: int) -> bool:
    return (await get_user_value(session, user_id, USER_KEY)) != "off"


async def state(session: AsyncSession, user: User) -> dict[str, Any]:
    st = await settings(session)
    async with rls.system_scope(session):
        count = (
            await session.execute(select(func.count(HelperNote.id)).where(HelperNote.user_id == user.id))
        ).scalar_one()
    return {
        "institution_enabled": bool(st["memory"]["enabled"]),
        "enabled": bool(st["memory"]["enabled"]) and await user_enabled(session, user.id),
        "notes": int(count),
        "max_notes": MAX_NOTES,
        "max_chars": MAX_CHARS,
        "retention_days": int(st["memory"]["retention_days"]),
        "history_days": int(st["history_days"]),
    }


async def set_user_enabled(session: AsyncSession, user: User, enabled: bool) -> None:
    await set_user_value(session, user.id, USER_KEY, "on" if enabled else "off")
    await session.commit()


def note_out(x: HelperNote) -> dict[str, Any]:
    return {
        "id": x.id,
        "text": x.text,
        "source": x.source,
        "created_at": x.created_at.isoformat(),
        "last_used_at": x.last_used_at.isoformat(),
        "expires_at": x.expires_at.isoformat(),
    }


async def list_notes(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    q = select(HelperNote).where(HelperNote.user_id == user.id).order_by(HelperNote.id)
    return [note_out(x) for x in (await session.execute(q)).scalars()]


async def _names_another_person(session: AsyncSession, user: User, text: str) -> bool:
    """Whether ``text`` contains the name of an account or instructor other than the author (Turkish-folded, whole
    words; the same matcher as the AI redactor, ``app/ai/personal.py``)."""
    from app.ai.personal import Redactor

    people: list[tuple[str, list[str]]] = []
    async with rls.system_scope(session):
        users = (await session.execute(select(User).where(User.id != user.id))).scalars().all()
        instructors = (
            (
                await session.execute(
                    select(Instructor).where((Instructor.user_id.is_(None)) | (Instructor.user_id != user.id))
                )
            )
            .scalars()
            .all()
        )
    for u in users:
        variants = [u.full_name or "", f"{u.firstname or ''} {u.lastname or ''}"]
        variants = [v for v in (n.clean_text(x) or "" for x in variants) if len(v.split()) >= 2]
        if variants:
            people.append((variants[0], variants))
    for ins in instructors:
        v = n.clean_text(ins.full_name) or ""
        if len(v.split()) >= 2:
            people.append((v, [v]))
    if not people:
        return False
    return Redactor(people).text(text) != text


async def add_note(session: AsyncSession, user: User, text: str, source: str) -> dict[str, Any]:
    if source not in ("user_button", "user_confirmed"):
        raise ActionRefused(422, "source", "Not yalnızca sizin onayınızla kaydedilir.", "A note is saved only by you.")
    st = await state(session, user)
    if not st["institution_enabled"]:
        raise ActionRefused(
            409,
            "memory_off_institution",
            "Yardımcı belleği kurumunuzda kapalı.",
            "Helper memory is switched off for your institution.",
        )
    if not st["enabled"]:
        raise ActionRefused(
            409,
            "memory_off",
            "Yardımcı belleğiniz kapalı; Profil › Yardımcı'dan açabilirsiniz.",
            "Your helper memory is off; switch it on in Profile › Helper.",
        )
    clean = " ".join((n.clean_text(text) or "").split())
    if not clean:
        raise ActionRefused(422, "empty", "Not boş olamaz.", "The note cannot be empty.")
    if len(clean) > MAX_CHARS:
        raise ActionRefused(
            422,
            "too_long",
            f"Not en fazla {MAX_CHARS} karakter olabilir.",
            f"A note can be at most {MAX_CHARS} characters.",
        )
    if st["notes"] >= MAX_NOTES:
        raise ActionRefused(
            409,
            "too_many",
            f"En fazla {MAX_NOTES} not saklanır; önce birini silin.",
            f"At most {MAX_NOTES} notes are kept; delete one first.",
        )
    if await _names_another_person(session, user, clean):
        raise ActionRefused(
            422,
            "names_a_person",
            "Notlar yalnızca sizin tercihleriniz içindir; başka birinin adını içeremez.",
            "Notes are for your own preferences; they cannot name another person.",
        )
    now = utcnow()
    note = HelperNote(
        user_id=user.id,
        text=clean,
        source=source,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=int(st["retention_days"])),
    )
    session.add(note)
    await session.commit()
    return note_out(note)


async def delete_note(session: AsyncSession, user: User, note_id: int) -> None:
    res = await session.execute(
        delete(HelperNote)
        .where(HelperNote.id == note_id, HelperNote.user_id == user.id)
        .execution_options(synchronize_session=False)
    )
    if not getattr(res, "rowcount", 0):
        raise ActionRefused(404, "not_found", "Not bulunamadı.", "Note not found.")
    await session.commit()


async def delete_all(session: AsyncSession, user: User, *, history: bool = False) -> dict[str, int]:
    out = {"notes": 0, "threads": 0}
    res = await session.execute(
        delete(HelperNote).where(HelperNote.user_id == user.id).execution_options(synchronize_session=False)
    )
    out["notes"] = int(getattr(res, "rowcount", 0) or 0)
    if history:
        await session.execute(
            delete(HelperMessage).where(HelperMessage.user_id == user.id).execution_options(synchronize_session=False)
        )
        res = await session.execute(
            delete(HelperThread).where(HelperThread.user_id == user.id).execution_options(synchronize_session=False)
        )
        out["threads"] = int(getattr(res, "rowcount", 0) or 0)
    await session.commit()
    return out


async def on_ai_personal_withdrawn(session: AsyncSession, user_id: int) -> int:
    """``kvkk.withdraw(ai_personal)``: delete the notes and turn the person's memory off (no commit: the caller's)."""
    async with rls.system_scope(session):
        res = await session.execute(
            delete(HelperNote).where(HelperNote.user_id == user_id).execution_options(synchronize_session=False)
        )
    await set_user_value(session, user_id, USER_KEY, "off")
    return int(getattr(res, "rowcount", 0) or 0)


async def purge(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Daily (``kvkk.purge_expired``): notes past their 180 days since last use, threads older than the history
    window, and the person's id on telemetry older than 90 days. Runs in the system scope; no commit."""
    now = now or utcnow()
    st = await settings(session)
    out: dict[str, int] = {}
    async with rls.system_scope(session):
        res = await session.execute(
            delete(HelperNote).where(HelperNote.expires_at <= now).execution_options(synchronize_session=False)
        )
        out["helper_notes"] = int(getattr(res, "rowcount", 0) or 0)
        cutoff = now - timedelta(days=int(st["history_days"]))
        old = select(HelperThread.id).where(HelperThread.last_at < cutoff)
        await session.execute(
            delete(HelperMessage).where(HelperMessage.thread_id.in_(old)).execution_options(synchronize_session=False)
        )
        res = await session.execute(
            delete(HelperThread).where(HelperThread.last_at < cutoff).execution_options(synchronize_session=False)
        )
        out["helper_threads"] = int(getattr(res, "rowcount", 0) or 0)
        res = await session.execute(
            update(HelperEvent)
            .where(HelperEvent.ts < now - EVENTS_ANONYMOUS_AFTER, HelperEvent.user_id.is_not(None))
            .values(user_id=None)
            .execution_options(synchronize_session=False)
        )
        out["helper_events_anonymised"] = int(getattr(res, "rowcount", 0) or 0)
    return out


async def dsr_rows(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """The person's notes, conversations and helper actions for the DSR export (``helper``): one list of rows, each
    with its ``kind`` (``note`` / ``thread`` / ``action``), like the export's other data classes."""
    async with rls.system_scope(session):
        notes = (
            (await session.execute(select(HelperNote).where(HelperNote.user_id == user_id).order_by(HelperNote.id)))
            .scalars()
            .all()
        )
        threads = (
            (
                await session.execute(
                    select(HelperThread).where(HelperThread.user_id == user_id).order_by(HelperThread.id)
                )
            )
            .scalars()
            .all()
        )
        messages = (
            (
                await session.execute(
                    select(HelperMessage).where(HelperMessage.user_id == user_id).order_by(HelperMessage.id)
                )
            )
            .scalars()
            .all()
        )
        actions = (
            (
                await session.execute(
                    select(HelperActionInvocation)
                    .where(HelperActionInvocation.user_id == user_id)
                    .order_by(HelperActionInvocation.id)
                )
            )
            .scalars()
            .all()
        )
    by_thread: dict[int, list[dict[str, Any]]] = {}
    for m in messages:
        by_thread.setdefault(m.thread_id, []).append({"role": m.role, "text": m.text, "created_at": m.created_at})
    rows: list[dict[str, Any]] = [{"kind": "note", **note_out(x)} for x in notes]
    rows += [
        {
            "kind": "thread",
            "title": t.title,
            "created_at": t.created_at,
            "last_at": t.last_at,
            "messages": by_thread.get(t.id, []),
        }
        for t in threads
    ]
    rows += [
        {
            "kind": "action",
            "action": a.action,
            "status": a.status,
            "entity": a.entity_type,
            "entity_id": a.entity_id,
            "created_at": a.created_at,
            "done_at": a.done_at,
        }
        for a in actions
    ]
    return rows


async def erase(session: AsyncSession, user_id: int) -> int:
    """KVKK erasure: the person's notes, threads, messages and helper action rows (the audit log keeps its own
    entries under its retention policy); telemetry keeps its rows without the person."""
    total = 0
    async with rls.system_scope(session):
        for model in (HelperNote, HelperMessage, HelperThread, HelperActionInvocation):
            res = await session.execute(
                delete(model).where(model.user_id == user_id).execution_options(synchronize_session=False)
            )
            total += int(getattr(res, "rowcount", 0) or 0)
        await session.execute(
            update(HelperEvent)
            .where(HelperEvent.user_id == user_id)
            .values(user_id=None)
            .execution_options(synchronize_session=False)
        )
    return total


__all__ = [
    "MAX_CHARS",
    "MAX_NOTES",
    "add_note",
    "delete_all",
    "delete_note",
    "dsr_rows",
    "erase",
    "list_notes",
    "on_ai_personal_withdrawn",
    "purge",
    "save_settings",
    "set_user_enabled",
    "settings",
    "state",
]
