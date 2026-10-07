"""Async SQLAlchemy engine/session factory. SQLite (aiosqlite) in dev/tests, Postgres (psycopg) in prod."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _make_engine(url: str) -> AsyncEngine:
    kwargs: dict[str, object] = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(url, **kwargs)  # type: ignore[arg-type]
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _make_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


def configure_engine(url: str) -> AsyncEngine:
    """Re-point the global engine (used by tests and the CLI)."""
    global _engine, _session_factory
    _engine = _make_engine(url)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def create_all() -> None:
    from app.models.base import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
