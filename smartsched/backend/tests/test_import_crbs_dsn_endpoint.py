"""Review D16 at the call site: ``POST /imports/crbs`` with a live ``dsn`` goes through ``crbs_dsn.check_dsn``
(planning admins only, allow-listed hosts only); SQL dump uploads are not affected."""

from __future__ import annotations

from tests.crbs_env import env  # noqa: F401

DSN = "mysql://crbs:x@10.0.0.5/classroombookings"


async def test_live_dsn_is_admin_only_and_allow_listed(env) -> None:  # noqa: F811
    _, planner = await env.user("planlama.dsn@uni.edu.tr", role="PLANNER")
    r = await env.client.post("/api/v1/imports/crbs", data={"dsn": DSN}, headers=planner)
    assert r.status_code == 403, r.text
    r = await env.client.post("/api/v1/imports/crbs", data={"dsn": DSN}, headers=env.admin)
    assert r.status_code == 422 and "crbs_dsn_allowed_hosts" in r.text  # nothing allow-listed yet
    r = await env.client.post("/api/v1/imports/crbs", data={"dsn": "mysql://x@127.0.0.1/db?unix_socket=/s"}, headers=env.admin)
    assert r.status_code == 422
    jobs = (await env.client.get("/api/v1/imports", params={"kind": "crbs"}, headers=env.admin)).json()
    assert jobs == []  # a refused DSN creates no job
