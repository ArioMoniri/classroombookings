"""Round-1 flow loop, lane D (KVKK / privacy) on the real 2026 Bahar list (the shared published week-3 database of
``tests/test_p19_moderation.py``; every test works on a private copy).

* T-R1-27 (R1-A-25, KVKK m.11 right of access): "Verilerimi indir" holds everything the system keeps about the
  person, not only the account: the linked instructor record and the sections they teach, the planning requests of
  those sections as Taleplerim shows them (request text, requested -> assigned, verdict), the exam requests, the
  teacher wishes with the coordinator's decision and reason, the coordinator's priority notes about them, approval
  decisions they received or made, learned priors, invigilation, calendar links and the audit rows about them. The
  other people on those records (the coordinator, a co-instructor) appear by their role only, never by name or
  e-mail. The zip's README explains every file.
* T-R1-28 (R1-A-26): the privacy notice follows the reader's language: a Turkish reader keeps the latest Turkish
  version even when a newer version exists only in English.
* T-R1-29 (R1-A-10, R1-S-24): a missing permission answers 403 ``{code: forbidden, permission, message_tr, message_en}``
  with the permission's Turkish name.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from app.core import db as dbmod
from app.importers.normalize import fold
from app.models import Instructor, MeetingRequest, Section, SectionInstructor, User
from sqlalchemy import select

from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)

API = "/api/v1"
ROW = 601  # PTL 102 §1 (the department asked for C 601)
NEW_SECTIONS = (
    "instructor",
    "instructor_sections",
    "planning_requests",
    "exam_requests",
    "teacher_preferences",
    "priority_notes",
    "approval_decisions",
    "approver_scopes",
    "learned_priors",
    "suggestion_feedback",
    "invigilation",
    "calendar_links",
    "booking_limits",
    "audit_as_subject",
)
OLD_SECTIONS = (
    "profile",
    "bookings",
    "series",
    "approvals",
    "notifications",
    "deliveries",
    "channel_deliveries",
    "channels",
    "sso_identities",
    "consents",
    "notice_acks",
    "audit_as_actor",
    "learning_observations",
    "data_requests",
)


async def _row(term_id: int, row: int) -> tuple[int, int, int]:
    """(request id, section id, primary instructor id) of a Bahar row."""
    async with dbmod.get_session_factory()() as s:
        mr = (
            await s.execute(
                select(MeetingRequest)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term_id, MeetingRequest.source_row_index == row)
            )
        ).scalar_one()
        iid = (
            await s.execute(
                select(SectionInstructor.instructor_id).where(
                    SectionInstructor.section_id == mr.section_id, SectionInstructor.role == "PRIMARY"
                )
            )
        ).scalar_one()
        return mr.id, mr.section_id, int(iid)


def _whole_words(text: str, needle: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(fold(needle))}(?!\w)", text) is not None


async def test_export_holds_every_record_about_the_person_and_no_one_else(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    rid, sid, iid = await _row(tid, ROW)
    uid, teacher = await make_user(c, h, "ptl.hoca@uni.edu.tr", role="TEACHER", full_name="Pelin Tuna")
    # the coordinator is an ADMIN (owner decision 2026-10-17, R2-M-08: only planning.admin sets a person's priority)
    _pid, planner = await make_user(c, h, "selin.koordinator@uni.edu.tr", role="ADMIN", full_name="Selin Kordinatörova")
    async with dbmod.get_session_factory()() as s:
        ins = await s.get(Instructor, iid)
        assert ins is not None
        ins.user_id = uid
        own_names = {ins.full_name}
        # a co-instructor on the same section, with a name and an e-mail: never in Pelin's export
        co = (
            (
                await s.execute(
                    select(Instructor).where(Instructor.id != iid, Instructor.user_id.is_(None)).order_by(Instructor.id)
                )
            )
            .scalars()
            .first()
        )
        assert co is not None
        co.email = "eş.hoca@uni.edu.tr"
        if not (
            await s.execute(
                select(SectionInstructor).where(
                    SectionInstructor.section_id == sid, SectionInstructor.instructor_id == co.id
                )
            )
        ).scalar_one_or_none():
            s.add(SectionInstructor(section_id=sid, instructor_id=co.id, role="SECONDARY"))
        co_name = co.full_name
        await s.commit()

    # the wishes: one accepted, one rejected with a reason that names the coordinator
    r = await c.post(
        f"{API}/moderation/me/preferences",
        json={"kind": "room", "request_ids": [rid], "rooms": ["C 301"], "note": "Projeksiyonlu sınıf daha uygun"},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    acc = r.json()["items"][0]["id"]
    assert (
        await c.post(f"{API}/moderation/preferences/{acc}/decide", json={"decision": "accept"}, headers=planner)
    ).status_code == 200
    r = await c.post(
        f"{API}/moderation/me/preferences",
        json={"kind": "building", "request_ids": [rid], "buildings": ["a blok"]},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    rej = r.json()["items"][0]["id"]
    reason = "A blokta laboratuvar yok; Selin Kordinatörova ile görüşün"
    r = await c.post(
        f"{API}/moderation/preferences/{rej}/decide",
        json={"decision": "reject", "reason": reason, "reason_code": "capacity"},
        headers=planner,
    )
    assert r.status_code == 200, r.text
    # a coordinator's priority note about the person
    r = await c.put(
        f"{API}/moderation/people/{iid}/priority",
        json={"term_id": tid, "priority": "high", "note": "Engelli öğrencisi var"},
        headers=planner,
    )
    assert r.status_code == 200, r.text

    # Taleplerim: the rows the academician sees
    hist = (await c.get(f"{API}/moderation/people/{iid}/history", headers=teacher)).json()
    seen = sorted(it["request_id"] for g in hist["terms"] for it in g["items"])
    assert rid in seen

    r = await c.post(f"{API}/me/data-requests", json={"kind": "export"}, headers=teacher)
    assert r.status_code == 201, r.text
    r = await c.get(f"{API}/me/data-requests/{r.json()['id']}/download", headers=teacher)
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    data = json.loads(z.read("data.json"))
    readme = z.read("README.txt").decode("utf-8")
    for sec in OLD_SECTIONS + NEW_SECTIONS:
        assert sec in data, sec
        assert f"{sec}.csv" in names and f"{sec}.json" in names, sec
        assert json.loads(z.read(f"{sec}.json")) == data[sec], sec
        assert f"{sec}.csv" in readme, f"README does not explain {sec}.csv"

    # the instructor record and the sections they teach
    assert [i["id"] for i in data["instructor"]] == [iid]
    assert data["instructor"][0]["full_name"] in own_names
    mine_sec = next(x for x in data["instructor_sections"] if x["section_id"] == sid)
    assert mine_sec["course_code"] == "PTL 102" and mine_sec["role"] == "PRIMARY"
    others_on_it = mine_sec["other_instructors"]  # the real row already has a second instructor; plus ours
    assert "[Öğretim elemanı] (SECONDARY)" in others_on_it and all(
        x.startswith("[Öğretim elemanı] (") for x in others_on_it
    )

    # planning requests: exactly Taleplerim's rows, with the request text, requested -> assigned and the verdict
    assert sorted(x["request_id"] for x in data["planning_requests"]) == seen
    pr = next(x for x in data["planning_requests"] if x["request_id"] == rid)
    assert pr["term_code"] == "2026-BAHAR" and pr["course_code"] == "PTL 102"
    assert pr["requested"]["rooms"] and pr["verdict"] and pr["verdict_text"]
    assert "assigned" in pr and "reason" in pr and "request_text" in pr
    assert all(i.get("name") is None for i in pr["instructors"])

    # the wishes with the decision, the reason, and the coordinator by role only
    wishes = {w["id"]: w for w in data["teacher_preferences"]}
    assert set(wishes) == {acc, rej}
    assert wishes[acc]["status"] == "accepted" and wishes[acc]["note"] == "Projeksiyonlu sınıf daha uygun"
    assert wishes[rej]["status"] == "rejected" and wishes[rej]["reason_code"] == "capacity"
    assert wishes[rej]["reason"] == "A blokta laboratuvar yok; [Planlamacı] ile görüşün"
    assert wishes[rej]["decided_by"] == "Planlamacı / planner"

    # the coordinator's priority note about the person; the change audited with the person as its subject
    pn = next(x for x in data["priority_notes"] if x["term_code"] == "2026-BAHAR")
    assert pn["note"] == "Engelli öğrencisi var" and pn["updated_by"] == "Planlamacı / planner"
    acts = {a["action"] for a in data["audit_as_subject"]}
    assert "person.priority" in acts, acts
    assert all(
        a["actor"] in ("kendim / myself", "Planlamacı / planner", "Yönetici / administrator", "sistem / system")
        for a in data["audit_as_subject"]
    ), [(a["action"], a["actor"]) for a in data["audit_as_subject"]]

    # nobody else by name or e-mail, anywhere in the zip
    whole = fold("\n".join(z.read(n).decode("utf-8") for n in names))
    async with dbmod.get_session_factory()() as s:
        others = list((await s.execute(select(User).where(User.id != uid))).scalars())
        teachers = list((await s.execute(select(Instructor).where(Instructor.id != iid))).scalars())
    assert others and teachers
    for u in others:
        for v in (u.email, u.full_name):
            # "Administrator" (the seeded admin's name) is a role word, which the export prints as a role label
            if v and len(v) >= 3 and fold(v) not in ("administrator", "admin"):
                assert not _whole_words(whole, v), v
    assert not _whole_words(whole, co_name) and not _whole_words(whole, "eş.hoca@uni.edu.tr")
    # the Bahar list's column header names the planning office's person ("...Birimi-<ad> Bey tarafından...")
    assert not re.search(r"\w+ bey tarafindan", whole) and "[kisi] tarafindan" in whole
    leaks = [t.full_name for t in teachers if t.full_name and len(t.full_name) > 5 and _whole_words(whole, t.full_name)]
    assert leaks == [], leaks[:10]


async def test_notice_follows_the_readers_language(real: dict[str, Any]) -> None:  # noqa: F811
    c, h = real["client"], real["admin"]
    tid_, tr_user = await make_user(c, h, "tr.okur@uni.edu.tr", role="TEACHER")
    eid_, en_user = await make_user(c, h, "en.reader@uni.edu.tr", role="TEACHER")
    async with dbmod.get_session_factory()() as s:
        for uid, lang in ((tid_, "tr"), (eid_, "en")):
            u = await s.get(User, uid)
            assert u is not None
            u.language = lang
        await s.commit()

    async def publish(lang: str, title: str) -> dict[str, Any]:
        r = await c.post(
            f"{API}/admin/privacy-notices", json={"language": lang, "title": title, "body_md": title}, headers=h
        )
        assert r.status_code == 201, r.text
        r = await c.post(f"{API}/admin/privacy-notices/{r.json()['id']}/publish", headers=h)
        assert r.status_code == 200, r.text
        return dict(r.json())

    tr1 = await publish("tr", "Aydınlatma metni")
    en2 = await publish("en", "Privacy notice")  # a later version, English only
    assert en2["version"] > tr1["version"]
    me = (await c.get(f"{API}/me/privacy", headers=tr_user)).json()
    assert me["notice"]["language"] == "tr" and me["notice"]["id"] == tr1["id"] and me["needs_ack"] is True
    assert (await c.get(f"{API}/me/privacy", headers=en_user)).json()["notice"]["id"] == en2["id"]
    assert (await c.post(f"{API}/me/privacy/ack", json={"notice_id": tr1["id"]}, headers=tr_user)).status_code == 200
    assert (await c.get(f"{API}/me/privacy", headers=tr_user)).json()["needs_ack"] is False
    # the login page's notice follows ?lang= the same way
    assert (await c.get(f"{API}/public/privacy-notice", params={"lang": "tr"})).json()["id"] == tr1["id"]
    # a new Turkish version asks again
    tr3 = await publish("tr", "Aydınlatma metni (güncel)")
    me = (await c.get(f"{API}/me/privacy", headers=tr_user)).json()
    assert me["notice"]["id"] == tr3["id"] and me["needs_ack"] is True


async def test_permission_refusal_names_the_permission_in_turkish(real: dict[str, Any]) -> None:  # noqa: F811
    c, h = real["client"], real["admin"]
    _uid, teacher = await make_user(c, h, "izin.yok@uni.edu.tr", role="TEACHER")
    r = await c.get(f"{API}/learning/suggestions", headers=teacher)
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert d["code"] == "forbidden" and d["permission"] == "planning.view" and d["permissions"] == ["planning.view"]
    assert d["message_tr"] == 'Bu işlem için "Planlama verilerini görme" izni gerekiyor'
    assert d["message_en"] == d["message"] == "requires permission planning.view"  # the English text as before


def test_every_permission_has_a_turkish_name() -> None:
    """The guard's Turkish names are the Rol ve izinler screen's (``messages/tr.json`` ``crbs.perm``)."""
    from pathlib import Path

    from app.api.deps import PERMISSION_TR
    from app.services.bookings_perms import PERMISSION_NAMES

    assert set(PERMISSION_TR) >= set(PERMISSION_NAMES)
    msgs = Path(__file__).resolve().parents[2] / "frontend" / "messages" / "tr.json"
    perm = json.loads(msgs.read_text(encoding="utf-8"))["crbs"]["perm"]
    for name, label in PERMISSION_TR.items():
        key = name.replace(".", "_")
        if key in perm and isinstance(perm[key], str):
            assert perm[key] == label, name
