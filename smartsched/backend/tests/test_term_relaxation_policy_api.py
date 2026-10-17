"""Per-term relaxation policy API and the studio's generate param (batch 4, 2026-10-16) on the real Bahar term.

``GET /terms/{id}/relaxation-policy`` reads the setting ``term.<id>.relaxation_policy`` (``source: term``) or the
default (``source: default``); ``PUT`` (administrators, like ``PUT /settings``) stores or clears it with one
``term.relaxation_policy`` audit event. Studio generate takes ``params.relaxation_policy`` (validated); without it
the run uses the term setting."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent
from app.services import run_params as rp
from app.workers.queue import get_queue
from sqlalchemy import select

from tests import studio_support

bahar = studio_support.bahar


async def test_term_policy_get_put_audited_and_studio_generate_param(bahar, stub_solver):
    c, admin, planner, tid = bahar.client, bahar.admin, bahar.planner, bahar.term_id
    url = f"/api/v1/terms/{tid}/relaxation-policy"
    r = await c.get(url, headers=planner)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "term_id": tid,
        "policy": "lock_first",
        "source": "default",
        "default": "lock_first",
        "options": ["lock_first", "most_classes_first"],
        "stored_invalid": False,
    }
    assert (await c.put(url, json={"policy": "most_classes_first"}, headers=planner)).status_code == 403
    assert (await c.put(url, json={"policy": "fewest_first"}, headers=admin)).status_code == 422
    r = await c.put(url, json={"policy": "most_classes_first"}, headers=admin)
    assert r.status_code == 200, r.text
    assert (r.json()["policy"], r.json()["source"]) == ("most_classes_first", "term")
    assert (await c.get(url, headers=planner)).json()["source"] == "term"
    async with get_session_factory()() as s:
        assert await rp.term_relaxation_policy(s, tid) == ("most_classes_first", "term")  # the same settings key
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "term.relaxation_policy"))).scalars()
        ev = list(ev)
    assert len(ev) == 1 and ev[0].before == {"policy": "lock_first", "source": "default"}
    assert ev[0].after == {"policy": "most_classes_first", "source": "term"} and ev[0].term_id == tid
    assert (await c.get("/api/v1/terms/999999/relaxation-policy", headers=planner)).status_code == 404

    # studio: an explicit policy per generate; a bad one is refused on the draft and on generate
    studio = f"/api/v1/terms/{tid}/studio"
    await c.get(studio, headers=planner)
    r = await c.put(
        studio,
        json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}, "params": {"relaxation_policy": "x"}},
        headers=planner,
    )
    assert r.status_code == 422
    r = await c.post(f"{studio}/generate", json={"params": {"relaxation_policy": "nope"}}, headers=planner)
    assert r.status_code == 422 and "relaxation_policy" in r.text
    r = await c.put(studio, json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}}, headers=planner)
    assert r.status_code == 200, r.text
    r = await c.post(
        f"{studio}/generate", json={"params": {"solver": "cpsat", "relaxation_policy": "lock_first"}}, headers=planner
    )
    assert r.status_code == 202, r.text
    explicit = r.json()["run_id"]
    # null = the term setting (the param is dropped, the bridge reads term.<id>.relaxation_policy)
    r = await c.post(f"{studio}/generate", json={"params": {"relaxation_policy": None}}, headers=planner)
    assert r.status_code == 202, r.text
    inherited = r.json()["run_id"]
    await get_queue().wait_idle(timeout=300)
    one = (await c.get(f"/api/v1/runs/{explicit}", headers=planner)).json()
    two = (await c.get(f"/api/v1/runs/{inherited}", headers=planner)).json()
    assert one["params"]["relaxation_policy"] == "lock_first" and "relaxation_policy" not in two["params"]
    assert one["stats"]["relaxation_policy"]["policy"] == "lock_first"
    assert one["stats"]["relaxation_policy"]["source"] == "run"
    assert two["stats"]["relaxation_policy"] == {**two["stats"]["relaxation_policy"], "policy": "most_classes_first"}
    assert two["stats"]["relaxation_policy"]["source"] == "term"

    # clearing the term setting: back to the default
    r = await c.put(url, json={"policy": None}, headers=admin)
    assert r.status_code == 200 and (r.json()["policy"], r.json()["source"]) == ("lock_first", "default")
