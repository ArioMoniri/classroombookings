"""Helpers for API tests: app client bound to a temp SQLite file, seeded admin, login headers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import Base
from app.services.seed import seed_admin
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def login(client: AsyncClient, email: str = "admin@example.com", password: str = "admin1234") -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
