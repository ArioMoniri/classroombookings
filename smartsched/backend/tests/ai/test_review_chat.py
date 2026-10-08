"""Review M2: concurrent applies of one chat diff create exactly one child run."""

from __future__ import annotations

import asyncio

from app.models import ChatApplyClaim, ScheduleRun

from tests.ai.conftest import text, tools
from tests.ai.test_chat import _count, _move, _setup


async def test_m2_concurrent_applies_claim_once(client, fake_sdk):
    h, sd = await _setup(client)
    fake_sdk.script = [
        tools(("move_event", _move(sd.assignments["NRS450"], "A 206"))),
        text("NRS 450'yi A 206'ya taşımayı öneriyorum."),
    ]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat", json={"message": "NRS 450 A 206", "lang": "tr"}, headers=h)
    diff_id = r.json()["proposed_diff"]["id"]
    url = f"/api/v1/runs/{sd.run_id}/chat/apply"
    res = await asyncio.gather(*(client.post(url, json={"diff_id": diff_id}, headers=h) for _ in range(5)))
    codes = sorted(x.status_code for x in res)
    assert codes == [200, 409, 409, 409, 409], [x.text for x in res]
    assert await _count(ScheduleRun) == 2  # parent + one child
    assert await _count(ChatApplyClaim) == 1
    winner = next(x.json() for x in res if x.status_code == 200)
    again = await client.post(url, json={"diff_id": diff_id}, headers=h)
    assert again.status_code == 409 and str(winner["child_run_id"]) in again.json()["detail"]


async def test_m2_rejected_apply_releases_the_claim(client, fake_sdk):
    h, sd = await _setup(client)
    fake_sdk.script = [
        tools(("move_event", _move(sd.assignments["PHAR240"], "A 101"))),  # 50 students into 20 seats
        text("PHAR 240 A 101'e."),
    ]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat", json={"message": "PHAR 240 A 101", "lang": "tr"}, headers=h)
    diff_id = r.json()["proposed_diff"]["id"]
    url = f"/api/v1/runs/{sd.run_id}/chat/apply"
    first = await client.post(url, json={"diff_id": diff_id}, headers=h)
    assert first.status_code == 200 and first.json()["status"] == "REJECTED"
    assert await _count(ChatApplyClaim) == 0  # nothing was applied: the planner may retry
