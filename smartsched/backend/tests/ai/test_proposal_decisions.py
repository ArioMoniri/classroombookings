"""Every reviewed AI proposal is kept with its outcome (coordinator request 2026-10-15; learning lane input).

``ai_proposal_decisions`` stores one row per proposal that reached an accept: ``accepted`` (with the created
constraint id), ``rejected`` (refused by the server, with the reasons) and ``declined`` (dismissed by the planner
in review, sent back in ``AcceptIn.declined``). Nothing in this table reaches the solver.
"""

from __future__ import annotations

import sqlite3

from alembic import command
from app.ai.elicit import accept_proposals
from app.core.db import get_session_factory
from app.models import AIProposalDecision, ConstraintRow
from app.schemas.ai import ProposedConstraint
from sqlalchemy import select

from tests.ai.conftest import seed_small
from tests.api_fixtures import login
from tests.test_crbs_migration import _run


def _pin(seed) -> ProposedConstraint:
    return ProposedConstraint(
        kind="room_pin",
        hardness="hard",
        weight=1,
        params={"event_ids": [seed.mr["PHAR240"]], "room_ids": [seed.rooms["A206"]]},
        nl_text="PHAR 240 A 206'da",
        source="UPLOAD",
        source_ref={"file": "prefs.xlsx", "row": 3},
    )


def _waiver() -> ProposedConstraint:
    return ProposedConstraint(kind="capacity", hardness="soft", weight=5, params={}, nl_text="kapasite önemsiz")


async def test_accept_records_accepted_rejected_and_declined(session, seed):
    declined = ProposedConstraint(
        kind="building_preference",
        hardness="soft",
        weight=4,
        params={"program": "eczacılık", "buildings": ["C"]},
        nl_text="eczacılık C blokta",
    )
    created, rejected = await accept_proposals(
        session, seed.term_id, [_pin(seed), _waiver()], user_id=None, declined=[declined]
    )
    assert len(created) == 1 and rejected[0]["index"] == 1
    rows = list((await session.execute(select(AIProposalDecision).order_by(AIProposalDecision.id))).scalars())
    by = {r.decision: r for r in rows}
    assert sorted(by) == ["accepted", "declined", "rejected"]
    acc = by["accepted"]
    assert acc.constraint_id == created[0] and acc.kind == "room_pin" and acc.source == "UPLOAD"
    assert acc.source_ref == {"file": "prefs.xlsx", "row": 3} and acc.term_id == seed.term_id
    rej = by["rejected"]
    assert rej.kind == "capacity" and rej.hardness == "soft" and rej.constraint_id is None
    assert any("structural" in r for r in rej.reasons) and rej.nl_text == "kapasite önemsiz"
    dec = by["declined"]
    assert dec.kind == "building_preference" and dec.reasons == ["declined by the planner in review"]
    # nothing but the accepted proposal became a solver rule
    cons = (await session.execute(select(ConstraintRow))).scalars().all()
    assert [c.id for c in cons] == created


async def test_accept_endpoint_stores_declined(client):
    h = await login(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
    body = {
        "proposals": [_pin(sd).model_dump(mode="json")],
        "declined": [_waiver().model_dump(mode="json")],
    }
    r = await client.post(f"/api/v1/terms/{sd.term_id}/elicit/accept", json=body, headers=h)
    assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(AIProposalDecision).order_by(AIProposalDecision.id))).scalars())
    assert [r.decision for r in rows] == ["accepted", "declined"]
    assert rows[0].created_by is not None and rows[1].kind == "capacity"


def test_migration_creates_and_drops_the_table(tmp_path):
    path = tmp_path / "dec.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("pragma table_info(ai_proposal_decisions)")}
    con.close()
    assert {"term_id", "run_id", "kind", "params", "hardness", "decision", "reasons", "constraint_id"} <= cols
    _run(url, command.downgrade, "0017_course_code_fold")
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert "ai_proposal_decisions" not in names
    _run(url, command.upgrade, "head")
