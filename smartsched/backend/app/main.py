"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import assert_secure, get_settings
from app.core.db import create_all, dispose_engine, get_engine, get_session_factory
from app.services.seed import seed_admin
from app.workers.queue import get_queue, recover_interrupted

log = logging.getLogger("smartsched")


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_upgrade(url: str) -> None:
    """``alembic upgrade head`` in-process (sync; alembic's env.py runs its own event loop)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()  # no ini file: keeps the app's logging configuration intact
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url  # alembic/env.py lets DATABASE_URL override the configured URL
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


async def _schema_drift() -> list[str]:
    """Tables / columns of the ORM models missing in the database (human-readable)."""
    from sqlalchemy import inspect

    from app.models.base import Base

    def check(conn: Any) -> list[str]:
        insp: Any = inspect(conn)
        tables = set(insp.get_table_names())
        out: list[str] = []
        for name, table in Base.metadata.tables.items():
            if name not in tables:
                out.append(f"table {name}")
                continue
            have = {c["name"] for c in insp.get_columns(name)}
            out += [f"column {name}.{c.name}" for c in table.columns if c.name not in have]
        return out

    async with get_engine().connect() as conn:
        return await conn.run_sync(check)


async def init_database(url: str, environment: str) -> str:
    """Dev/test startup schema handling (F1: a dev DB created by ``create_all`` once silently lacked
    columns added later, and every run FAILED).

    * SQLite outside ``test``: a **new** database or one with an ``alembic_version`` table is migrated
      with ``alembic upgrade head``; a legacy ``create_all`` database (tables, no ``alembic_version``)
      gets ``create_all`` for missing tables and a loud warning listing missing columns with the fix.
    * ``test`` (fast in-memory DBs) and non-SQLite dev databases: ``create_all`` as before.

    Returns the strategy used (``migrate`` / ``create_all`` / ``legacy``)."""
    if environment == "test" or not url.startswith("sqlite") or ":memory:" in url:
        await create_all()
        return "create_all"
    from sqlalchemy import inspect

    async with get_engine().connect() as conn:
        tables = set(await conn.run_sync(lambda c: cast(Any, inspect(c)).get_table_names()))
    if not tables or "alembic_version" in tables:
        await asyncio.to_thread(_alembic_upgrade, url)  # alembic/env.py uses the async engine
        drift = await _schema_drift()
        if drift:
            log.warning("database schema differs from the models after migrations: %s", ", ".join(drift[:20]))
        return "migrate"
    await create_all()
    drift = await _schema_drift()
    if drift:
        log.warning(
            "dev database %s was created without migrations and lacks %s; delete it (it is recreated and "
            "migrated on the next start) or run `alembic stamp 0001 && alembic upgrade head`",
            url,
            ", ".join(drift[:20]),
        )
    return "legacy"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    assert_secure(settings)  # review M9: no default / short secrets in prod
    if settings.create_tables_on_startup and settings.environment != "prod":
        await init_database(settings.database_url, settings.environment)
    async with get_session_factory()() as session:
        await seed_admin(session)
    async with get_session_factory()() as session:
        await recover_interrupted(session)  # jobs of a dead process never finish: mark them FAILED
    log.info("SmartSched backend ready (%s, %s)", settings.environment, settings.database_url.split("@")[-1])
    yield
    await get_queue().shutdown()
    await dispose_engine()


def _install_error_handlers(app: FastAPI) -> None:
    """A lost optimistic-concurrency race anywhere (``version_id_col`` rows) is a 409, never a 500."""
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from sqlalchemy.orm.exc import StaleDataError

    async def stale(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "the record changed since you loaded it; reload and retry"}, status_code=409)

    app.add_exception_handler(StaleDataError, stale)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SmartSched API",
        version="0.1.0",
        description="AI classroom optimizer & scheduler: imports, CP-SAT runs, exports.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    # Only room photos are public. Uploaded workbooks (uploads/imports: instructor names, enrolments)
    # are served through the authenticated ``GET /api/v1/imports/{id}/file``.
    photos = Path(settings.upload_dir) / "rooms"
    photos.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads/rooms", StaticFiles(directory=str(photos)), name="room-photos")
    return app


app = create_app()
