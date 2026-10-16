"""Round-1 admin blocker R1-M-01: a dry-run conflict apply (which rolls back) crashed with
``_after_rollback() takes 1 positional argument but 2 were given`` because SQLAlchemy's
``after_soft_rollback`` passes ``(session, previous_transaction)``."""

from __future__ import annotations

from app.workers import integrations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def test_kick_after_commit_survives_a_rollback_and_clears_its_flag() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(text("select 1"))
            integrations.kick_after_commit(session)
            assert session.sync_session.info.get(integrations.KEY)
            await session.rollback()  # used to raise TypeError from the listener
            assert integrations.KEY not in session.sync_session.info
            # a later unit of work in the same session can register again
            await session.execute(text("select 1"))
            integrations.kick_after_commit(session)
            assert session.sync_session.info.get(integrations.KEY)
            await session.rollback()
    finally:
        await engine.dispose()
