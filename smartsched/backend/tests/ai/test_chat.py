"""Chat on a run: proposals only until /apply; apply validates with the solver and creates a child run."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Assignment, ChatMessage, ConstraintRow, ScheduleRun
from app.workers.queue import get_queue
from sqlalchemy import func, select

from tests.ai.conftest import empty_params, empty_selector, proposal, seed_small, store_key, text, tool, tools
from tests.api_fixtures import login


async def _setup(client):
    h = await login(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
        await store_key(s)
    return h, sd


async def _rows(run_id: int) -> list[Assignment]:
    async with get_session_factory()() as s:
        return list(
            (await s.execute(select(Assignment).where(Assignment.run_id == run_id).order_by(Assignment.id))).scalars()
        )


async def _count(model) -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


def _move(aid: int, room: str, day: int = 0, start: int = 0) -> dict:
    return {
        "assignment_id": aid,
        "day": day,
        "start_period": start,
        "end_period": 0,
        "room_codes": [room],
        "weeks": [],
        "reason": "test",
    }


async def test_chat_proposes_but_never_applies(client, fake_sdk):
    h, sd = await _setup(client)
    before = [(a.day, a.start_period, a.room_ids) for a in await _rows(sd.run_id)]
    fake_sdk.script = [
        tool("find_assignments", {"query": "PHAR 240", "room_code": "", "day": 0, "week": 0, "limit": 10}),
        tools(
            ("move_event", _move(sd.assignments["PHAR240"], "A 101")),  # 50 students into 20 seats
            ("move_event", _move(sd.assignments["NRS450"], "A 206")),
        ),
        text("PHAR 240'ı A 101'e, NRS 450'yi A 206'ya taşımayı öneriyorum."),
    ]
    r = await client.post(
        f"/api/v1/runs/{sd.run_id}/chat",
        json={"message": "PHAR 240 A 101'e, NRS 450 A 206'ya", "lang": "tr"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    diff = out["proposed_diff"]
    assert [op["op"] for op in diff["operations"]] == ["move", "move"]
    assert diff["operations"][0]["room_ids"] == [sd.rooms["A101"]]
    assert out["usage"]["requests"] == 3 and out["usage"]["input_tokens"] == 360

    # what we sent: strict tools, auto tool choice (no forced tool use on Opus 5.5), run context cached
    first = fake_sdk.calls[0]
    assert all(t["strict"] for t in first["tools"])
    assert first["tool_choice"]["type"] == "auto"
    assert any(b.get("cache_control") for b in first["system"])
    assert "Run #" in first["system"][-1]["text"]
    # the read tool result went back with real data
    tool_result = fake_sdk.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "PHAR 240" in tool_result["content"]

    # nothing applied: same assignments, no child run, diff stored on the assistant message
    assert [(a.day, a.start_period, a.room_ids) for a in await _rows(sd.run_id)] == before
    assert await _count(ScheduleRun) == 1
    hist = (await client.get(f"/api/v1/runs/{sd.run_id}/chat", headers=h)).json()
    assert [m["role"] for m in hist] == ["user", "assistant"]
    stored = [tc for tc in hist[1]["tool_calls"] if tc.get("type") == "diff"]
    assert stored and stored[0]["diff"]["id"] == diff["id"] and stored[0]["applied"] is None
    assert any(tc.get("type") == "usage" for tc in hist[1]["tool_calls"])

    # apply: capacity-violating move rejected, valid move accepted -> child run
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/apply", json={"diff_id": diff["id"]}, headers=h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["mode"] == "patch" and res["child_run_id"]
    assert [x["index"] for x in res["applied"]] == [1]
    assert res["rejected"][0]["index"] == 0 and any("capacity" in reason for reason in res["rejected"][0]["reasons"])
    assert res["hard_score"] == 100 and res["status"] == "FEASIBLE"

    child = (await client.get(f"/api/v1/runs/{res['child_run_id']}", headers=h)).json()
    assert child["parent_run_id"] == sd.run_id and child["prompt_text"].startswith("PHAR 240")
    rows = {a.meeting_request_id: a for a in await _rows(res["child_run_id"])}
    nrs = rows[sd.mr["NRS450"]]
    assert (nrs.day, nrs.start_period, nrs.room_ids, nrs.origin) == (3, 5, [sd.rooms["A206"]], "AI_EDIT")
    phar = rows[sd.mr["PHAR240"]]
    assert phar.room_ids == [sd.rooms["A206"]] and phar.origin == "SOLVER"
    # parent untouched
    assert [(a.day, a.start_period, a.room_ids) for a in await _rows(sd.run_id)] == before

    # a diff applies once
    again = await client.post(f"/api/v1/runs/{sd.run_id}/chat/apply", json={"diff_id": diff["id"]}, headers=h)
    assert again.status_code == 409


async def test_move_to_another_day_of_a_fixed_request_is_rejected_with_hint(client, fake_sdk):
    h, sd = await _setup(client)
    diff = {
        "id": "d1",
        "run_id": sd.run_id,
        "operations": [{"op": "move", "assignment_id": sd.assignments["NRS450"], "day": 4}],
    }
    res = (await client.post(f"/api/v1/runs/{sd.run_id}/chat/apply", json={"diff": diff}, headers=h)).json()
    assert res["child_run_id"] is None and res["status"] == "REJECTED"
    assert any("set_section_field" in reason for reason in res["rejected"][0]["reasons"])
    assert await _count(ScheduleRun) == 1  # nothing created when every op fails


async def test_unknown_ids_from_the_model_are_reported_not_recorded(client, fake_sdk):
    h, sd = await _setup(client)
    fake_sdk.script = [
        tools(
            ("move_event", _move(987654, "A 206")),
            ("remove_constraint", {"constraint_id": 4242, "reason": "x"}),
            ("move_event", _move(sd.assignments["PSI101"], "Q 999")),
        ),
        text("Bu atamaları bulamadım."),
    ]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat", json={"message": "taşı", "lang": "tr"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["proposed_diff"] is None
    results = fake_sdk.calls[1]["messages"][-1]["content"]
    assert len(results) == 3 and all(x.get("is_error") for x in results)


async def test_constraint_add_and_resolve_runs_repair(client, fake_sdk):
    h, sd = await _setup(client)
    fake_sdk.script = [
        tools(
            (
                "add_constraint",
                proposal(
                    "room_forbid",
                    "hard",
                    selector=empty_selector(course_codes=["PSI 101"]),
                    params=empty_params(room_codes=["A 204"]),
                    nl_text="PSI 101 A 204'te olmasın",
                ),
            ),
            ("re_solve", {"stability": True, "reason": "kural değişti"}),
        ),
        text("PSI 101 için A 204 yasağı ve kararlı yeniden çözüm öneriyorum."),
    ]
    r = await client.post(
        f"/api/v1/runs/{sd.run_id}/chat", json={"message": "PSI 101 A 204'te olmasın", "lang": "tr"}, headers=h
    )
    diff = r.json()["proposed_diff"]
    assert diff["re_solve"] and diff["operations"][0]["constraint"]["status"] == "ok"
    assert await _count(ConstraintRow) == 0  # not created before apply

    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/apply", json={"diff_id": diff["id"]}, headers=h)
    res = r.json()
    assert r.status_code == 200 and res["mode"] == "repair" and res["re_solve_queued"], res
    assert len(res["constraints_created"]) == 1
    await get_queue().wait_idle()
    async with get_session_factory()() as s:
        c = await s.get(ConstraintRow, res["constraints_created"][0])
        assert c.source == "AI" and c.nl_text.startswith("PSI 101") and c.term_id == sd.term_id
        child = await s.get(ScheduleRun, res["child_run_id"])
        assert child.status in ("OPTIMAL", "FEASIBLE"), (child.status, child.error, child.diagnosis)
        assert child.parent_run_id == sd.run_id
    rows = {a.meeting_request_id: a for a in await _rows(res["child_run_id"])}
    assert sd.rooms["A204"] not in rows[sd.mr["PSI101"]].room_ids
    # stability: untouched events keep their place
    assert rows[sd.mr["PHAR240"]].room_ids == [sd.rooms["A206"]]


async def test_edited_diff_is_revalidated(client, fake_sdk):
    """A diff posted back by the browser is not trusted: foreign ids and bad weights are rejected."""
    h, sd = await _setup(client)
    diff = {
        "id": "client-edit",
        "run_id": sd.run_id,
        "operations": [
            {"op": "move", "assignment_id": 999999, "room_ids": [sd.rooms["A206"]]},
            {"op": "set_weight", "constraint_id": 777, "weight": 50},
            {"op": "lock", "assignment_id": sd.assignments["PSI101"]},
        ],
    }
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/apply", json={"diff": diff}, headers=h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert {x["index"] for x in res["rejected"]} == {0, 1} and [x["index"] for x in res["applied"]] == [2]
    rows = {a.meeting_request_id: a for a in await _rows(res["child_run_id"])}
    assert rows[sd.mr["PSI101"]].is_locked and not rows[sd.mr["PHAR240"]].is_locked
    async with get_session_factory()() as s:
        n_msgs = (await s.execute(select(func.count()).select_from(ChatMessage))).scalar_one()
    assert n_msgs == 0 and not fake_sdk.calls  # apply never calls the model
