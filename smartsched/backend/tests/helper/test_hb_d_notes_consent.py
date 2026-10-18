"""HX-17 / orchestrator decision 2026-10-18: ``POST /helper/notes`` ("Not ekle" in Profil › Yardımcı) needs the
``ai_personal`` consent too, exactly like the helper's "Bunu hatırla" card. Without it the note is refused with the
same code and the same TR/EN text the remember card uses (``consent_missing``), and nothing is saved; with it the note
is saved as before."""

from __future__ import annotations

from app.ai.helper.memory import CONSENT_MISSING
from app.core import db as dbmod
from app.models.helper import HelperNote
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, grant_ai_personal, personas


async def _notes(uid: int) -> int:
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count(HelperNote.id)).where(HelperNote.user_id == uid))).scalar_one())


async def test_hb_d_add_note_needs_ai_personal_consent(env) -> None:  # noqa: F811
    t = (await personas(env))["teacher"]
    body = {"text": "Tercih edilen bina: B blok", "source": "user_confirmed"}
    r = await env.client.post(f"{H}/notes", json=body, headers=t.headers)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "consent_missing"
    assert (detail["message_tr"], detail["message_en"]) == CONSENT_MISSING
    assert await _notes(t.uid) == 0
    await grant_ai_personal(env, t)
    r = await env.client.post(f"{H}/notes", json=body, headers=t.headers)
    assert r.status_code == 201, r.text
    assert await _notes(t.uid) == 1
    # withdrawn again: refused again (and the withdrawal already deleted the note)
    assert (await env.client.delete("/api/v1/me/consents/ai_personal", headers=t.headers)).status_code == 200
    r = await env.client.post(f"{H}/notes", json=body, headers=t.headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] in ("consent_missing", "memory_off"), r.text
    assert await _notes(t.uid) == 0
