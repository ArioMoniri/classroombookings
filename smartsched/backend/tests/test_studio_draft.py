"""Studio draft: round trip + optimistic concurrency, per-draft exclusions and built-in switches,
on the real Bahar 2026 import."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ConstraintRow, StudioDraft
from app.services.studio import build_draft_input, build_solver_input_for_draft
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import bahar_counts, meeting_id

bahar = studio_support.bahar


async def _draft(term_id: int, email: str = "planner@example.com") -> StudioDraft:
    from app.models import User

    async with get_session_factory()() as s:
        uid = (await s.execute(select(User.id).where(User.email == email))).scalar_one()
        return (
            await s.execute(select(StudioDraft).where(StudioDraft.term_id == term_id, StudioDraft.user_id == uid))
        ).scalar_one()


async def test_draft_round_trip_and_version_conflict(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    r = await c.get(url, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "COURSE" and d["version"] == 1 and d["etag"] == '"1"'
    weeks = (await bahar_counts(bahar.term_id))["weeks"]
    assert d["scope"]["horizon"] == "TERM" and d["scope"]["weeks"] == list(range(1, weeks + 1))
    assert d["excluded_event_ids"] == [] and d["disabled_builtin_kinds"] == [] and d["pins"] == []
    phar240 = await meeting_id("PHAR 240", day=1, start=1)  # Mon P1-P3, LOCKED in A 206
    body = {
        "version": 1,
        "horizon": "WEEK",
        "horizon_params": {"weeks": [3]},
        "excluded_event_ids": [phar240],
        "last_step": "classes",
        "params": {"time_limit_s": 20, "seed": 3},
    }
    r = await c.put(url, json=body, headers=h)
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["version"] == 2 and d2["excluded_event_ids"] == [phar240] and d2["scope"]["weeks"] == [3]
    assert d2["last_step"] == "classes" and d2["params"]["seed"] == 3
    assert (await c.get(url, headers=h)).json() == d2
    # idempotent: the same body against the current version changes nothing
    r = await c.put(url, json={**body, "version": 2}, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 2
    # stale writer gets 409 with the current draft
    r = await c.put(url, json={**body, "version": 1, "excluded_event_ids": []}, headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["current"]["version"] == 2
    # If-Match works too
    r = await c.put(url, json={"excluded_event_ids": []}, headers={**h, "If-Match": '"1"'})
    assert r.status_code == 409
    r = await c.put(url, json={"excluded_event_ids": []}, headers={**h, "If-Match": '"2"'})
    assert r.status_code == 200 and r.json()["version"] == 3 and r.json()["excluded_event_ids"] == []
    # ids are validated against the term
    r = await c.put(url, json={"version": 3, "excluded_event_ids": [987654]}, headers=h)
    assert r.status_code == 422 and "987654" in r.text
    # drafts are per user: the admin's draft is untouched
    assert (await c.get(url, headers=bahar.admin)).json()["version"] == 1
    # a PLANNER may not switch built-in rules off
    r = await c.put(url, json={"version": 3, "disabled_builtin_kinds": ["no_instructor_overlap"]}, headers=h)
    assert r.status_code == 403


async def test_exclusion_removes_events_from_solver_input(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    async with get_session_factory()() as s:
        base = await build_draft_input(s, await _draft(bahar.term_id))
    # a joint lecture: MAT 112 §1 is listed once per programme and merged into one solver event
    merged = next(ev for ev, ids in base.members.items() if len(ids) == 2)
    head, other = base.members[merged]
    single = await meeting_id("PHAR 240", day=1, start=1)
    assert single in {e.id for e in base.inp.events}
    size_before = next(e.size for e in base.inp.events if e.id == merged)
    r = await c.put(url, json={"version": 1, "excluded_event_ids": [single, other]}, headers=h)
    assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        draft = await _draft(bahar.term_id)
        inp = await build_solver_input_for_draft(s, draft)
        out = await build_draft_input(s, draft)
    ids = {e.id for e in inp.events}
    assert single not in ids and merged in ids
    assert len(inp.events) == len(base.inp.events) - 1
    assert out.members[merged] == [head] and other not in {m for ms in out.members.values() for m in ms}
    assert next(e.size for e in inp.events if e.id == merged) <= size_before
    assert out.excluded == [single, other]


async def test_disabled_builtin_is_recorded_and_honoured(bahar):
    c, h, url = bahar.client, bahar.admin, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    r = await c.put(url, json={"version": 1, "disabled_builtin_kinds": ["no_room_overlap"]}, headers=h)
    assert r.status_code == 422  # never switchable
    r = await c.put(url, json={"version": 1, "disabled_builtin_kinds": ["no_instructor_overlap"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["disabled_builtin_kinds"] == ["no_instructor_overlap"]
    draft_id = r.json()["draft_id"]
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(ConstraintRow).where(ConstraintRow.source == "BUILTIN"))).scalars())
        assert [(x.kind, x.enabled, x.term_id, (x.source_ref or {}).get("draft_id")) for x in rows] == [
            ("no_instructor_overlap", False, bahar.term_id, draft_id)
        ]
        inp = await build_solver_input_for_draft(s, await _draft(bahar.term_id, "admin@example.com"))
    assert all(not e.instructor_keys for e in inp.events)
    cfg = [k for k in inp.constraints if k.kind == "no_instructor_overlap"]
    assert len(cfg) == 1 and cfg[0].hard and cfg[0].params["keys"]  # checks a key nobody has
    # the planner's draft keeps the rule
    async with get_session_factory()() as s:
        await c.get(url, headers=bahar.planner)
        inp_p = await build_solver_input_for_draft(s, await _draft(bahar.term_id))
    assert any(e.instructor_keys for e in inp_p.events)
    assert not [k for k in inp_p.constraints if k.kind == "no_instructor_overlap"]
    # switching it back on removes the row
    r = await c.put(url, json={"version": 2, "disabled_builtin_kinds": []}, headers=h)
    assert r.status_code == 200 and r.json()["disabled_builtin_kinds"] == []
    async with get_session_factory()() as s:
        assert not list((await s.execute(select(ConstraintRow).where(ConstraintRow.source == "BUILTIN"))).scalars())
