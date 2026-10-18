"""HB-21 (2): ``GET /ai/faculty/usage`` says how much of the allowance is used, as ``share_of_allowance`` (0..1) for
the faculty and each department, so the UI can say "payın %25'i" instead of token counts. The larger of the token
and cost shares counts; above the allowance it stays 1; ``null`` without an allowance."""

from __future__ import annotations

import pytest
from app.services import ai_usage as meter

from tests.ai.test_hb_11_faculty import U, _limits, _world
from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _reset():
    meter.reset_state()
    yield
    meter.reset_state()


async def test_hb_21_share_of_allowance(client):
    w = await _world(client)
    await _limits(
        w,
        client,
        faculties={str(w["f1"]): {"monthly_tokens": 2000, "managers": [w["dekan"]]}},
        departments={str(w["p1"]): {"monthly_tokens": 200}, str(w["p2"]): {"monthly_tokens": 800}},
    )
    h = await login(client, "dekan@uni.edu.tr", "parola-1234")
    body = (await client.get(U, headers=h)).json()
    assert body["faculty"]["share_of_allowance"] == 0.25  # 500 of 2000
    deps = {d["name"]: d["share_of_allowance"] for d in body["by_department"]}
    assert deps == {"Eczacılık": 1.0, "Farmakoloji": 0.25}  # 300 of 200 stays 1; 200 of 800
    # no allowance: null, never a division by zero
    await _limits(w, client, faculties={str(w["f1"]): {"managers": [w["dekan"]]}}, departments={})
    body = (await client.get(U, headers=h)).json()
    assert body["faculty"]["share_of_allowance"] is None
    assert all(d["share_of_allowance"] is None for d in body["by_department"])
