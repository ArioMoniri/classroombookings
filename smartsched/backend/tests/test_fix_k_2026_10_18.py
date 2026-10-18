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
        json={
            "term_id": term["id"],
            "kind": "building_preference",
            "params": params,
            "hardness": "soft",
            "nl_text": "x",
        },
        headers=h,
    )
    assert rule.status_code in (200, 201), rule.text
    rid = rule.json()["id"]
    r = await client.put(
        f"/api/v1/constraints/{rid}", json={"params": {"buildings": ["A"]}, "hardness": "hard"}, headers=h
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "rule_scope_lost" and detail["fields"] == ["kinds"] and detail["message_tr"]
    got = next(
        x
        for x in (await client.get("/api/v1/constraints", params={"term_id": term["id"]}, headers=h)).json()
        if x["id"] == rid
    )
    assert got["params"] == params and got["hardness"] == "soft"
    # keeping the scope and changing the rest is fine
    ok = await client.put(
        f"/api/v1/constraints/{rid}", json={"params": {**params, "buildings": ["A"]}, "hardness": "hard"}, headers=h
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["params"]["event_ids"] == [426]
    # the Studio's "Kime uygulanır › Herkes" widens a planner's own class rule on purpose: allowed
    own = await client.post(
        "/api/v1/constraints",
        json={
            "term_id": term["id"],
            "kind": "building_preference",
            "params": {"event_ids": [5], "buildings": ["A"]},
            "hardness": "soft",
            "nl_text": "y",
        },
        headers=h,
    )
    wide = await client.put(f"/api/v1/constraints/{own.json()['id']}", json={"params": {"buildings": ["A"]}}, headers=h)
    assert wide.status_code == 200, wide.text


async def test_e2ea_f07_a_file_rule_keeps_its_event_ids(client):  # noqa: F811
    from app.core.db import get_session_factory
    from app.models import ConstraintRow

    h = await login(client)
    term = (await client.post("/api/v1/terms", json={"code": "2026-FINAL", "name": "Final"}, headers=h)).json()
    async with get_session_factory()() as s:
        row = ConstraintRow(
            term_id=term["id"],
            kind="building_preference",
            params={"event_ids": [426], "buildings": ["A", "C"]},
            hardness="soft",
            weight=1,
            source="FILE",
            nl_text="satır 431",
            enabled=True,
        )
        s.add(row)
        await s.commit()
        rid = row.id
    r = await client.put(f"/api/v1/constraints/{rid}", json={"params": {"buildings": ["A"]}}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["fields"] == ["event_ids"], r.text


# ---------------------------------------------------------------------------------------------------- E2EA2-F05


def test_e2ea2_f05_returned_evidence_names_the_current_grid_times() -> None:
    """A learned habit stored with "(08:30–13:20)" is read after the admin moved P1 to 08:00: the returned
    ``evidence.value_label`` follows the grid like ``value_label`` does; the other evidence is untouched."""
    from app.importers import normalize as n
    from app.models import LearnedPrior
    from app.services import learning, period_grid

    p = LearnedPrior(
        attribute="period",
        value="morning",
        evidence={
            "value_label": {"tr": "sabah saatleri (08:30–13:20)", "en": "the morning (08:30–13:20)"},
            "request_ids": [7],
        },
    )
    times = [(f"{x.start:%H:%M}", f"{x.end:%H:%M}") for x in n.DEFAULT_PERIODS]
    times[0] = ("08:00", "08:40")
    try:
        n.set_period_grid(period_grid.parse([{"start": s, "end": e} for s, e in times]))
        ev = learning._evidence(p)
        assert ev["value_label"]["tr"] == "sabah saatleri (08:00–13:20)"
        assert ev["value_label"]["en"] == "the morning (08:00–13:20)"
        assert ev["request_ids"] == [7]
        assert p.evidence["value_label"]["tr"] == "sabah saatleri (08:30–13:20)"  # the stored row is not changed
    finally:
        n.set_period_grid(None)
    assert learning._evidence(LearnedPrior(attribute="room", value="A 204", evidence=None)) == {}


# ---------------------------------------------------------------------------------------------------- E2EA2-F06


async def test_e2ea2_f06_a_week_set_back_to_its_file_value_is_no_longer_edited(client):  # noqa: F811
    """The board import remembers each week's kind / label / start date; PATCH back to those values clears
    ``edited`` (so the next board import updates the week again). A week with no remembered values keeps the old
    rule: any change marks it edited."""
    from datetime import date

    from app.core.db import get_session_factory
    from app.models import Week
    from app.services.week_snapshots import remember_imported_week

    h = await login(client)
    term = (await client.post("/api/v1/terms", json={"code": "2026-BAHAR", "name": "Bahar"}, headers=h)).json()
    async with get_session_factory()() as s:
        w14 = Week(term_id=term["id"], index=14, start_date=date(2026, 5, 18), kind="LECTURE", label="14. hafta")
        w13 = Week(term_id=term["id"], index=13, start_date=date(2026, 5, 11), kind="LECTURE", label="13. hafta")
        s.add_all([w14, w13])
        await s.flush()
        await remember_imported_week(s, w14)
        await s.commit()
    url = f"/api/v1/terms/{term['id']}/weeks"
    r = await client.patch(f"{url}/14", json={"kind": "HOLIDAY"}, headers=h)
    assert r.status_code == 200 and r.json()["edited"] is True, r.text
    r = await client.patch(f"{url}/14", json={"kind": "LECTURE"}, headers=h)
    assert r.status_code == 200 and r.json()["kind"] == "LECTURE" and r.json()["edited"] is False, r.text
    # no remembered values (imported before FIX-K): stays edited, as before
    await client.patch(f"{url}/13", json={"kind": "HOLIDAY"}, headers=h)
    r = await client.patch(f"{url}/13", json={"kind": "LECTURE"}, headers=h)
    assert r.json()["edited"] is True
