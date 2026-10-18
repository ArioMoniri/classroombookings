"""HB-21 (1): "Geçmişi sil" without the notes. ``DELETE /helper/threads`` removes the person's own chat threads and
their messages, keeps every memory note, touches nobody else's history and writes one ``helper.threads_deleted``
audit row (counts only). ``DELETE /helper/notes?history=true`` keeps deleting both."""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent
from app.models.base import utcnow
from app.models.helper import HelperMessage, HelperNote, HelperThread
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import H, grant_ai_personal, personas


async def _thread(uid: int, n: int = 2) -> None:
    async with dbmod.get_session_factory()() as s:
        t = HelperThread(user_id=uid, title="Rezervasyon", created_at=utcnow(), last_at=utcnow())
        s.add(t)
        await s.flush()
        for i in range(n):
            s.add(HelperMessage(thread_id=t.id, user_id=uid, role="user", text=f"soru {i}", cards=[]))
        await s.commit()


async def _count(model, *where) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())


async def test_hb_21_threads_only_delete_keeps_notes(env) -> None:  # noqa: F811
    people = await personas(env)
    t, a = people["teacher"], people["approver"]
    await grant_ai_personal(env, t)  # "Not ekle" needs the ai_personal consent (HX-17)
    r = await env.client.post(
        f"{H}/notes", json={"text": "Tercih edilen bina: B blok", "source": "user_button"}, headers=t.headers
    )
    assert r.status_code == 201, r.text
    await _thread(t.uid, 3)
    await _thread(t.uid, 1)
    await _thread(a.uid, 2)
    r = await env.client.delete(f"{H}/threads", headers=t.headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"threads": 2, "messages": 4, "notes_kept": 1}
    assert await _count(HelperThread, HelperThread.user_id == t.uid) == 0
    assert await _count(HelperMessage, HelperMessage.user_id == t.uid) == 0
    assert await _count(HelperNote, HelperNote.user_id == t.uid) == 1  # the notes stay
    assert await _count(HelperThread, HelperThread.user_id == a.uid) == 1  # nobody else's history
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "helper.threads_deleted"))).scalars().one()
        assert ev.after == {"threads": 2, "messages": 4, "via": "helper"}
    # nothing left: still 200, zero counts
    r = await env.client.delete(f"{H}/threads", headers=t.headers)
    assert r.status_code == 200 and r.json()["threads"] == 0
    # "Tümünü sil" + "Geçmişi sil" is unchanged: both go
    await _thread(t.uid, 1)
    r = await env.client.delete(f"{H}/notes", params={"history": "true"}, headers=t.headers)
    assert r.status_code == 200 and r.json() == {"notes": 1, "threads": 1}
