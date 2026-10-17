"""CAL-02 "Derslerim": an academician's own published classes as a subscription feed
(``/calendar/feeds/{token}/classes.ics``) on the real Bahar 2026 import.

The account is linked to the PSY 262 instructor (P19-L1 ``Instructor.user_id``); the feed holds exactly the
meetings of the sections that instructor teaches, from the published run only, with TZID=Europe/Istanbul + one
VTIMEZONE, RFC 7986 NAME + SOURCE, and only the allowed fields (course code, section, room, time, department; the
title and a SmartSched link as the admin allows; never students, notes or the other teachers' names by default).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from app.core import db as dbmod
from app.importers import normalize as n
from app.models import Assignment, Course, ScheduleRun, Section, SectionInstructor
from app.services import calendar_classes as cc
from app.services import run_copy
from sqlalchemy import select, update

from tests.cal_support import IST, events, link_instructor, lint_ics, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off

#: every property a class event may carry (the PII allow-list)
ALLOWED = {
    "UID",
    "DTSTAMP",
    "LAST-MODIFIED",
    "SEQUENCE",
    "DTSTART",
    "DTEND",
    "SUMMARY",
    "LOCATION",
    "STATUS",
    "TRANSP",
    "DESCRIPTION",
}
PANEL = "https://rezervasyon.uni.edu.tr"


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)
    r = await env.client.put("/api/v1/calendar/admin/settings", json={"public_url": PANEL}, headers=env.admin)
    assert r.status_code == 200, r.text


async def _ayse(env):  # type: ignore[no-untyped-def]  # noqa: F811
    p = await psy262(env)
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    await link_instructor(uid, p.instructor_id)
    await calendar_consent(env.client, ayse)
    return p, uid, ayse


async def _taught_codes(env, instructor_id: int) -> set[str]:  # type: ignore[no-untyped-def]  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        codes = (
            await s.execute(
                select(Course.display_code)
                .join(Section, Section.course_id == Course.id)
                .join(SectionInstructor, SectionInstructor.section_id == Section.id)
                .where(SectionInstructor.instructor_id == instructor_id, Section.term_id == env.term_id)
            )
        ).scalars()
        return {str(c) for c in codes}


async def test_cal_02_my_classes_feed_holds_exactly_the_linked_instructors_meetings(env):  # noqa: F811
    p, _, ayse = await _ayse(env)
    r = await env.client.post("/api/v1/calendar/subscriptions", json={"scope_kind": "my_classes"}, headers=ayse)
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["scope_kind"] == "my_classes" and sub["token"].startswith("sst_")
    assert sub["url"] == f"{PANEL}/api/v1/calendar/feeds/{sub['token']}/classes.ics"
    assert sub["urls"]["webcal"].startswith("webcal://") and "calendar.google.com" in sub["urls"]["google"]
    feed = await env.client.get(f"/api/v1/calendar/feeds/{sub['token']}/classes.ics")
    assert feed.status_code == 200 and feed.headers["content-type"].startswith("text/calendar")
    text = feed.text
    cal = lint_ics(text, forbidden=[*p.instructor_names, "Ayşe Yılmaz"])
    assert str(cal["NAME"]) == "SmartSched – Derslerim" and str(cal["X-WR-CALNAME"]) == "SmartSched – Derslerim"
    assert str(cal["SOURCE"]) == sub["url"]
    assert [str(t["TZID"]) for t in cal.walk("VTIMEZONE")] == ["Europe/Istanbul"]
    assert "DTSTART;TZID=Europe/Istanbul:20260302T133000" in text
    evs = events(text)
    assert evs
    for e in evs:
        assert set(e.keys()) <= ALLOWED, set(e.keys()) - ALLOWED
    # exactly the instructor's courses
    taught = await _taught_codes(env, p.instructor_id)
    shown = {str(e["SUMMARY"]).split(" · ")[0] for e in evs}
    assert shown and shown <= taught, shown - taught
    mon = [e for e in evs if e.decoded("DTSTART") == datetime(2026, 3, 2, 13, 30, tzinfo=IST)]
    assert len(mon) == 1
    ev = mon[0]
    assert str(ev["SUMMARY"]) == "PSY 262 · Şube 1"
    assert ev.decoded("DTEND") == datetime(2026, 3, 2, 15, 50, tzinfo=IST)
    assert str(ev["LOCATION"]) == p.room.display_name == "A 308"
    desc = str(ev["DESCRIPTION"])
    assert "Klinik Psikolojiye Giriş" in desc and "Bölüm: Psikoloji" in desc and f"SmartSched: {PANEL}" in desc
    # the 15 teaching weeks of PSY 262 from the 90 past days on
    assert len([e for e in evs if str(e["SUMMARY"]).startswith("PSY 262")]) == 15
    # a draft run changes nothing (T19)
    async with dbmod.get_session_factory()() as s:
        live = await s.get(ScheduleRun, env.run_id)
        assert live is not None
        _, id_map = await run_copy.clone_as_draft(s, live, actor=None, reason="CAL-02 draft")
        await s.execute(
            update(Assignment).where(Assignment.id == id_map[p.week5_assignment_id]).values(start_period=1, end_period=3)
        )
        await s.commit()
    again = await env.client.get(f"/api/v1/calendar/feeds/{sub['token']}/classes.ics")
    assert again.status_code == 200 and again.text == text


async def test_cal_02_not_linked_is_409_in_both_languages(env):  # noqa: F811
    _, mehmet = await env.user("mehmet.kaya@uni.edu.tr", full_name="Mehmet Kaya")
    await calendar_consent(env.client, mehmet)
    r = await env.client.post("/api/v1/calendar/subscriptions", json={"scope_kind": "my_classes"}, headers=mehmet)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "not_linked"
    assert d["message_tr"] == "Hesabınız bir öğretim elemanı kaydına bağlı değil; planlama ofisine başvurun."
    assert "not linked" in d["message_en"]
    r = await env.client.get("/api/v1/calendar/export/classes.ics", headers=mehmet)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_linked"


def test_cal_02_fields_allow_list_and_co_instructors_switch() -> None:
    """The DESCRIPTION follows the admin's field switches; the other teachers' names only when allowed, never the
    viewer's own; course code and room are always there (SUMMARY / LOCATION)."""
    o = cc.ClassOccurrence(
        uid="class-0123456789abcdef0123@smartsched",
        term_id=1,
        run_id=1,
        assignment_id=1,
        week=5,
        start=datetime(2026, 3, 2, 13, 30),
        end=datetime(2026, 3, 2, 15, 50),
        room_ids=(47,),
        rooms=("A 308",),
        codes=("PSY 262",),
        section="1",
        title="Klinik Psikolojiye Giriş",
        program_ids=(28,),
        departments=("Psikoloji",),
        instructor_ids=(203, 204),
        fingerprint="x" * 64,
    )
    names = {203: "Ezgi Soncu Büyükişcan", 204: "İsmail Işık"}
    on = cc.EventContext(cc.Fields(), frozenset({203}), PANEL, names)
    assert o.summary() == "PSY 262 · Şube 1" and o.location == "A 308"
    assert cc.description(o, on) == f"Klinik Psikolojiye Giriş\nBölüm: Psikoloji\nSmartSched: {PANEL}/profile"
    co = cc.EventContext(cc.Fields(co_instructors=True), frozenset({203}), "", names)
    text = cc.description(o, co) or ""
    assert "İsmail Işık" in text and "Ezgi" not in text
    bare = cc.EventContext(cc.Fields(course_title=False, department=False, link=False), frozenset(), PANEL, names)
    assert cc.description(o, bare) is None
    assert set(cc.Fields().as_dict()) == set(cc.FIELD_KEYS) and cc.Fields().as_dict()["co_instructors"] is False
    assert cc.ascii_slug("2026-BAHAR") == "2026-bahar" and cc.ascii_slug("Psikoloji (İngilizce)") == "psikoloji-ingilizce"
    assert n.course_key("PSY 262") == "PSY262"
    assert date(2026, 3, 2).isoweekday() == 1
