"""Flow loop round 1, lane B: Taleplerim and the academician's moderation reads on the real 2026 Bahar list (the
shared published week-3 database of ``tests/test_p19_moderation.py``; every test works on a private copy).

Real row: R601 PTL 102 §1, its primary instructor logs in as an academician (TEACHER) linked to the record.
"""

from __future__ import annotations

from typing import Any

from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)
from tests.test_p19_t2_teacher_preferences import ROW, _row, _teacher

API = "/api/v1"


async def test_t_r1_11_taleplerim_reads_only_the_own_rows_from_its_own_endpoint(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    rid, iid, _ = await _row(tid, ROW)
    _uid, teacher = await _teacher(c, h, iid, "ptl.taleplerim@uni.edu.tr")
    term_wide = (await c.get(f"{API}/terms/{tid}/moderation/matchings?check=false&limit=5000", headers=teacher)).json()
    r = await c.get(f"{API}/moderation/me/matchings", params={"term_id": tid}, headers=teacher)
    assert r.status_code == 200, r.text
    mine = r.json()
    assert mine["visibility"] == "own" and mine["total"] == len(mine["items"]) > 0
    assert rid in {it["request_id"] for it in mine["items"]}
    assert all(iid in {i["id"] for i in it["instructors"]} for it in mine["items"])
    # the same rows as the term-wide list scoped to the academician, with their wishes, without the heavy extras
    assert sorted(it["request_id"] for it in mine["items"]) == sorted(it["request_id"] for it in term_wide["items"])
    assert all(it["teacher_preferences"] == [] and it["issues"] == [] for it in mine["items"])
    # a coordinator who teaches sees only their own rows here too (Taleplerim is personal)
    _pid, planner = await make_user(c, h, "koordinator.taleplerim@uni.edu.tr", role="PLANNER")
    r = await c.get(f"{API}/moderation/me/matchings", params={"term_id": tid}, headers=planner)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_linked"
    assert "öğretim elemanı" in r.json()["detail"]["message_tr"]
