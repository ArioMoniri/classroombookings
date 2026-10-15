"""Admin persona 2026-10-15 M-47 (D1 bypass): an empty or blank selector names no class.

``{"match": ""}``, ``{"match": " "}`` and ``{"event_ids": []}`` on a soft structural rule used to pass the guard
because it looked at key presence only, while the solver's ``select_events`` treats an empty selector as "every
event" (and a blank match as a substring of nearly every label). The guard now counts a selector only when it
has a non-blank value (NBSP and other Unicode spaces count as blank). Exact repro bodies:
``EV/curl/d1-guard-bypass.txt`` D1-f, D1-g, D1-i. Runs on the real Bahar 2026 import; MAT 112 is a real
Bahar planning-list course.
"""

from __future__ import annotations

import pytest
from app.services.constraint_guard import is_targeted_params, is_waiver

from tests.crbs_env import env  # noqa: F401

C = "/api/v1/constraints"
UNTARGETED = (
    {"match": ""},  # D1-f
    {"event_ids": []},  # D1-g
    {"match": " "},  # D1-i
    {"match": "\u00a0"},  # NBSP pasted from Excel
    {"match": ["", " \t"]},
    {"cohort": "", "cohorts": [], "program": "  ", "programs": [""], "instructor": "\u200b", "instructors": []},
    {"event_ids": [], "_source_ref": {"row": 12}},
)
TARGETED = (
    {"match": "MAT 112"},
    {"match": ["", "MAT 112"]},
    {"event_ids": [1]},
    {"cohort": "PROG:Psikoloji:Y1"},
    {"instructors": ["INS:ilker şahin"]},
)


@pytest.mark.parametrize("params", UNTARGETED)
async def test_planner_cannot_waive_capacity_with_an_empty_selector(env, params):  # noqa: F811
    body = {"term_id": env.term_id, "kind": "capacity", "params": params, "hardness": "soft", "weight": 5}
    r = await env.client.post(C, json=body, headers=env.planner)
    assert r.status_code == 422, (params, r.text)
    assert "structural" in str(r.json()["detail"])


async def test_planner_cannot_untarget_an_existing_rule_with_an_empty_selector(env):  # noqa: F811
    body = {"term_id": env.term_id, "kind": "capacity", "params": {"match": "MAT 112"}, "hardness": "soft"}
    r = await env.client.post(C, json={**body, "weight": 5}, headers=env.planner)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    for params in ({"match": ""}, {"event_ids": []}, {"match": " "}):
        r = await env.client.put(f"{C}/{rid}", json={"params": params}, headers=env.planner)
        assert r.status_code == 422, (params, r.text)
    row = next(x for x in (await env.client.get(C, params={"term_id": env.term_id}, headers=env.planner)).json() if x["id"] == rid)
    assert row["params"] == {"match": "MAT 112"}


def test_selector_predicate():
    for params in UNTARGETED:
        assert not is_targeted_params(params), params
        assert is_waiver("capacity", params, "soft"), params
        assert not is_waiver("capacity", params, "hard"), params
    for params in TARGETED:
        assert is_targeted_params(params), params
        assert not is_waiver("room_tags", params, "soft"), params
