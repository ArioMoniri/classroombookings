"""Studio rules: meta/templates, affected-count preview, copy between terms/runs, presets, the no-AI
column-mapping fallback for preference sheets and accept with ``constraints.source_ref``."""

from __future__ import annotations

import io
import json

from app.core.db import get_session_factory
from app.models import ConstraintRow, Course, MeetingRequest, Program, ScheduleRun, Section, Term
from openpyxl import Workbook
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import meeting_id, room

bahar = studio_support.bahar


async def _program(name: str) -> Program:
    async with get_session_factory()() as s:
        return (await s.execute(select(Program).where(Program.name == name))).scalar_one()


async def _rule(b, **body):
    r = await b.client.post("/api/v1/constraints", json={"term_id": b.term_id, **body}, headers=b.planner)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_meta_weight_scale_and_templates(bahar):
    m = (await bahar.client.get("/api/v1/studio/meta", headers=bahar.planner)).json()
    assert (m["weight_scale"]["low"], m["weight_scale"]["normal"], m["weight_scale"]["high"]) == (2, 5, 8)
    assert len(m["templates"]) == 14 and len({t["id"] for t in m["templates"]}) == 14
    kinds = {k["kind"] for k in m["catalog"]}
    assert all(t["kind"] in kinds and t["title"]["tr"] and t["sentence"]["en"] for t in m["templates"])
    waste = next(t for t in m["templates"] if t["kind"] == "min_capacity_waste")
    assert waste["allowed_hardness"] == ["soft"] and waste["default_weight"] == 2
    assert {b["kind"]: b["disableable"] for b in m["builtins"]}["no_room_overlap"] is False
    assert len(m["periods"]) == 18 and m["periods"][11]["start"] == "17:30"


async def test_preview_counts_match_the_class_list(bahar):
    ecz = await _program("Eczacılık")
    url = "/api/v1/studio/constraints/preview"
    body = {
        "term_id": bahar.term_id,
        "kind": "building_preference",
        "params": {"program": ecz.canonical_name, "building": "C"},
    }
    p = (await bahar.client.post(url, json=body, headers=bahar.planner)).json()
    assert p["affected_count"] > 10 and p["targeted"] and p["issues"] == [] and p["sample"]
    assert p["total"] > 800 and 0 < p["percent"] < 50
    rid = await _rule(bahar, kind="building_preference", params=body["params"], hardness="soft", weight=5)
    listed = (
        await bahar.client.get(
            f"/api/v1/terms/{bahar.term_id}/studio/classes",
            params={"rule_id": rid, "limit": 2000},
            headers=bahar.planner,
        )
    ).json()
    assert listed["total"] == p["affected_count"]
    phar = await meeting_id("PHAR 240", day=1, start=1)
    one = (
        await bahar.client.post(
            url, json={**body, "params": {"event_ids": [phar], "building": "C"}}, headers=bahar.planner
        )
    ).json()
    assert one["affected_count"] == 1 and one["sample"][0]["label"] == "PHAR 240 §1"
    none = (
        await bahar.client.post(url, json={**body, "params": {"program": "yok böyle program"}}, headers=bahar.planner)
    ).json()
    assert none["affected_count"] == 0 and "matches_none" in none["notes"]
    most = (
        await bahar.client.post(
            url,
            json={
                "term_id": bahar.term_id,
                "kind": "room_tags",
                "params": {"forbidden_tags": ["PC"]},
                "hardness": "hard",
            },
            headers=bahar.planner,
        )
    ).json()
    assert not most["targeted"] and most["percent"] == 100.0 and "affects_most" in most["notes"]
    bad = (await bahar.client.post(url, json={**body, "params": {"room_ids": "A206"}}, headers=bahar.planner)).json()
    assert bad["issues"]
    # left-out classes are not counted: exclude PHAR 240 §1 in the draft
    await bahar.client.get(f"/api/v1/terms/{bahar.term_id}/studio", headers=bahar.planner)
    await bahar.client.put(
        f"/api/v1/terms/{bahar.term_id}/studio",
        json={"version": 1, "excluded_event_ids": [phar]},
        headers=bahar.planner,
    )
    one = (
        await bahar.client.post(
            url, json={**body, "params": {"event_ids": [phar], "building": "C"}}, headers=bahar.planner
        )
    ).json()
    assert one["affected_count"] == 0


async def test_copy_rules_between_terms_and_from_a_run(bahar):
    c, h = bahar.client, bahar.planner
    ecz = await _program("Eczacılık")
    phar = await meeting_id("PHAR 240", day=1, start=1)
    r_course = await _rule(
        bahar,
        kind="room_preference",
        params={"event_ids": [phar], "room_ids": [12]},
        hardness="soft",
        weight=8,
        nl_text="PHAR 240 A 206'da",
    )
    r_prog = await _rule(
        bahar,
        kind="building_preference",
        params={"program": ecz.canonical_name, "building": "C"},
        hardness="soft",
        weight=5,
    )
    r_room = await _rule(bahar, kind="room_pin", params={"event_ids": [phar], "room_ids": [999999]}, hardness="hard")
    # a small next term with the same PHAR 240 §1 (Mon P1-P3) and nothing else
    async with get_session_factory()() as s:
        nxt = Term(code="2026-YAZ", name="Yaz 2026", week_count=8)
        s.add(nxt)
        await s.flush()
        course = (await s.execute(select(Course).where(Course.code == "PHAR240"))).scalar_one()
        sec = Section(
            term_id=nxt.id,
            course_id=course.id,
            program_id=ecz.id,
            label="1",
            class_year=2,
            class_years=[2],
            enrolment=40,
            source_key="yaz-phar240-1",
        )
        s.add(sec)
        await s.flush()
        mr = MeetingRequest(
            section_id=sec.id, day=1, days=[1], start_period=1, end_period=3, weeks=[1, 2, 3], status="PARSED"
        )
        s.add(mr)
        await s.commit()
        nxt_id, new_mr = nxt.id, mr.id
    body = {
        "to_term_id": nxt_id,
        "from_term_id": bahar.term_id,
        "constraint_ids": [r_course, r_prog, r_room],
        "dry_run": True,
    }
    r = await c.post("/api/v1/studio/constraints/copy", json=body, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["source_id"] for x in out["will_match"]] == [r_course, r_prog]
    assert out["will_match"][0]["params"]["event_ids"] == [new_mr] and out["will_match"][0]["affected_count"] == 1
    assert [x["source_id"] for x in out["cannot_match"]] == [r_room] and "not bookable" in out["cannot_match"][0][
        "reasons"
    ][0]
    assert out["created"] == [] and out["dry_run"] is True
    r = await c.post("/api/v1/studio/constraints/copy", json={**body, "dry_run": False}, headers=h)
    created = r.json()["created"]
    assert len(created) == 2
    async with get_session_factory()() as s:
        row = await s.get(ConstraintRow, created[0])
        assert row.term_id == nxt_id and row.params["event_ids"] == [new_mr] and row.weight == 8
        assert row.source_ref["copied_from"] == {"term_id": bahar.term_id, "run_id": None, "constraint_id": r_course}
    # copying again: identical rules already exist
    again = (await c.post("/api/v1/studio/constraints/copy", json={**body, "dry_run": False}, headers=h)).json()
    assert again["created"] == [] and all("already exists" in " ".join(x["reasons"]) for x in again["cannot_match"][:2])
    # from a run: its run-scoped rules + the term's rules
    async with get_session_factory()() as s:
        run = ScheduleRun(term_id=bahar.term_id, kind="COURSE", status="FEASIBLE")
        s.add(run)
        await s.flush()
        s.add(
            ConstraintRow(
                run_id=run.id, kind="min_capacity_waste", params={"unit": 10}, hardness="soft", weight=2, source="AI"
            )
        )
        await s.commit()
        run_id = run.id
    r = await c.post(
        "/api/v1/studio/constraints/copy",
        json={"to_term_id": bahar.term_id, "from_run_id": run_id, "dry_run": True},
        headers=h,
    )
    out = r.json()
    assert [x["kind"] for x in out["will_match"]] == ["min_capacity_waste"]  # the term's own rules already exist
    assert r.status_code == 200 and len(out["cannot_match"]) == 3
    assert (
        await c.post("/api/v1/studio/constraints/copy", json={"to_term_id": bahar.term_id}, headers=h)
    ).status_code == 422


async def test_presets_crud_and_apply(bahar):
    c = bahar.client
    ecz = await _program("Eczacılık")
    keep = await _rule(
        bahar,
        kind="building_preference",
        params={"program": ecz.canonical_name, "building": "C"},
        hardness="soft",
        weight=5,
    )
    drop = await _rule(bahar, kind="min_capacity_waste", params={"unit": 10}, hardness="soft", weight=2)
    preset = {
        "name": "Bahar standard",
        "kind": "COURSE",
        "rules": [
            {
                "kind": "building_preference",
                "params": {"program": ecz.canonical_name, "building": "C"},
                "hardness": "soft",
                "weight": 8,
            },
            {"kind": "min_capacity_waste", "params": {"unit": 10}, "hardness": "soft", "weight": 2, "enabled": False},
            {
                "kind": "room_preference",
                "params": {
                    "courses": [{"code": "PHAR 240", "label": "1", "program": ecz.canonical_name}],
                    "room_codes": ["A 206"],
                },
                "hardness": "soft",
                "weight": 5,
                "nl_text": "PHAR 240 A 206'da kalsın",
            },
            {
                "kind": "room_forbid",
                "params": {"room_codes": ["Z 999"], "courses": [{"code": "XYZ 999"}]},
                "hardness": "hard",
            },
        ],
        "scope": {"horizon": "WEEK", "horizon_params": {"weeks": [3]}},
        "filters": {"include_only": {"program": ecz.canonical_name}},
    }
    r = await c.post("/api/v1/presets", json=preset, headers=bahar.planner)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["author"] == "Fatih Bey"
    assert [p["id"] for p in (await c.get("/api/v1/presets", headers=bahar.admin)).json()] == [pid]  # university-wide
    r = await c.post(
        f"/api/v1/presets/{pid}/apply", json={"term_id": bahar.term_id, "dry_run": True}, headers=bahar.planner
    )
    assert r.status_code == 200, r.text
    diff = r.json()
    assert [x["kind"] for x in diff["add"]] == ["room_preference"]
    assert [x["constraint_id"] for x in diff["change"]] == [keep] and diff["change"][0]["from"]["weight"] == 5
    assert [x["constraint_id"] for x in diff["turn_off"]] == [drop]
    assert [u["kind"] for u in diff["unresolved"]] == ["room_forbid"] and diff["draft"] is None
    phar_ids = {await meeting_id("PHAR 240", day=1, start=1)}
    assert set(diff["add"][0]["params"]["event_ids"]) >= phar_ids
    assert diff["add"][0]["params"]["room_ids"] == [(await room("A206")).id]
    r = await c.post(f"/api/v1/presets/{pid}/apply", json={"term_id": bahar.term_id}, headers=bahar.planner)
    res = r.json()
    assert len(res["created"]) == 1
    d = res["draft"]
    assert d["preset_id"] == pid and d["scope"]["weeks"] == [3] and d["disabled_rule_ids"] == [drop]
    assert d["rule_overrides"] == {str(keep): {"hardness": "soft", "weight": 8}}
    assert 1000 < len(d["excluded_event_ids"]) < 1524 and res["excluded_count"] == len(d["excluded_event_ids"])
    async with get_session_factory()() as s:
        row = await s.get(ConstraintRow, res["created"][0])
        assert row.source_ref == {"preset_id": pid, "preset": "Bahar standard"}
    # save the current draft as a preset (names, not ids)
    r = await c.post("/api/v1/presets", json={"name": "Snapshot", "from_term_id": bahar.term_id}, headers=bahar.planner)
    snap = r.json()
    assert snap["scope"] == {"horizon": "WEEK", "horizon_params": {"weeks": [3]}}
    pref = next(x for x in snap["rules"] if x["kind"] == "room_preference")
    assert "event_ids" not in pref["params"] and pref["params"]["room_codes"] == ["A206"]
    assert pref["params"]["courses"][0]["code"] == "PHAR240"
    assert next(x for x in snap["rules"] if x["kind"] == "min_capacity_waste")["enabled"] is False
    # edit: author or admin; delete: admin only
    assert (await c.put(f"/api/v1/presets/{pid}", json={"name": "Bahar std"}, headers=bahar.planner)).json()[
        "name"
    ] == "Bahar std"
    assert (await c.delete(f"/api/v1/presets/{pid}", headers=bahar.planner)).status_code == 403
    assert (await c.delete(f"/api/v1/presets/{pid}", headers=bahar.admin)).status_code == 204
    assert (await c.get(f"/api/v1/presets/{pid}", headers=bahar.planner)).status_code == 404


def _prefs_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Talepler"
    ws.append(["Eczacılık Fakültesi derslik talepleri"])
    ws.append(["Ders Kodu", "Şube", "Bölüm", "Derslik", "Öğrenci Sayısı", "Gün", "Saat", "Açıklama"])
    ws.append(["PHAR 240", "1", "Eczacılık", "A 206, A 207", None, None, None, None])
    ws.append(["PSİ 116", None, "Psikoloji", "C Blok", 95, None, None, None])
    ws.append(["PHAR\xa0290", "1", "Eczacılık", None, None, "Çarşamba", "13.30-15.50", None])
    ws.append([None, None, None, None, None, None, None, "Lütfen sabah dersi olmasın"])
    ws.append(["XYZ 999", None, None, "A 206", None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_mapping_fallback_without_ai_and_accept_with_source_ref(bahar):
    c, h = bahar.client, bahar.planner
    url = f"/api/v1/terms/{bahar.term_id}/studio/preferences/mapping"
    files = {
        "file": (
            "eczacilik_talepler.xlsx",
            _prefs_xlsx(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    r = await c.post(url, files=files, headers=h)
    assert r.status_code == 200, r.text
    cols = r.json()
    assert cols["mode"] == "columns" and cols["header_row"] == 2 and cols["row_count"] == 5
    sug = cols["suggested_mapping"]["columns"]
    assert sug == {"course": 0, "section": 1, "program": 2, "room": 3, "enrolment": 4, "day": 5, "time": 6, "note": 7}
    assert cols["columns"][0]["samples"][:2] == ["PHAR 240", "PSİ 116"]
    mapping = {"columns": sug, "room_rule": "prefer", "weight": 8}
    r = await c.post(url, files=files, data={"mapping": json.dumps(mapping)}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    props = out["proposals"]
    assert [p["kind"] for p in props] == ["room_preference", "building_preference", "room_preference"]
    pref = props[0]
    assert pref["status"] == "ok" and pref["source"] == "UPLOAD" and pref["weight"] == 8 and pref["hardness"] == "soft"
    assert pref["source_ref"]["file"] == "eczacilik_talepler.xlsx" and pref["source_ref"]["row"] == 3
    assert pref["params"]["room_ids"] == [(await room("A206")).id, (await room("A207")).id]
    phar = await meeting_id("PHAR 240", day=1, start=1)
    assert phar in pref["params"]["event_ids"]
    assert props[1]["params"]["building"] == "C" and props[1]["source_ref"]["row"] == 4
    assert props[2]["status"] == "needs_review" and props[2]["source_ref"]["row"] == 7  # XYZ 999 is not in the term
    edits = out["section_edits"]
    assert [(e["source_ref"]["row"], e["changes"]) for e in edits] == [
        (
            4,
            {
                "enrolment": 95,
                "day": None,
                "start_period": None,
                "end_period": None,
                "mode": None,
                "preferred_room_ids": None,
            },
        ),
        (
            5,
            {"enrolment": None, "day": 3, "start_period": 7, "end_period": 9, "mode": None, "preferred_room_ids": None},
        ),
    ]
    assert [u["source_ref"]["row"] for u in out["unparsed"]] == [6]
    print(
        json.dumps(
            [(p["kind"], p["status"], p["issues"]) for p in props] + [(e["status"], e["issues"]) for e in edits],
            ensure_ascii=False,
        )
    )
    assert out["counts"] == {"ready": 4, "needs_look": 1, "couldnt_read": 1}
    # bad mapping / file type
    assert (await c.post(url, files=files, data={"mapping": "{nope"}, headers=h)).status_code == 422
    assert (await c.post(url, files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=h)).status_code == 400
    # accept the ready rule cards: the provenance lands in constraints.source_ref
    ready = [p for p in props if p["status"] == "ok"]
    r = await c.post(
        f"/api/v1/terms/{bahar.term_id}/studio/proposals/accept",
        json={"proposals": ready, "section_edits": edits[:1]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    acc = r.json()
    assert len(acc["created"]) == 2 and acc["rejected"] == [] and len(acc["section_edits_applied"]) == 1
    async with get_session_factory()() as s:
        rows = [await s.get(ConstraintRow, i) for i in acc["created"]]
    assert all(x.source == "UPLOAD" and "_source_ref" not in x.params for x in rows)
    ref = rows[0].source_ref
    assert ref["file"] == "eczacilik_talepler.xlsx" and ref["row"] == 3 and "PHAR 240" in ref["excerpt"]
    rules = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio/rules", headers=h)).json()["rules"]
    assert next(x for x in rules if x["id"] == acc["created"][0])["source_ref"]["file"] == "eczacilik_talepler.xlsx"


async def test_minor7_copied_rules_that_need_review_land_in_the_tray(bahar):
    """A copied rule with some classes missing in the target term is reported, not created."""
    c, h = bahar.client, bahar.planner
    phar = await meeting_id("PHAR 240", day=1, start=1)
    other = await meeting_id("PHAR 290", day=3, start=9)
    rid = await _rule(
        bahar, kind="room_preference", params={"event_ids": [phar, other], "room_ids": [12]}, hardness="soft", weight=4
    )
    ecz = await _program("Eczacılık")
    async with get_session_factory()() as s:
        nxt = Term(code="2026-YAZ2", name="Yaz", week_count=8)
        s.add(nxt)
        await s.flush()
        course = (await s.execute(select(Course).where(Course.code == "PHAR240"))).scalar_one()
        sec = Section(
            term_id=nxt.id,
            course_id=course.id,
            program_id=ecz.id,
            label="1",
            class_year=2,
            class_years=[2],
            enrolment=40,
            source_key="yaz2-phar240-1",
        )
        s.add(sec)
        await s.flush()
        s.add(
            MeetingRequest(section_id=sec.id, day=1, days=[1], start_period=1, end_period=3, weeks=[1], status="PARSED")
        )
        await s.commit()
        nxt_id = nxt.id
    out = (
        await c.post(
            "/api/v1/studio/constraints/copy",
            json={"to_term_id": nxt_id, "from_term_id": bahar.term_id, "constraint_ids": [rid], "dry_run": False},
            headers=h,
        )
    ).json()
    assert [x["source_id"] for x in out["needs_review"]] == [rid] and out["created"] == []
    assert out["needs_review"][0]["created_id"] is None
