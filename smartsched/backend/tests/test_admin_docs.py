"""No-placeholder audit m6 option b (ROADMAP "Docs for ADMIN sessions in prod"): production serves no public
``/api/docs`` or ``/api/openapi.json``; operators get the schema at ``GET /api/v1/admin/openapi.json`` with a
``planning.admin`` session instead of re-opening the public route."""

from __future__ import annotations

from app.core.config import get_settings
from httpx import ASGITransport, AsyncClient

from tests.crbs_env import env  # noqa: F401


async def test_prod_schema_only_for_planning_admins(env, monkeypatch):  # noqa: F811
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "environment", "prod")
    prod = create_app()
    async with AsyncClient(transport=ASGITransport(app=prod), base_url="http://test") as c:
        assert (await c.get("/api/openapi.json")).status_code == 404
        assert (await c.get("/api/v1/admin/openapi.json")).status_code == 401
        assert (await c.get("/api/v1/admin/openapi.json", headers=env.planner)).status_code == 403
        r = await c.get("/api/v1/admin/openapi.json", headers=env.admin)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        spec = r.json()
        assert spec["info"]["title"] == "SmartSched API" and "/api/v1/runs/{run_id}/activate" in spec["paths"]
