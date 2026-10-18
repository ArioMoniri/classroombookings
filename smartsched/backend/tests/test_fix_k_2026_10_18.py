"""FIX-K (round 4, 2026-10-18): the open e2e-a / e2e-a2 / e2e-b minors on the backend.

- E2EA-F07: PUT /constraints/{id} with ``params`` that drop a rule's ``event_ids`` / ``kinds`` would make a
  one-exam rule term-wide; it is refused (422 ``rule_scope_lost``), the rule unchanged.
"""

from __future__ import annotations

from tests.api_fixtures import client, login  # noqa: F401


async def test_e2ea_f07_replacing_params_never_widens_a_scoped_rule(client):  # noqa: F811
    h = await login(client)
    term = (await client.post("/api/v1/terms", json={"code": "2026-FINAL", "name": "Final"}, headers=h)).json()
    params = {"event_ids": [426], "kinds": ["exam"], "buildings": ["A", "C"]}
    rule = await client.post(
        "/api/v1/constraints",
        json={"term_id": term["id"], "kind": "building_preference", "params": params, "hardness": "soft", "nl_text": "x"},
        headers=h,
    )
    assert rule.status_code in (200, 201), rule.text
    rid = rule.json()["id"]
    r = await client.put(f"/api/v1/constraints/{rid}", json={"params": {"buildings": ["A"]}, "hardness": "hard"}, headers=h)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "rule_scope_lost" and "event_ids" in detail["message"] and detail["message_tr"]
    got = next(x for x in (await client.get("/api/v1/constraints", params={"term_id": term["id"]}, headers=h)).json() if x["id"] == rid)
    assert got["params"] == params and got["hardness"] == "soft"
    # keeping the scope and changing the rest is fine
    ok = await client.put(
        f"/api/v1/constraints/{rid}", json={"params": {**params, "buildings": ["A"]}, "hardness": "hard"}, headers=h
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["params"]["event_ids"] == [426]
