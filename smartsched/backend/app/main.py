"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import create_all, dispose_engine, get_session_factory
from app.services.seed import seed_admin
from app.workers.queue import get_queue

log = logging.getLogger("smartsched")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.create_tables_on_startup and settings.environment != "prod":
        await create_all()
    async with get_session_factory()() as session:
        await seed_admin(session)
    log.info("SmartSched backend ready (%s, %s)", settings.environment, settings.database_url.split("@")[-1])
    yield
    await get_queue().shutdown()
    await dispose_engine()


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
    app.include_router(api_router, prefix="/api/v1")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")
    return app


app = create_app()
