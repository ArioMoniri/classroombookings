"""Two requests materialise a term's class revisions at the same time (pod CI run #161, ``GET
/calendar/export/options`` answered 500).

The first refresh of a term stores every class occurrence (``calendar_class_revisions``). When two requests do it at
once, the loser either hits the unique ``uid`` (IntegrityError) or, on SQLite WAL, writes from a read snapshot older
than the winner's commit ("database is locked" at once). It rolled back and tried again, but the rollback had
expired the term, the run and the request's user, and the next ``term.id`` lazy-loaded outside the async bridge:
``MissingGreenlet`` from ``create_cursor``, a 500. ``calendar_classes.retry_lost_race`` reloads what the session held
and tries again; the loser then reads the winner's rows and answers like it.
"""

from __future__ import annotations

from datetime import date

from app.core import db as dbmod
from app.models import CalendarClassRevision, ScheduleRun, Term, User
from app.services import calendar_classes as cc
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401


async def _count() -> int:
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(CalendarClassRevision))).scalar_one())


async def test_a_refresh_that_loses_the_race_retries_with_its_objects_reloaded(env, monkeypatch):  # noqa: F811
    assert await _count() == 0
    raced = {"n": 0, "winning": False}

    async def winner() -> None:
        raced["winning"] = True
        async with dbmod.get_session_factory()() as other:
            t = await other.get(Term, env.term_id)
            r = await other.get(ScheduleRun, env.run_id)
            assert t is not None and r is not None
            await cc.persist_revisions(other, t.id, await cc.term_occurrences(other, t, r))
        raced["winning"] = False

    real_persist = cc.persist_revisions

    async def racing_persist(session, term_id, occs, *, exam=False):  # type: ignore[no-untyped-def]
        if raced["winning"] or exam:
            return await real_persist(session, term_id, occs, exam=exam)
        # read the stored rows now (empty the first time), let the winner commit, then write from the stale read
        real_execute = session.execute
        state = {"reads": 0}

        async def execute(stmt, *a, **kw):  # type: ignore[no-untyped-def]
            out = await real_execute(stmt, *a, **kw)
            state["reads"] += 1
            if state["reads"] == 2 and raced["n"] == 0:  # after the two reads, before the inserts
                raced["n"] += 1
                await winner()
            return out

        session.execute = execute
        try:
            return await real_persist(session, term_id, occs, exam=exam)
        finally:
            del session.execute

    monkeypatch.setattr(cc, "persist_revisions", racing_persist)
    async with dbmod.get_session_factory()() as s:
        user = (await s.execute(select(User).order_by(User.id).limit(1))).scalar_one()
        snaps = await cc.snapshots(s, date(2026, 2, 16), date(2026, 6, 30))
        # the loser answered with the winner's rows, and what the request held before is readable (no MissingGreenlet)
        assert raced["n"] == 1 and len(snaps) == 1 and snaps[0].occurrences
        assert user.email
        stored = await _count()
        assert stored >= len(snaps[0].occurrences)
    # nothing was stored twice; a later refresh changes nothing
    async with dbmod.get_session_factory()() as s:
        again = await cc.snapshots(s, date(2026, 2, 16), date(2026, 6, 30))
        assert len(again[0].occurrences) == len(snaps[0].occurrences)
    assert await _count() == stored


async def test_lost_race_only_covers_the_race():  # noqa: D103
    from sqlalchemy.exc import IntegrityError, OperationalError

    assert cc.lost_race(IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed")))
    assert cc.lost_race(OperationalError("INSERT", {}, Exception("database is locked")))
    assert not cc.lost_race(OperationalError("SELECT", {}, Exception("no such table: x")))
