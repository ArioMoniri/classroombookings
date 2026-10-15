"""P19-00b (review 2026-10-15 D1): per-source kind/hardness allowlist for model-made rules.

Rules whose source is AI, UPLOAD or LEARNED may never be a *soft* structural rule (capacity, room_tags,
fixed_time, room_pin, room_forbid) and never untargeted (an untargeted row reconfigures a rule for every class).
LEARNED rules are further limited to {room_preference, building_preference, same_room_across_weeks,
day_window (soft)}, soft, weight 1..5, targeted. The check runs when the model's proposal comes back (status
``rejected`` with a reason), again on accept (the browser's copy is not trusted) and in the chat diff.
"""

from __future__ import annotations

import pytest
from app.ai import catalog
from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.ai.elicit import accept_proposals, elicit_constraints
from app.models import ConstraintRow
from sqlalchemy import select

from tests.ai.conftest import empty_params, empty_selector, proposal, text, tool

STRUCTURAL = ("capacity", "room_tags", "fixed_time", "room_pin", "room_forbid")


@pytest.mark.parametrize("source", ["AI", "UPLOAD", "LEARNED"])
@pytest.mark.parametrize("kind", STRUCTURAL)
def test_model_sources_never_soften_structural_rules(kind, source):
    untargeted = catalog.source_policy_issues(kind, {}, "soft", source)
    assert untargeted and any("soft" in i for i in untargeted)
    targeted = catalog.source_policy_issues(kind, {"event_ids": [1]}, "soft", source, weight=3)
    assert any("structural" in i for i in targeted)


def test_untargeted_rows_are_refused_but_targeted_hard_rules_pass():
    assert catalog.source_policy_issues("room_pin", {"room_ids": [3]}, "hard", "AI")  # every class into room 3
    assert catalog.source_policy_issues("day_window", {"latest": 10}, "hard", "UPLOAD")
    assert catalog.source_policy_issues("min_capacity_waste", {}, "soft", "AI", weight=5)
    assert catalog.source_policy_issues("room_pin", {"event_ids": [1], "room_ids": [3]}, "hard", "AI") == []
    assert catalog.source_policy_issues("day_window", {"program": "eczacılık", "latest": 10}, "hard", "UPLOAD") == []
    # a room closure targets a room, not classes
    assert catalog.source_policy_issues("room_closed", {"room_id": 3, "day": 1}, "hard", "AI") == []
    assert catalog.source_policy_issues("room_closed", {"day": 1}, "hard", "AI")


def test_planner_and_admin_rows_are_left_to_the_constraint_guard():
    # POST /constraints is guarded by app.services.constraint_guard (waiver with a reason); not this policy
    assert catalog.source_policy_issues("capacity", {}, "soft", "ADMIN") == []


def test_learned_allowlist():
    ok = {"event_ids": [1], "room_ids": [2]}
    assert catalog.source_policy_issues("room_preference", ok, "soft", "LEARNED", weight=3) == []
    assert catalog.source_policy_issues("building_preference", {"event_ids": [1]}, "soft", "LEARNED", weight=1) == []
    assert (
        catalog.source_policy_issues("same_room_across_weeks", {"event_ids": [1, 2]}, "soft", "LEARNED", weight=5) == []
    )
    assert (
        catalog.source_policy_issues("day_window", {"event_ids": [1], "latest": 9}, "soft", "LEARNED", weight=2) == []
    )
    assert catalog.source_policy_issues("day_window", {"event_ids": [1], "latest": 9}, "hard", "LEARNED")
    assert catalog.source_policy_issues("room_preference", ok, "soft", "LEARNED", weight=8)  # 1..5 only
    assert catalog.source_policy_issues("room_preference", {"room_ids": [2]}, "soft", "LEARNED", weight=3)
    assert catalog.source_policy_issues("room_closed", {"room_id": 2}, "hard", "LEARNED")
    assert catalog.source_policy_issues("exam_gap", {"event_ids": [1]}, "soft", "LEARNED", weight=3)


def _capacity_waiver() -> dict:
    return {
        "proposals": [proposal("capacity", "soft", weight=5, nl_text="kapasite önemli değil")],
        "section_edits": [],
        "unparsed": [],
    }


async def test_soft_untargeted_capacity_proposal_comes_back_rejected(session, seed, fake_sdk):
    fake_sdk.script = [tool("propose_constraints", _capacity_waiver())]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await elicit_constraints(session, seed.term_id, "kapasite önemli değil", "tr", client=client)
    p = out.proposals[0]
    assert p.kind == "capacity" and p.status == "rejected"
    assert any("structural" in i and "AI" in i for i in p.issues), p.issues

    # the browser's copy is not trusted: status flipped to ok and source to ADMIN is still refused
    forged = p.model_copy(update={"status": "ok", "issues": [], "source": "ADMIN"})
    created, rejected = await accept_proposals(session, seed.term_id, [forged])
    assert not created and any("structural" in i for i in rejected[0]["issues"])
    rows = (await session.execute(select(ConstraintRow).where(ConstraintRow.kind == "capacity"))).scalars().all()
    assert rows == []


async def test_targeted_hard_proposal_still_accepted(session, seed, fake_sdk):
    fake_sdk.script = [
        tool(
            "propose_constraints",
            {
                "proposals": [
                    proposal(
                        "room_pin",
                        selector=empty_selector(course_codes=["PHAR 240"]),
                        params=empty_params(room_codes=["A 206"]),
                    )
                ],
                "section_edits": [],
                "unparsed": [],
            },
        )
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await elicit_constraints(session, seed.term_id, "PHAR 240 A 206'da", "tr", client=client)
    assert out.proposals[0].status == "ok"
    created, rejected = await accept_proposals(session, seed.term_id, out.proposals)
    assert created and not rejected


async def test_chat_add_constraint_waiver_is_rejected_on_apply(session, seed, fake_sdk):
    raw = {**proposal("capacity", "soft", weight=4, nl_text="kapasiteyi boşver"), "scope": "term"}
    fake_sdk.script = [tool("add_constraint", raw), text("Önerdim.")]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, seed.run_id, "kapasiteyi boşver", "tr", client=client)
    assert out.proposed_diff is not None
    op = out.proposed_diff.operations[0]
    assert op.op == "add_constraint" and op.constraint.status == "rejected"
    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert res.child_run_id is None and res.status == "REJECTED"
    assert any("structural" in r for r in res.rejected[0]["reasons"])
