"""Round-1 R1-S-04: a minimal-change re-solve after one soft wish lost 17 placed classes and the publish confirm said
nothing. A repair re-solve never drops a published class for a soft wish: a class it leaves out is put back in its
published cell when that cell still keeps every hard rule; every class it still loses is a hard conflict, named
(``base_conflict`` when the published cell itself now breaks a rule, else its cell is taken by the change).

Real Bahar 2026 week 3 published (``tests/test_p19_moderation`` fixture).
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import Room
from sqlalchemy import select

from tests.test_p19_moderation import _resolve, real, workdir  # noqa: F401


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a["day"] == b["day"]
        and a["start_period"] <= b["end_period"]
        and b["start_period"] <= a["end_period"]
        and bool(set(a["room_ids"]) & set(b["room_ids"]))
        and (not a["weeks"] or not b["weeks"] or bool(set(a["weeks"]) & set(b["weeks"])))
    )


async def test_soft_wish_resolve_never_drops_a_class_without_a_hard_cause(real):  # noqa: F811
    c, h, tid, base = real["client"], real["admin"], real["term_id"], real["run_id"]
    phar = real["phar240"]
    async with dbmod.get_session_factory()() as s:
        big = [r for r in (await s.execute(select(Room).where(Room.is_bookable.is_(True)))).scalars()]
    target = max((r for r in big if "TIP" not in (r.tags or [])), key=lambda r: (r.capacity or 0, r.code))
    r = await c.post(
        "/api/v1/constraints",
        json={
            "term_id": tid,
            "kind": "room_preference",
            "params": {"event_ids": [phar], "room_ids": [target.id]},
            "hardness": "soft",
            "weight": 10,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    d = await _resolve(
        c, h, tid, {"base_run_id": base, "changed_request_ids": [phar], "mode": "repair", "time_limit_s": 30}
    )
    assert d["scores"]["hard"]["after"] == 100, d["diagnosis"]
    placed_now = [x["to"] for x in d["moved"]] + [x["to"] for x in d["newly_placed"]]
    for loss in (u for u in d["unplaceable"] if u["was_placed"]):
        # either its published cell itself breaks a hard rule now, or the change took that cell
        assert loss.get("base_conflict") or any(_overlap(loss["from"], p) for p in placed_now), loss
        assert loss["reason"]["text"]["tr"]
    assert d["counts"]["moved_unexplained"] == 0
