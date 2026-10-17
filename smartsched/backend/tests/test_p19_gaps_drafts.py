"""Phase 19 backend gaps 6 + 7: program wizard drafts and the wizard reads, on real rows.

Real-data check (the brief): the Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans programme, Bahar rows 182-198
of ``bahar_derslik_planlama_listesi_v5.xlsx`` (MBG 598 Seminer, MBG 532 Epigenetik, MBG 534 Proteomiks, MBG 546,
MBG 502, MBG 541, MBG 549, with their enrolments, days, start times, instructors and the rooms the planner gave
them), typed into a draft for an empty term with the real room master (``room_master.csv``):

    draft (autosave, nothing written) -> validate (field / step / pre-check) -> commit (one transaction)
    -> POST /runs (CP-SAT, one worker) hard 100, planner_check 0 violations -> undo archives everything

and joint teaching on the real Bahar database (published week-3 run): the section search finds MBG 014 with its
published placement, a draft links a new course to it, the commit copies its meeting so the bridge merges both.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from app.core.db import get_session_factory
from app.importers.room_master import import_room_master
from app.models import AuditEvent, Course, Instructor, MeetingRequest, Program, ScheduleRun, Section
from app.workers.queue import get_queue
from httpx import AsyncClient
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.conftest import FIXTURES
from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)

API = "/api/v1"
#: Bahar rows of the MBG Tezli YL programme (Sayfa1, 1-based) and how the coordinator types the code
ROWS = {182: "MBG 598", 188: "mbg532", 189: "MBG\xa0534", 190: "MBG 546", 192: "MBG502", 195: "MBG 541", 198: "MBG 549"}


def _row(parsed: Any, number: int) -> Any:
    return next(r for r in parsed.rows if r.row == number)


def _hhmm(t: time) -> str:
    return f"{t:%H.%M}"  # dotted, as the lists write it


def mbg_payload(parsed: Any) -> dict[str, Any]:
    """The wizard state for the real rows, in the wizard's own camelCase keys (the backend accepts both)."""
    courses = []
    for number, typed in ROWS.items():
        r = _row(parsed, number)
        hours = r.t + r.u + r.l
        length = r.periods.end_period - r.periods.start_period + 1
        people = [{"name": r.instructors[0]}] if r.instructors else []
        courses.append(
            {
                "key": f"c{number}",
                "code": typed,
                "name": r.course_name,
                "t": r.t,
                "u": r.u,
                "l": r.l,
                "credits": str(r.credits).replace(".", ","),  # comma decimals
                "ects": r.ects,
                "year": r.class_years[0] if r.class_years else 1,
                "mode": r.mode.raw,  # "Yüz yüze"
                "sections": [
                    {"key": f"s{number}", "label": str(r.label or "1"), "enrolment": r.enrolment, "instructors": people}
                ],
                "pattern": {
                    "theoryBlocks": [r.t] if r.t else [],
                    "weeklyHours": None if hours else length,  # MBG 598 is 0 0 0 but meets one period
                    "days": r.day.days,
                    "start": _hhmm(r.start_time),
                    "weeks": "1-14",
                },
                # the planner's room as the wish (R195 has none: "Derslik talebi yok")
                "room": {
                    "capacity": None,
                    "tags": [],
                    "building": "",
                    "preferred": r.definitive.raw if r.definitive.room_codes else "",
                },
            }
        )
    first = _row(parsed, 188)
    return {
        "program": {
            "facultyName": first.faculty,
            "name": first.program,
            "level": "masterThesis",
            "evening": False,
            "prefix": "MBG",
            "years": 2,
        },
        "courses": courses,
        "cohorts": [{"key": "y1", "label": "MBG YL 1. sınıf", "year": 1, "compulsory": [c["key"] for c in courses]}],
        "rules": {"window": {"enabled": False, "earliest": 1, "latest": 11, "hard": False}, "sameRoom": True},
    }


async def _count(model: Any, *where: Any) -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())


def _codes(v: dict[str, Any], level: str) -> set[str]:
    return {i["code"] for i in v["issues"] if i["level"] == level}


async def test_mbg_tezli_yl_draft_validate_commit_solve_and_undo(client: AsyncClient, parsed_bahar_list: Any) -> None:
    h = await login(client)
    async with get_session_factory()() as s:
        await import_room_master(s, FIXTURES / "room_master.csv")
        await s.commit()
    r = await client.post(
        f"{API}/terms", json={"code": "2027-BAHAR", "name": "2027 Bahar", "week_count": 14}, headers=h
    )
    tid = r.json()["id"]
    _pid, planner = await make_user(client, h, "koordinator@uni.edu.tr", role="PLANNER")
    _vid, viewer = await make_user(client, h, "izleyici@uni.edu.tr", role="VIEWER")
    assert (await client.post(f"{API}/program-drafts", json={"term_id": tid}, headers=viewer)).status_code == 403

    # an empty draft, then the coordinator types: every save is a PATCH, nothing reaches the term
    r = await client.post(f"{API}/program-drafts", json={"term_id": tid, "step": "program"}, headers=planner)
    assert r.status_code == 201, r.text
    d = r.json()
    did, v = d["id"], d["version"]
    assert d["validation"]["can_commit"] is False and "no_name" in _codes(d["validation"], "error")
    payload = mbg_payload(parsed_bahar_list)
    r = await client.patch(
        f"{API}/program-drafts/{did}", json={"payload": payload, "base_version": v, "step": "courses"}, headers=planner
    )
    assert r.status_code == 200, r.text
    v = r.json()["version"]
    r = await client.patch(
        f"{API}/program-drafts/{did}",
        json={"path": "courses.c188.sections.s188.enrolment", "value": "80", "base_version": v},
        headers=planner,
    )
    assert r.status_code == 200 and r.json()["version"] == v + 1
    # another coordinator edits the same field from an older version: last write wins, the overwrite is reported
    r = await client.patch(
        f"{API}/program-drafts/{did}",
        json={"path": "courses.c188.sections.s188.enrolment", "value": 80, "base_version": v},
        headers=h,
    )
    assert r.status_code == 200
    over = r.json()["overwritten"]
    assert over and over[0]["path"] == "courses.c188.sections.s188.enrolment" and over[0]["previous"] == "80"
    # a whole payload from a stale version is refused (it cannot be merged field by field)
    stale = await client.patch(
        f"{API}/program-drafts/{did}", json={"payload": payload, "base_version": v}, headers=planner
    )
    assert stale.status_code == 409
    assert await _count(Section, Section.term_id == tid) == 0
    assert await _count(Program) == 0 and await _count(Course) == 0 and await _count(Instructor) == 0

    # resume list
    mine = (await client.get(f"{API}/program-drafts", params={"term_id": tid}, headers=planner)).json()
    assert [x["id"] for x in mine["items"]] == [did] and mine["items"][0]["step"] == "courses"
    assert mine["items"][0]["title"] == "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)"
    assert mine["items"][0]["summary"]["courses"] == 7 and mine["items"][0]["term_code"] == "2027-BAHAR"

    # validation: the spec's own consequence lines on the real rows
    val = (await client.post(f"{API}/program-drafts/{did}/validate", headers=planner)).json()
    assert val["can_commit"] is True, [i for i in val["issues"] if i["level"] == "error"]
    warns = {(i["code"], i["path"]): i for i in val["issues"] if i["level"] == "warning"}
    assert ("zero_hours", "courses.c182.t") in warns  # MBG 598 is 0 0 0 in the list
    exact = next(i for i in val["issues"] if i["code"] == "exact_fit")
    assert exact["text"]["tr"] == "A 207 tam 120 kişilik; kayıt artarsa sığmaz"
    small = next(i for i in val["issues"] if i["code"] == "preferred_small")
    assert small["text"]["tr"].startswith("C 504 (40) 80 öğrenciye yetmez")
    unknown = next(i for i in val["issues"] if i["code"] == "preferred_unknown")
    assert unknown["vars"]["room"] == "B 501"
    fixed = next(i for i in val["issues"] if i["code"] == "code_fixed" and i["path"] == "courses.c188.code")
    assert fixed["text"]["tr"] == "Ders kodu 'mbg532' → MBG 532 olarak düzeltildi"
    fits = next(i for i in val["issues"] if i["code"] == "fits" and i["path"] == "courses.c182.room")
    assert [x["display_name"] for x in fits["vars"]["rooms"][:4]] == ["A 207", "C 201", "A 203", "A 204"] or (
        fits["vars"]["rooms"][0]["display_name"] == "A 207"
    )
    rail = {s["step"]: s["status"] for s in val["steps"]}
    assert rail["program"] == "ok" and rail["rooms"] == "warning" and rail["courses"] == "warning"
    assert val["summary"]["courses"] == 7 and val["summary"]["new_people"] >= 4
    only = (await client.post(f"{API}/program-drafts/{did}/validate?step=patterns", headers=planner)).json()
    assert [s["step"] for s in only["steps"]] == ["rooms"]  # the wizard's step names are accepted
    # a pattern total that does not add up is an error on its step, and blocks the commit
    bad = await client.patch(
        f"{API}/program-drafts/{did}", json={"path": "courses.c195.pattern.theoryBlocks", "value": [2]}, headers=planner
    )
    errs = [i for i in bad.json()["validation"]["issues"] if i["level"] == "error"]
    assert [i["code"] for i in errs] == ["pattern_total"]
    assert errs[0]["text"]["tr"] == "MBG 541: 3 saatlik ders için yalnızca 2 saat yerleştirildi"
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)
    assert r.status_code == 422 and r.json()["detail"]["errors"] == 1
    assert await _count(Program) == 0  # nothing written
    await client.patch(
        f"{API}/program-drafts/{did}", json={"path": "courses.c195.pattern.theoryBlocks", "value": [3]}, headers=planner
    )

    # program-scoped pre-check: the draft's classes in the term, in a rolled-back session
    pre = (await client.post(f"{API}/program-drafts/{did}/precheck", headers=planner)).json()
    assert pre["readiness"] in ("ready", "needs_look"), pre["items"][:3]
    assert pre["counts"]["requests"] == 7 and len(pre["rooms_fit"]) == 7
    seminar = next(f for f in pre["rooms_fit"] if f["size"] == 120)
    assert seminar["rooms"][0]["code"] == "A207"
    assert (
        await _count(Program) == 0
        and await _count(MeetingRequest) == 0
        and await _count(AuditEvent, AuditEvent.action == "program.create") == 0
    )

    # paste preview (W-03): header, comma decimals, the code fix
    tsv = "Kod\tAd\tT\tU\tL\tK\tAKTS\tSınıf\nmbg532\tEpigenetik\t3\t0\t0\t3,5\t9\t1\n\n"
    pv = (
        await client.post(f"{API}/program-drafts/{did}/paste", json={"step": "courses", "tsv": tsv}, headers=planner)
    ).json()
    assert (
        pv["rows"][0]["code"] == "MBG 532"
        and pv["rows"][0]["credits"] == 3.5
        and pv["ignored"][0]["reason"] == "header"
    )

    # commit: one transaction
    r = await client.post(f"{API}/program-drafts/{did}/commit", json={"solve": "minimal"}, headers=planner)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["counts"]["courses"] == 7 and out["counts"]["sections"] == 7 and out["counts"]["requests"] == 7
    assert out["run_id"] is None and out["next"] == "studio"  # no published plan in this term
    assert out["audit_id"] and out["undo_until"]
    async with get_session_factory()() as s:
        prog = await s.get(Program, out["program_id"])
        assert prog is not None and prog.name == "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)"
        ev = await s.get(AuditEvent, out["audit_id"])
        assert ev is not None and ev.action == "program.create"
        mrs = list(
            (await s.execute(select(MeetingRequest).where(MeetingRequest.id.in_(out["created"]["requests"])))).scalars()
        )
        by_start = {(m.days[0] if m.days else m.day, m.start_period, m.end_period) for m in mrs}
        assert (2, 4, 6) in by_start  # MBG 532: Salı 11.00, 3 periods (Bahar R188)
        assert all(m.source_key.startswith("MAN:") for m in mrs)
        commit_ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "program_draft.commit"))
        ).scalar_one()
        assert sorted(commit_ev.after["requests"]) == sorted(out["created"]["requests"])
    # a committed draft is read-only and is no longer in the open list
    assert (
        await client.patch(f"{API}/program-drafts/{did}", json={"path": "program.name", "value": "x"}, headers=planner)
    ).status_code == 409
    assert (await client.post(f"{API}/program-drafts/{did}/commit", json={}, headers=planner)).status_code == 409
    assert (await client.get(f"{API}/program-drafts", params={"term_id": tid}, headers=planner)).json()["total"] == 0

    # solve the term like POST /runs: every class placed, hard 100, planner_check 0 violations
    body = {"term_id": tid, "kind": "COURSE", "params": {"workers": 1, "seed": 0, "time_limit_s": 60}}
    r = await client.post(f"{API}/runs", json=body, headers=h)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"{API}/runs/{run_id}", headers=h)).json()
    assert run["status"] in ("OPTIMAL", "FEASIBLE") and run["hard_score"] == 100, run
    from app.services.planner_check import check_run

    async with get_session_factory()() as s:
        stored = await s.get(ScheduleRun, run_id)
        assert stored is not None
        res = await check_run(s, stored)
    assert res.violations == [] and res.requests_placed == res.requests_total == 7, res.summary()
    print(
        f"P19-W draft {did}: run {run_id} {run['status']} hard={run['hard_score']} soft={run['soft_score']} {res.summary()}"
    )

    # undo: refused while the classes are in the published plan, with the reason
    assert (await client.post(f"{API}/runs/{run_id}/activate", headers=h)).status_code == 200
    chk = (await client.get(f"{API}/program-drafts/{did}/undo", headers=planner)).json()
    assert chk["can_undo"] is False and chk["blockers"][0]["code"] == "published"
    r = await client.post(f"{API}/program-drafts/{did}/undo", headers=planner)
    assert r.status_code == 409 and r.json()["detail"]["blockers"][0]["code"] == "published"
    async with get_session_factory()() as s:  # another plan is published meanwhile (none here: unpublish)
        stored = await s.get(ScheduleRun, run_id)
        assert stored is not None
        stored.is_active = False
        await s.commit()
    _oid, other = await make_user(client, h, "baska@uni.edu.tr", role="PLANNER")
    assert (await client.post(f"{API}/program-drafts/{did}/undo", headers=other)).status_code == 403
    r = await client.post(f"{API}/program-drafts/{did}/undo", headers=planner)
    assert r.status_code == 200, r.text
    arch = r.json()["archived"]
    assert len(arch["sections"]) == 7 and len(arch["courses"]) == 7 and arch["program"] == [out["program_id"]]
    assert await _count(Section, Section.term_id == tid, Section.archived.is_(False)) == 0
    assert await _count(MeetingRequest, MeetingRequest.archived.is_(False)) == 0
    assert await _count(Program, Program.archived.is_(False)) == 0
    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "program.undo"))).scalar_one()
        assert ev.undo_of == out["audit_id"]
    assert (await client.post(f"{API}/program-drafts/{did}/undo", headers=planner)).status_code == 409


async def test_wizard_reads_and_joint_teaching_on_the_real_bahar_term(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    # section search: the code typed any way finds MBG 014 Proteomiks (lisans) with its published placement
    r = await c.get(f"{API}/terms/{tid}/sections/search", params={"q": "mbg014"}, headers=h)
    assert r.status_code == 200, r.text
    hits = r.json()["items"]
    mbg014 = next(x for x in hits if x["course_code"] == "MBG 014")
    assert mbg014["enrolment"] == 75 and mbg014["periods_per_week"] >= 1 and mbg014["instructors"]
    assert mbg014["meetings"][0]["day"] == 5  # Cuma (Bahar R61)
    by_code = (await c.get(f"{API}/terms/{tid}/sections/search", params={"course_code": "MBG 014"}, headers=h)).json()
    assert {x["section_id"] for x in by_code["items"]} == {
        x["section_id"] for x in hits if x["course_code"] == "MBG 014"
    }
    prog = (
        await c.get(
            f"{API}/terms/{tid}/sections/search", params={"q": "moleküler biyoloji ve genetik tezli"}, headers=h
        )
    ).json()
    assert prog["total"] >= 7 and all("Tezli" in x["program_name"] for x in prog["items"])
    # instructor load: periods a week this term, with the limit
    ins_id = mbg014["instructors"][0]["id"]
    load = (await c.get(f"{API}/terms/{tid}/instructors/load", params={"ids": str(ins_id)}, headers=h)).json()
    assert load["limit"] == 20 and load["items"][0]["periods_per_week"] > 0 and load["items"][0]["sections"] >= 1
    named = (await c.get(f"{API}/terms/{tid}/instructors/load", params={"q": "SANER"}, headers=h)).json()
    assert any(i["instructor_id"] == ins_id for i in named["items"])  # Turkish-aware name search
    fit = (await c.get(f"{API}/terms/{tid}/rooms/fit", params={"capacity": 120}, headers=h)).json()
    assert fit["items"][0]["display_name"] == "A 207" and all("TIP" not in x["tags"] for x in fit["items"])

    # the Tezli YL programme exists in Bahar (imported): a second one with the same name is an error
    base = {
        "program": {
            "faculty_name": "Fen Bilimleri Enstitüsü",
            "name": "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (İngilizce)",
        },
        "courses": [],
    }
    r = await c.post(f"{API}/program-drafts", json={"term_id": tid, "payload": base}, headers=h)
    assert "program_exists" in _codes(r.json()["validation"], "error")
    # a new non-thesis programme takes MBG 534 jointly with MBG 014 ("Ortak ders"), same people
    payload = {
        "program": {
            "faculty_name": "Fen Bilimleri Enstitüsü",
            "name": "Moleküler Biyoloji ve Genetik Tezsiz Yüksek Lisans",
        },
        "courses": [
            {
                "key": "c1",
                "code": "MBG 534",
                "t": 3,
                "u": 0,
                "l": 0,
                "ects": 9,
                "year": 1,
                "mode": "F2F",
                "sections": [
                    {
                        "key": "s1",
                        "label": "1",
                        "enrolment": 10,
                        "instructors": [{"id": ins_id}],
                        "joint_section_ids": [mbg014["section_id"]],
                    }
                ],
                "pattern": {},
                "room": {},
            }
        ],
    }
    r = await c.post(f"{API}/program-drafts", json={"term_id": tid, "payload": payload}, headers=h)
    assert r.status_code == 201
    did = r.json()["id"]
    val = r.json()["validation"]
    assert val["can_commit"], [i for i in val["issues"] if i["level"] == "error"]
    assert "code_exists" in _codes(val, "info")  # MBG 534 is in the Bahar catalogue: reused, not duplicated
    fits = next(i for i in val["issues"] if i["code"] == "fits")
    assert fits["vars"]["n"] == 85  # 10 + MBG 014's 75: the joint total drives the room
    if mbg014["placement"]:
        assert "joint_placed" in _codes(val, "info")
    pre = (await c.post(f"{API}/program-drafts/{did}/precheck", headers=h)).json()
    assert pre["counts"]["requests"] == len(mbg014["meetings"])
    r = await c.post(f"{API}/program-drafts/{did}/commit", json={"solve": "none"}, headers=h)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["counts"]["courses"] == 0 and out["created"]["reused_courses"] and out["created"]["joint_links"]
    async with get_session_factory()() as s:
        new = list(
            (await s.execute(select(MeetingRequest).where(MeetingRequest.id.in_(out["created"]["requests"])))).scalars()
        )
        old = list(
            (
                await s.execute(
                    select(MeetingRequest).where(
                        MeetingRequest.section_id == mbg014["section_id"], MeetingRequest.archived.is_(False)
                    )
                )
            ).scalars()
        )
        assert sorted((m.day, m.start_period, m.end_period) for m in new) == sorted(
            (m.day, m.start_period, m.end_period) for m in old
        )
        assert all(m.notes and m.notes.startswith("Ortak ders: MBG 014") for m in new)
    # the instructor's load now counts the joint lecture once (same slot, same weeks)
    after = (await c.get(f"{API}/terms/{tid}/instructors/load", params={"ids": str(ins_id)}, headers=h)).json()
    assert after["items"][0]["periods_per_week"] == load["items"][0]["periods_per_week"]
    assert after["items"][0]["sections"] == load["items"][0]["sections"] + 1
