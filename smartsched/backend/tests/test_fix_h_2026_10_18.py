"""FIX-H (round 4, 2026-10-18): the open items after FIX-E.

- CAL10-F03: the feed ETag is the body's hash; an audit event elsewhere (a booking in another room) keeps it, so a
  polling calendar gets a 304.

Fixtures: the real Bahar 2026 import (tests/crbs_env.py, tests/cal_support.py)."""

from __future__ import annotations

from datetime import date

import pytest

from tests.cal_support import link_instructor, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off


@pytest.fixture
async def _kvkk(env):  # noqa: F811
    await kvkk_sign_off(env)


async def test_cal10_f03_an_unrelated_audit_event_keeps_the_feed_etag(env, _kvkk):  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.etag@uni.edu.tr", full_name="Ayşe Etag")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    sub = (
        await env.client.post("/api/v1/calendar/subscriptions", json={"scope_kind": "my_classes"}, headers=ayse)
    ).json()
    url = f"/api/v1/calendar/feeds/{sub['token']}/classes.ics"
    first = await env.client.get(url)
    assert first.status_code == 200
    etag = first.headers["etag"]
    # someone else books a room: an audit event, nothing in Ayşe's classes changes
    await env.book(env.planner, "A101", date(2026, 2, 18), "P1")
    again = await env.client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304, again.text
    assert again.headers["etag"] == etag
    # a client without the ETag gets the same body and the same tag
    plain = await env.client.get(url)
    assert plain.status_code == 200 and plain.headers["etag"] == etag and plain.text == first.text


# ---------------------------------------------------------------------------------------------------- PER-F05


def test_per_f05_every_common_importer_warning_has_a_code_and_a_turkish_sentence():
    from app.importers.report import ImportReport
    from app.importers.warning_text import classify

    w = classify("row 11: instructor value 'UZEM' names no person (mode); not used as an instructor")
    assert (w.row, w.code) == (11, "instructor_not_person")
    assert w.message_tr == "“UZEM” bir kişi değil (öğretim biçimi); öğretim elemanı sayılmadı"
    assert w.message_en == "instructor value 'UZEM' names no person (mode); not used as an instructor"
    assert classify("row 3: weeks value 0; assuming all").message_tr == "Hafta değeri 0; bütün haftalar varsayıldı"
    snap = classify("row 9: time 13:40-18:00 snapped to P7-P12 (13:30-18:00): overlap")
    assert snap.code == "time_snapped" and snap.message_tr.startswith("13:40–18:00 saati P7–P12")
    assert classify("something new").code == "other"

    r = ImportReport(kind="planning-list")
    for row in range(1, 38):
        r.warn("instructor value 'UZEM' names no person (mode); not used as an instructor", row)
    r.warn("weeks value 0; assuming all", 40)
    r.warn("a sentence no rule knows", 41)
    d = r.to_dict()
    assert d["warnings"][0] == "row 1: instructor value 'UZEM' names no person (mode); not used as an instructor"
    assert d["warning_items"][0] == {
        "row": 1,
        "code": "instructor_not_person",
        "message_tr": "“UZEM” bir kişi değil (öğretim biçimi); öğretim elemanı sayılmadı",
        "message_en": "instructor value 'UZEM' names no person (mode); not used as an instructor",
    }
    groups = d["warning_groups"]
    assert [g["code"] for g in groups] == ["instructor_not_person", "weeks_assumed_all", "other"]
    assert groups[0]["count"] == 37 and groups[0]["items"][0]["count"] == 37
    assert groups[0]["items"][0]["rows"][:3] == [1, 2, 3] and len(groups[0]["items"][0]["rows"]) == 12
    assert groups[0]["label_tr"] == "Kişi olmayan öğretim elemanı değeri"


def test_per_f05_the_real_planning_lists_read_in_turkish():
    """The workbooks the persona run imported: every row warning the parser writes has a code and a Turkish sentence."""
    from collections import Counter
    from pathlib import Path

    from app.importers.planning_list import parse_planning_list
    from app.importers.warning_text import classify

    fixtures = Path(__file__).parent / "fixtures"
    unknown: Counter[str] = Counter()
    seen = 0
    for name in ("bahar_derslik_planlama_listesi_v5.xlsx", "guz_derslik_planlama_2026_2027_v2.xlsx"):
        parsed = parse_planning_list(fixtures / name)
        for r in parsed.rows:
            for w in r.warnings:
                seen += 1
                t = classify(f"row {r.row}: {w}")
                assert t.row == r.row
                if t.code == "other":
                    unknown["".join("#" if ch.isdigit() else ch for ch in w)] += 1
    assert seen > 100
    assert not unknown, unknown.most_common(10)


# ---------------------------------------------------------------------------------------------------- PER-F04


def test_per_f04_the_file_names_its_season_in_the_name_or_a_sheet_title(tmp_path):
    import openpyxl
    from app.services.import_term_check import file_term

    from tests.conftest import BAHAR_LIST, GUZ_LIST

    assert file_term(BAHAR_LIST.name, BAHAR_LIST)[0] == "SPRING"
    assert file_term(GUZ_LIST.name, GUZ_LIST)[:2] == ("FALL", 2026)
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "BAHAR 2026"
    wb.save(tmp_path / "liste.xlsx")
    assert file_term("liste.xlsx", tmp_path / "liste.xlsx") == ("SPRING", 2026, "sheet_title")
    assert file_term("liste.csv", None) == (None, None, None)


async def test_per_f04_a_bahar_preview_onto_guz_says_so_and_suggests_bahar(client):  # noqa: F811
    from app.core.db import get_session_factory
    from app.models import Term
    from app.workers.queue import get_queue
    from sqlalchemy import select

    from tests.api_fixtures import login
    from tests.conftest import BAHAR_LIST

    h = await login(client)
    async with get_session_factory()() as s:
        have = {t.code for t in (await s.execute(select(Term))).scalars()}
        for code, name in (("2026-GUZ", "Güz 2026-27"), ("2026-BAHAR", "Bahar 2026")):
            if code not in have:
                s.add(Term(code=code, name=name))
        await s.commit()
        ids = {t.code: t.id for t in (await s.execute(select(Term))).scalars()}

    async def preview(term_code: str) -> dict:
        with BAHAR_LIST.open("rb") as f:
            r = await client.post(
                "/api/v1/imports/planning-list",
                files={"file": (BAHAR_LIST.name, f, "application/octet-stream")},
                data={"term_code": term_code, "dry_run": "true"},
                headers=h,
            )
        assert r.status_code == 202, r.text
        await get_queue().wait_idle()
        job = (await client.get(f"/api/v1/imports/{r.json()['id']}", headers=h)).json()
        assert job["status"] == "DONE", job
        return job["summary"]

    wrong = await preview("2026-GUZ")
    check = wrong["term_check"]
    assert check["mismatch"] is True and check["file_season"] == "SPRING" and check["source"] == "file_name"
    assert check["target_name"] == "Güz 2026-27"
    assert wrong["suggested_term_id"] == ids["2026-BAHAR"] and check["suggested_term_name"] == "Bahar 2026"
    # PER-F05 travels with the same summary: codes, Turkish sentences, groups
    assert wrong["warning_items"] and wrong["warning_items"][0]["message_tr"]
    assert (
        wrong["warning_groups"][0]["count"] >= wrong["warning_groups"][-1]["count"]
        or wrong["warning_groups"][-1]["code"] == "other"
    )
    right = await preview("2026-BAHAR")
    assert right["term_check"]["mismatch"] is False and right["suggested_term_id"] is None


# ---------------------------------------------------------------------------------------------------- PER-F09


async def test_per_f09_derslerim_lists_my_published_classes_of_the_week(env):  # noqa: F811
    from tests.cal_support import WEEK5_MON

    p = await psy262(env)
    uid, ayse = await env.user("ayse.derslerim@uni.edu.tr", full_name="Ayşe Derslerim")
    # not linked yet: an empty week that says so, not a 403
    before = (await env.client.get("/api/v1/me/classes/week", params={"date": "2026-03-04"}, headers=ayse)).json()
    assert before["linked"] is False and before["classes"] == []
    assert before["week_start"] == "2026-03-02" and before["week_end"] == "2026-03-08"
    assert before["prev"] == "2026-02-23" and before["next"] == "2026-03-09"
    await link_instructor(uid, p.instructor_id)
    week = (await env.client.get("/api/v1/me/classes/week", params={"date": "2026-03-04"}, headers=ayse)).json()
    assert week["linked"] is True and week["term_id"] == env.term_id
    psy = [c for c in week["classes"] if "PSY 262" in " ".join(c["codes"]) or "PSY262" in "".join(c["codes"])]
    assert psy, week["classes"][:3]
    first = psy[0]
    assert first["date"] == WEEK5_MON.isoformat() and first["rooms"] == [p.room.name]
    assert first["start"] < first["end"]
    assert all("2026-03-02" <= c["date"] <= "2026-03-08" for c in week["classes"])
