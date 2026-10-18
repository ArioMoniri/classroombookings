"""CAL-13 "Sınav görevlerim": a person's invigilation duties of the **active** plan and their own exams of the
active EXAM run, as a scope-bound calendar link (``/calendar/feeds/{token}/duties.ics``), a one-off file and a push
scope, on the real 2026 Final (``tests/planning_analytics_support.build_final_plan``: the Bahar list for the
instructors and their teaching, the Final board + exam list solved like ``POST /runs``, one invigilation plan solved
with the default rules like the queue job).

Two academicians are linked to real instructor records (P19-L1 ``Instructor.user_id``): Ayşe, the instructor with
the most duties who also owns at least one exam of the run (the exam list's instructor cell matched with the
invigilation service's own rules), and Mehmet, another invigilator who shares no post with her. The clock is fixed
before the exams (Monday 4 May 2026).

UIDs are ``exam-<sha1(term | post key or exam request ids | date | ordinal)[:20]>@smartsched`` in
``calendar_class_revisions``: a re-solve that keeps a person at the same post keeps the UID; a duty that leaves the
published plan is sent once as ``STATUS:CANCELLED`` with a higher SEQUENCE."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import (
    Assignment,
    CalendarConnection,
    CalendarSyncJob,
    ExamRequest,
    Instructor,
    InvigilationDuty,
    Room,
    ScheduleRun,
    User,
)
from app.services import bookings as booking_service
from app.services import calendar_connectors as conn_svc
from app.services import invigilation as svc
from app.services import kvkk
from app.services.seed import seed_admin
from app.workers import integrations as worker
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.cal_support import IST, events, link_instructor, lint_ics
from tests.crbs_support import make_user
from tests.integrations_support import calendar_consent, kvkk_sign_off
from tests.planning_analytics_support import build_final_plan, copy_db

PANEL = "https://rezervasyon.uni.edu.tr"
TODAY = date(2026, 5, 4)  # the Monday before the Final's first exam day (13 May 2026)
INV = "/api/v1/invigilation"
SUBS = "/api/v1/calendar/subscriptions"


@dataclass
class Person:
    user_id: int
    headers: dict[str, str]
    instructor_id: int
    name: str
    #: (local start, room name) of each of the person's duties in the solved plan
    duties: set[tuple[datetime, str]]
    #: (local start, room names) of the person's own exams in the exam run
    exams: set[tuple[datetime, str]]


@dataclass
class DutyEnv:
    client: AsyncClient
    admin: dict[str, str]
    plan_id: int
    exam_run: int
    exam_run_b: int
    final_id: int
    ayse: Person
    mehmet: Person


@pytest.fixture(scope="session")
def cal13_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("cal13")


def _start(d: date, time_text: str) -> datetime:
    """``"13:30–15:50"`` (the invigilation screen's ``duty_out`` time) on ``d`` -> the local start."""
    hh, mm = time_text.split("–")[0].split(":")
    return datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=IST)


async def _people(plan_id: int, exam_run: int) -> tuple[dict[int, set[tuple[datetime, str]]], dict[int, set[Any]]]:
    """Duties per instructor (plan) and own exams per instructor (the exam list's instructor cell, matched like the
    invigilation service matches the exam people)."""
    async with dbmod.get_session_factory()() as s:
        rooms = {r.id: r.display_name for r in (await s.execute(select(Room))).scalars()}
        duties: dict[int, set[tuple[datetime, str]]] = defaultdict(set)
        for d in (await s.execute(select(InvigilationDuty).where(InvigilationDuty.plan_id == plan_id))).scalars():
            if d.instructor_id is not None:
                duties[int(d.instructor_id)].add((_start(d.date, svc.duty_out(d)["time"]), rooms[int(d.room_id or 0)]))
        exams = {e.id: e for e in (await s.execute(select(ExamRequest))).scalars()}
        instructors = list((await s.execute(select(Instructor).where(Instructor.archived.is_(False)))).scalars())
        owners = {k: k for e in exams.values() for k, _ in svc.person_keys(e.instructor_text)}
        found = svc.match_exam_people(owners, instructors)
        by_key: dict[str, int] = {k: i for i, k in found.key_of.items()}
        own: dict[int, set[Any]] = defaultdict(set)
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == exam_run))).scalars()
        for a in rows:
            e = exams.get(int(a.exam_request_id or 0))
            if e is None or (a.date or e.date) is None:
                continue
            for k, _ in svc.person_keys(e.instructor_text):
                if k in by_key:
                    own[by_key[k]].add((a.date or e.date, a.start_period, a.end_period))
    return duties, own


@pytest.fixture
async def denv(cal13_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[DutyEnv]:
    base, ids = await build_final_plan(cal13_dir)
    path = copy_db(base, tmp_path)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.core import throttle

    throttle.reset_all()

    async def fake_today(_session: Any) -> date:
        return TODAY

    monkeypatch.setattr(booking_service, "today", fake_today)
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        admin = await login(c)
        # the Final exam timetable is published (the plan was solved on it); the invigilation plan is not yet
        r = await c.post(f"/api/v1/runs/{ids['exam_run']}/activate", headers=admin)
        assert r.status_code == 200, r.text
        await kvkk_sign_off(SimpleNamespace(client=c, admin=admin))
        r = await c.put("/api/v1/calendar/admin/settings", json={"public_url": PANEL}, headers=admin)
        assert r.status_code == 200, r.text
        duties, own = await _people(ids["plan"], ids["exam_run"])
        ranked = sorted(duties, key=lambda i: (-len(duties[i]), i))
        ayse_iid = next(i for i in ranked if own.get(i))
        mehmet_iid = next(i for i in ranked if i != ayse_iid and not (duties[i] & duties[ayse_iid]))
        people: list[Person] = []
        for iid, email, full in (
            (ayse_iid, "ayse.yilmaz@uni.edu.tr", "Ayşe Yılmaz"),
            (mehmet_iid, "mehmet.oz@uni.edu.tr", "Mehmet Öz"),
        ):
            uid, headers = await make_user(c, admin, email, full_name=full)
            await link_instructor(uid, iid)
            async with dbmod.get_session_factory()() as s:
                ins = await s.get(Instructor, iid)
                assert ins is not None
                name = ins.full_name
            people.append(Person(uid, headers, iid, name, duties[iid], set(own.get(iid, set()))))
        yield DutyEnv(c, admin, ids["plan"], ids["exam_run"], ids["exam_run_b"], ids["final_id"], *people)
    await worker.wait_idle()
    await worker.shutdown()
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def _subscribe(e: DutyEnv, p: Person) -> dict[str, Any]:
    await calendar_consent(e.client, p.headers)
    r = await e.client.post(SUBS, json={"scope_kind": "my_duties"}, headers=p.headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _feed(e: DutyEnv, token: str) -> tuple[int, str]:
    r = await e.client.get(f"/api/v1/calendar/feeds/{token}/duties.ics")
    return r.status_code, r.text


def _duty_events(text: str, status: str = "CONFIRMED") -> list[Any]:
    return [x for x in events(text) if str(x["SUMMARY"]).startswith("Gözetmenlik") and str(x["STATUS"]) == status]


def _exam_events(text: str) -> list[Any]:
    return [x for x in events(text) if str(x["SUMMARY"]).startswith("Sınav ·")]


def _keyed(evs: list[Any]) -> dict[tuple[datetime, str], Any]:
    return {(x.decoded("DTSTART"), str(x["LOCATION"])): x for x in evs}


async def _activate(e: DutyEnv, plan_id: int) -> None:
    r = await e.client.post(f"{INV}/plans/{plan_id}/activate", headers=e.admin)
    assert r.status_code == 200, r.text


async def _rerun(e: DutyEnv, plan_id: int) -> int:
    r = await e.client.post(f"{INV}/plans/{plan_id}/rerun", json={"params": {"time_limit_s": 4.0}}, headers=e.admin)
    assert r.status_code == 202, r.text
    new_id = int(r.json()["plan_id"])
    await qmod.get_queue().wait_idle(600)
    d = (await e.client.get(f"{INV}/plans/{new_id}", headers=e.admin)).json()
    assert d["status"] in ("OPTIMAL", "FEASIBLE"), d["status"]
    return new_id


# ------------------------------------------------------------------------------------------- the feed


async def test_cal_13_duties_appear_on_activation_and_only_the_persons_own(denv: DutyEnv) -> None:
    e = denv
    sub = await _subscribe(e, e.ayse)
    assert sub["scope_kind"] == "my_duties" and sub["scope_label"] == "Sınav görevlerim"
    assert sub["url"] == f"{PANEL}/api/v1/calendar/feeds/{sub['token']}/duties.ics"
    assert sub["urls"]["webcal"].startswith("webcal://") and sub["path"] == "duties.ics"
    # the plan is solved but not published: no duty yet; her own exams (published exam run) are there
    status, text = await _feed(e, sub["token"])
    assert status == 200 and not _duty_events(text)
    exams = _exam_events(text)
    assert {x.decoded("DTSTART").date() for x in exams} == {d for d, _s, _e in e.ayse.exams}
    assert all(str(x["UID"]).startswith("exam-") and str(x["UID"]).endswith("@smartsched") for x in exams)

    await _activate(e, e.plan_id)
    status, text = await _feed(e, sub["token"])
    assert status == 200
    print("FEEDTEXT\n" + text)
    cal = lint_ics(text, forbidden=[e.mehmet.name, e.ayse.name, "Ayşe Yılmaz", "Mehmet Öz"])
    assert str(cal["X-WR-CALNAME"]) == "SmartSched – Sınav görevlerim"
    mine = _keyed(_duty_events(text))
    assert set(mine) == e.ayse.duties, (sorted(mine)[:3], sorted(e.ayse.duties)[:3])
    assert not set(mine) & e.mehmet.duties  # another person's duties never show
    for x in mine.values():
        assert str(x["UID"]).startswith("exam-") and int(x["SEQUENCE"]) >= 0
        assert x.decoded("DTSTART").tzinfo is not None and str(x["DTSTART"].params["TZID"]) == "Europe/Istanbul"
        assert "Öğrenci" not in str(x.get("DESCRIPTION", ""))

    # Mehmet's link shows his duties and none of hers
    sub_m = await _subscribe(e, e.mehmet)
    _, text_m = await _feed(e, sub_m["token"])
    theirs = _keyed(_duty_events(text_m))
    assert set(theirs) == e.mehmet.duties and not set(theirs) & e.ayse.duties
    assert not {str(x["UID"]) for x in mine.values()} & {str(x["UID"]) for x in theirs.values()}


async def test_cal_13_uids_stable_across_resolves_and_tombstoned_when_the_duty_leaves(denv: DutyEnv) -> None:
    e = denv
    sub = await _subscribe(e, e.ayse)
    await _activate(e, e.plan_id)
    _, text1 = await _feed(e, sub["token"])
    first = _keyed(_duty_events(text1))
    assert first

    # the same exams re-solved and published again: a duty she keeps keeps its UID
    plan2 = await _rerun(e, e.plan_id)
    await _activate(e, plan2)
    _, text2 = await _feed(e, sub["token"])
    second = _keyed(_duty_events(text2))
    kept = set(first) & set(second)
    assert kept, "the re-solve kept none of her posts"
    for k in kept:
        assert str(first[k]["UID"]) == str(second[k]["UID"])
        assert int(second[k]["SEQUENCE"]) >= int(first[k]["SEQUENCE"])
    lint_ics(text2)

    # she is taken out of the pool (Havuz: "görev almıyor") and the re-solve is published: every duty of hers
    # leaves the plan and is sent once as CANCELLED with a higher SEQUENCE; Mehmet's stay
    r = await e.client.post(
        f"{INV}/pool", json={"instructor_id": e.ayse.instructor_id, "full_name": e.ayse.name, "active": False},
        headers=e.admin,
    )  # fmt: skip
    assert r.status_code == 201, r.text
    plan3 = await _rerun(e, plan2)
    await _activate(e, plan3)
    _, text3 = await _feed(e, sub["token"])
    assert not _duty_events(text3)
    gone = _keyed(_duty_events(text3, "CANCELLED"))
    assert set(gone) == set(second)
    for k, x in gone.items():
        assert str(x["UID"]) == str(second[k]["UID"]) and int(x["SEQUENCE"]) > int(second[k]["SEQUENCE"])
    lint_ics(text3)
    sub_m = await _subscribe(e, e.mehmet)
    _, text_m = await _feed(e, sub_m["token"])
    assert _duty_events(text_m)

    # another exam timetable is published for the term: the plan of the old one no longer reaches calendars
    r = await e.client.post(f"/api/v1/runs/{e.exam_run_b}/activate", headers=e.admin)
    assert r.status_code == 200, r.text
    _, text_b = await _feed(e, sub_m["token"])
    assert not _duty_events(text_b) and _duty_events(text_b, "CANCELLED")


async def test_cal_13_link_serves_only_its_path_file_and_revocation(denv: DutyEnv) -> None:
    e = denv
    await _activate(e, e.plan_id)
    sub = await _subscribe(e, e.ayse)
    token = sub["token"]
    status, text = await _feed(e, token)
    assert status == 200
    # the scope-bound token serves only duties.ics
    for other in ("classes.ics", "mine.ics"):
        assert (await e.client.get(f"/api/v1/calendar/feeds/{token}/{other}")).status_code == 404
    # conditional GET: the same version answers 304
    r = await e.client.get(f"/api/v1/calendar/feeds/{token}/duties.ics")
    r304 = await e.client.get(f"/api/v1/calendar/feeds/{token}/duties.ics", headers={"If-None-Match": r.headers["etag"]})
    assert r304.status_code == 304
    # the one-off file: same engine and UIDs, attachment, no SOURCE
    f = await e.client.get("/api/v1/calendar/export/duties.ics", headers=e.ayse.headers)
    assert f.status_code == 200, f.text
    assert 'attachment; filename="sinav-gorevlerim-2026-final.ics"' == f.headers["content-disposition"]
    assert {str(x["UID"]) for x in events(f.text)} == {str(x["UID"]) for x in events(text)}
    assert "SOURCE" not in f.text
    # revoking the link kills it at once
    r = await e.client.delete(f"{SUBS}/{sub['id']}", headers=e.ayse.headers)
    assert r.status_code == 204
    assert (await _feed(e, token))[0] == 404
    # the administrator's switch for the scope
    r = await e.client.put("/api/v1/calendar/admin/export-settings", json={"export_my_duties": False}, headers=e.admin)
    assert r.status_code == 200 and r.json()["export_my_duties"] is False, r.text
    r = await e.client.post(SUBS, json={"scope_kind": "my_duties"}, headers=e.ayse.headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "scope_disabled"


async def test_cal_13_kvkk_consent_withdrawal_and_switch_like_the_other_personal_scopes(denv: DutyEnv) -> None:
    e = denv
    await _activate(e, e.plan_id)
    # without the person's calendar_sync consent: 409 consent_required (the sheet shows the consent tick)
    r = await e.client.post(SUBS, json={"scope_kind": "my_duties"}, headers=e.ayse.headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "consent_required", r.text
    sub = await _subscribe(e, e.ayse)
    assert sub["consent_id"] is not None
    assert (await _feed(e, sub["token"]))[0] == 200
    # the personal data export lists the link with its scope and consent (Art. 11), never the key
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, e.ayse.user_id)
        assert user is not None
        data = await kvkk.export_data(s, user)
    flat = repr(data)
    assert "'scope_kind': 'my_duties'" in flat and sub["token"] not in flat
    # withdrawing the consent revokes the link
    assert (await e.client.delete("/api/v1/me/consents/calendar_sync", headers=e.ayse.headers)).status_code == 200
    assert (await _feed(e, sub["token"]))[0] == 404
    # the institution's KVKK switch off: every duty feed is a 404
    sub_m = await _subscribe(e, e.mehmet)
    assert (await _feed(e, sub_m["token"]))[0] == 200
    r = await e.client.put("/api/v1/calendar/admin/settings", json={"calendar_sync_enabled": False}, headers=e.admin)
    assert r.status_code == 200, r.text
    assert (await _feed(e, sub_m["token"]))[0] == 404


async def test_cal_13_options_and_push_scope(denv: DutyEnv) -> None:
    e = denv
    await calendar_consent(e.client, e.ayse.headers)
    r = await e.client.get("/api/v1/calendar/export/options", headers=e.ayse.headers)
    assert r.status_code == 200, r.text
    item = next(x for x in r.json()["scopes"] if x["kind"] == "my_duties")
    assert item["label_tr"] == "Sınav görevlerim" and item["label_en"] == "My exam duties" and item["available"]
    assert item["preview"]["upcoming_count"] == len(e.ayse.exams)  # no published duty yet: her own exams
    # an account without an instructor record: not available, with the reason in Turkish
    _, other = await make_user(e.client, e.admin, "idari@uni.edu.tr", full_name="İdari Personel")
    r = await e.client.get("/api/v1/calendar/export/options", headers=other)
    nl = next(x for x in r.json()["scopes"] if x["kind"] == "my_duties")
    assert nl["available"] is False and nl["reason"]["code"] == "not_linked" and "öğretim elemanı" in nl["reason"]["message_tr"]

    # push: "my_duties" is a push scope; publishing the plan queues the person's class reconcile, and the desired
    # events are the feed's UIDs
    assert conn_svc.check_export_scopes(["my_duties"]) == [("my_duties", None)]
    assert conn_svc.class_scopes(["my_duties", "my_bookings"]) == ["my_duties"]
    async with dbmod.get_session_factory()() as s:
        conn = CalendarConnection(
            user_id=e.ayse.user_id, provider="google", status="ACTIVE", owned_calendar=True,
            export_scopes=["my_duties"], account_email="ayse.yilmaz@uni.edu.tr",
        )  # fmt: skip
        s.add(conn)
        await s.commit()
        conn_id = conn.id
    await _activate(e, e.plan_id)
    async with dbmod.get_session_factory()() as s:
        jobs = list((await s.execute(select(CalendarSyncJob).where(CalendarSyncJob.connection_id == conn_id))).scalars())
        assert any(j.kind == "classes" for j in jobs), [(j.kind, j.status) for j in jobs]
        conn_row = await s.get(CalendarConnection, conn_id)
        assert conn_row is not None
        want = await conn_svc.desired_classes(s, conn_row)
    sub = await _subscribe(e, e.ayse)
    _, text = await _feed(e, sub["token"])
    live = {str(x["UID"]) for x in events(text) if str(x["STATUS"]) == "CONFIRMED"}
    assert set(want) == live and all(u.startswith("exam-") for u in want)
    assert any(item.summary.startswith("Gözetmenlik") for item in want.values())

