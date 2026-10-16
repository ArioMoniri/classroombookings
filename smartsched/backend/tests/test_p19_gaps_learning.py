"""Phase 19 backend gap 4 (P19-S-02 / P19-S-03) on the real Bahar 2026 + Güz 2026 lists (the learning module's
database, a new same-season term 2027-BAHAR with SYS 19 and RAD 202 copied without rooms):

* ``POST /learning/suggestions/{id}/restore`` undoes a dismissal (the -3 evidence is taken back, the suggestion is
  open again), a snooze, and an acceptance (its LEARNED rule is switched off, the suggestion is open);
* ``accept`` takes ``scope: term | persistent``; persistent needs ``planning.admin`` and marks the same suggestion
  in another term (``persistent_accept``), never applied by itself.
"""

from __future__ import annotations

from app.models import AuditEvent, ConstraintRow, LearnedObservation
from sqlalchemy import func, select

from tests.test_p19_learning import API, Env, _next_bahar, _pick, _session, _suggestions, env  # noqa: F401


async def test_restore_undoes_dismiss_snooze_and_accept(env: Env) -> None:  # noqa: F811
    term, _copies = await _next_bahar(["SYS 19", "RAD 202"])
    items = await _suggestions(env, term)
    rad = _pick(items, "course", "building", "RAD 202")
    url = f"{API}/learning/suggestions/{rad['id']}"
    # nothing to undo on an open suggestion
    assert (await env.client.post(f"{url}/restore", headers=env.planner)).status_code == 409
    # dismissal -> restore: open again, the -3 evidence is gone
    assert (await env.client.post(f"{url}/reject", json={"reason": "Bu dönem farklı"}, headers=env.planner)).is_success
    assert rad["id"] not in {i["id"] for i in await _suggestions(env, term)}
    r = await env.client.post(f"{url}/restore", headers=env.planner)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": rad["id"], "state": "open", "undone": "dismissed", "disabled_constraint_id": None}
    again = _pick(await _suggestions(env, term), "course", "building", "RAD 202")
    assert again["id"] == rad["id"] and again["state"] == "open"
    assert again["confidence"] == rad["confidence"]  # the memory is as before the dismissal
    async with _session() as s:
        n_rejected = (
            await s.execute(select(func.count()).where(LearnedObservation.kind == "suggestion_rejected"))
        ).scalar_one()
        assert n_rejected == 0
    # snooze -> restore
    assert (await env.client.post(f"{url}/snooze", json={"until": "P7D"}, headers=env.planner)).is_success
    r = await env.client.post(f"{url}/restore", headers=env.planner)
    assert r.json()["undone"] == "snoozed"
    assert rad["id"] in {i["id"] for i in await _suggestions(env, term)}
    # accept -> restore: the rule is switched off and the suggestion is open (it can be accepted again)
    r = await env.client.post(f"{url}/accept", json={}, headers=env.planner)
    assert r.status_code == 201 and r.json()["scope"] == "term"
    cid = r.json()["constraint_id"]
    accepted = await _suggestions(env, term, state="accepted")
    assert [(i["id"], i["scope"]) for i in accepted] == [(rad["id"], "term")]
    r = await env.client.post(f"{url}/restore", headers=env.planner)
    assert r.json()["undone"] == "accepted" and r.json()["disabled_constraint_id"] == cid
    async with _session() as s:
        rule = await s.get(ConstraintRow, cid)
        assert rule is not None and rule.enabled is False
        acts = [
            a for (a,) in (await s.execute(select(AuditEvent.action).where(AuditEvent.action.like("suggestion.%"))))
        ]
        assert acts.count("suggestion.restore") == 3
    assert rad["id"] in {i["id"] for i in await _suggestions(env, term)}
    r = await env.client.post(f"{url}/accept", json={}, headers=env.planner)
    assert r.status_code == 201  # once undone, it can be accepted again


async def test_persistent_acceptance_needs_admin_and_marks_the_next_term(env: Env) -> None:  # noqa: F811
    term, _ = await _next_bahar(["SYS 19", "RAD 202"])
    sys19 = _pick(await _suggestions(env, term), "course", "building", "SYS 19")
    url = f"{API}/learning/suggestions/{sys19['id']}/accept"
    r = await env.client.post(url, json={"scope": "persistent"}, headers=env.planner)
    assert r.status_code == 403  # Kalıcı is planning.admin's
    assert (await env.client.post(url, json={"scope": "forever"}, headers=env.admin)).status_code == 422
    r = await env.client.post(url, json={"scope": "persistent"}, headers=env.admin)
    assert r.status_code == 201, r.text
    async with _session() as s:
        rule = await s.get(ConstraintRow, r.json()["constraint_id"])
        assert rule is not None and rule.source_ref["scope"] == "persistent" and rule.hardness == "soft"
    accepted = await _suggestions(env, term, state="accepted")
    assert accepted[0]["scope"] == "persistent"
    # the Güz term's SYS 19 building suggestion (same subject, attribute, value) is marked, listed first, still open
    guz = await _suggestions(env, env.guz, state="all")
    same = [i for i in guz if (i["subject"]["type"], i["attribute"], i["value"]) == ("course", "building", "A")]
    marked = [i for i in same if i["subject"]["id"] == sys19["subject"]["id"]]
    if marked:  # Güz has SYS 19 classes: the suggestion exists there
        assert marked[0]["persistent_accept"]["term_id"] == term and marked[0]["state"] != "accepted"
        assert guz[0]["persistent_accept"] is not None
    assert all(i["persistent_accept"] is None for i in guz if i["subject"]["id"] != sys19["subject"]["id"])
