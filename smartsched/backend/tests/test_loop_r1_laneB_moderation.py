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


async def test_t_r1_16_the_same_wish_twice_is_refused_while_the_first_waits(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    rid, iid, _ = await _row(tid, ROW)
    _uid, teacher = await _teacher(c, h, iid, "ptl.ikitercih@uni.edu.tr")
    body = {"kind": "room", "request_ids": [rid], "rooms": ["C 301"]}
    first = await c.post(f"{API}/moderation/me/preferences", json=body, headers=teacher)
    assert first.status_code == 201, first.text
    # the preview already says so (the sheet disables "Onaya gönder"), and the real send is refused in Turkish
    preview = await c.post(f"{API}/moderation/me/preferences", params={"dry_run": 1}, json=body, headers=teacher)
    assert preview.status_code == 409 and preview.json()["detail"]["code"] == "duplicate_pending"
    again = await c.post(f"{API}/moderation/me/preferences", json=body, headers=teacher)
    assert again.status_code == 409, again.text
    d = again.json()["detail"]
    assert (
        d["code"] == "duplicate_pending"
        and d["message_tr"] == "Bu tercih zaten gönderildi ve koordinatörün kararını bekliyor."
    )
    mine = (await c.get(f"{API}/moderation/me/preferences", headers=teacher)).json()
    assert sum(1 for it in mine["items"] if it["status"] == "pending") == 1
    # the sentence lists each class once
    assert all(it["text"]["tr"].count("PTL 102") <= 1 for it in mine["items"])


async def test_t_r1_20_an_academician_reads_the_moderation_refusals_in_turkish(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    _rid, iid, _ = await _row(tid, ROW)
    _uid, teacher = await _teacher(c, h, iid, "ptl.ret@uni.edu.tr")
    other = iid + 1
    r = await c.get(f"{API}/moderation/people/{other}/history", headers=teacher)
    assert r.status_code == 403
    d = r.json()["detail"]
    assert d["code"] == "not_yours" and d["message_tr"] == "Yalnız kendi taleplerinizi görebilirsiniz."
    assert d["message_en"] == "you can see only your own requests"
    _sid, stranger = await make_user(c, h, "baglantisiz@uni.edu.tr", role="TEACHER")
    r = await c.get(f"{API}/terms/{tid}/moderation/people", headers=stranger)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_linked" and r.json()["detail"]["message_tr"]


async def test_t_r1_20_kisiler_finds_the_teachers_of_a_course_code(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    _rid, iid, _ = await _row(tid, ROW)  # PTL 102 §1
    for q in ("PTL 102", "ptl102"):
        r = await c.get(f"{API}/terms/{tid}/moderation/people", params={"q": q}, headers=h)
        assert r.status_code == 200, r.text
        assert iid in {int(p["id"]) for p in r.json()["items"]}, q
    # the rows carry the course codes (the console filters Kişiler on the client)
    every = (await c.get(f"{API}/terms/{tid}/moderation/people", headers=h)).json()["items"]
    assert "PTL 102" in next(p for p in every if int(p["id"]) == iid)["courses"]
