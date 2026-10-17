"""Re-upload into a filled term (T-R1-25), without masking: commit the real Bahar list (planning-list importer, fast
path), then dry-run the list again and its English CSV export (general path) as new jobs against the same term.

The export holds the same requests read by another reader: the general writer matches them against the term's
committed rows (same section, days and times), takes only what a row lacks, and skips a file's second identical
row. What is left is the one row the planning-list importer refuses ('MDF-516', an unrecognised course code) and
the general reader accepts: a request the term really does not have yet."""

from __future__ import annotations

from tests.api_fixtures import login
from tests.council import exports
from tests.council.conftest import BAHAR_LIST, EN_CSV
from tests.council.test_formats_api import upload

BODY = {"group": 0, "term": {"code": "2026-BAHAR", "week_count": 14}, "allow_pending": True}


async def _dry(client, h, job_id: int) -> dict:
    r = await client.post(f"/api/v1/council/jobs/{job_id}/commit", headers=h, json={**BODY, "dry_run": True})
    assert r.status_code == 200, r.text
    return r.json()


def _n(counts: dict, entity: str, change: str) -> int:
    return int(counts.get(entity, {}).get(change, 0))


async def test_reupload_of_the_list_and_its_export_plans_nothing_new(client):
    h = await login(client)
    first = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false")
    r = await client.post(f"/api/v1/council/jobs/{first['id']}/commit", headers=h, json=BODY)
    assert r.status_code == 200, r.text

    again = await _dry(client, h, (await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes())))["id"])
    for entity in ("meeting_requests", "sections", "instructors", "section_instructors"):
        assert _n(again["counts"], entity, "create") == 0, (entity, again["counts"])
    assert _n(again["counts"], "meeting_requests", "update") == 0

    export = await _dry(client, h, (await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), ai="false"))["id"])
    c = export["counts"]
    created = [row for row in export["rows"] if row["change"] == "create"]
    # only the MDF-516 request the importer refused: its course, section, request and its one teacher
    assert [row["key"] for row in created if row["entity"] == "courses"] == ["MDF516"]
    assert _n(c, "meeting_requests", "create") == 1 and _n(c, "sections", "create") == 1
    assert _n(c, "instructors", "create") <= 1
    # the export does not rewrite what the importer read (weeks, flags, notes): at most a filled-in gap
    assert _n(c, "meeting_requests", "update") <= 1 and _n(c, "meeting_requests", "unchanged") > 1300


async def _active_meetings() -> int:
    from app.core.db import get_session_factory
    from app.models import MeetingRequest
    from sqlalchemy import func, select

    async with get_session_factory()() as s:
        q = select(func.count()).select_from(MeetingRequest).where(MeetingRequest.archived.is_(False))
        return int((await s.execute(q)).scalar_one())


def _share_unchanged(counts: dict, entity: str) -> float:
    c = counts.get(entity, {})
    total = sum(int(c.get(k, 0)) for k in ("create", "update", "unchanged", "conflict"))
    return int(c.get("unchanged", 0)) / total if total else 0.0


async def test_general_then_fast_path_share_one_key_and_the_dry_run_predicts_the_commit(client):
    """R2-M-06 / T-R2-19, the tester's order on a fresh term. Job B: the English CSV (general path) committed
    first. Job A (the Bahar workbook, fast path, with the same CSV): the dry run's per-entity counts equal the
    commit's, and the importer finds the general writer's rows under the one natural key (``PL:<term>:id:…#n``,
    app.importers.identity.meeting_identity), so the term holds each request once. Job D (the CSV again): nothing
    to create or update. Job C (Turkish Excel's cp1254 ';' export of the list, fast path): >= 99 % unchanged."""
    h = await login(client)
    job_b = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), ai="false")
    r = await client.post(f"/api/v1/council/jobs/{job_b['id']}/commit", headers=h, json=BODY)
    assert r.status_code == 200, r.text
    b = r.json()
    n_b = _n(b["changes"], "meeting_requests", "create")
    assert n_b > 1300 and await _active_meetings() == n_b

    job_a = await upload(
        client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), (EN_CSV.name, EN_CSV.read_bytes()), ai="false"
    )
    dry_a = await _dry(client, h, job_a["id"])
    r = await client.post(f"/api/v1/council/jobs/{job_a['id']}/commit", headers=h, json=BODY)
    assert r.status_code == 200, r.text
    real_a = r.json()
    # I4: the dry run predicts the commit, entity by entity
    assert real_a["changes"] == dry_a["counts"], (real_a["changes"], dry_a["counts"])
    # I5 / D14: the workbook's 1,511 requests + the one row the importer refuses (MDF-516) - never a second copy
    # of the rows the CSV already wrote
    total = await _active_meetings()
    import json as _j
    print("DBG_GENERAL", _j.dumps(real_a["general"]), _j.dumps(dry_a["counts"]["meeting_requests"]))
    print("DBG_CREATED", _j.dumps([r for r in dry_a["rows"] if r["change"] == "create" and r["entity"] in ("meeting_requests", "sections")], ensure_ascii=False)[:3000])
    print("DBG_UPDATED", _j.dumps([r for r in dry_a["rows"] if r["change"] == "update" and r["entity"] == "meeting_requests"][:8], ensure_ascii=False)[:3000])
    import json as _j
    probe = await _dry(client, h, (await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false"))["id"])
    print("DBG_PROBE", _j.dumps(probe["counts"].get("meeting_requests")), _j.dumps(probe["result"]["fast_path"][0]["updated"]))
    print("DBG_PROBE_ROWS", _j.dumps([r for r in probe["rows"] if r["entity"] == "meeting_requests"][:6], ensure_ascii=False)[:2500])
    from app.core.db import get_session_factory as _gsf
    from app.models import MeetingRequest as _MR, Section as _S, Course as _Co, Program as _P
    from sqlalchemy import select as _sel
    async with _gsf()() as _s:
        for r in [r for r in probe["rows"] if r["entity"] == "meeting_requests"][:6]:
            mr = await _s.get(_MR, r["id"])
            sec = await _s.get(_S, mr.section_id)
            co = await _s.get(_Co, sec.course_id)
            print("DBG_ROW", co.code, sec.label, sec.source_key, mr.days, str(mr.start_time), mr.source_key, mr.source_row_index, mr.archived)
    assert 1511 <= total <= 1512, total
    assert _n(dry_a["counts"], "meeting_requests", "create") <= total - n_b + 1, dry_a["counts"]["meeting_requests"]

    # Job D: the same CSV once more: every row is there already
    job_d = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), ai="false")
    dry_d = await _dry(client, h, job_d["id"])
    for entity in ("meeting_requests", "sections", "instructors", "section_instructors", "courses"):
        assert _n(dry_d["counts"], entity, "create") == 0, (entity, dry_d["counts"])
    assert _n(dry_d["counts"], "meeting_requests", "update") == 0, dry_d["counts"]["meeting_requests"]
    assert (
        _n(dry_d["counts"], "meeting_requests", "unchanged")
        + int(dry_d["result"]["general"].get("duplicates_skipped", 0))
        >= n_b
    ), (dry_d["counts"], dry_d["result"]["general"])
    assert await _active_meetings() == total

    # Job C: the office's cp1254 ';' export of the same list (fast path): the importer's own rows, unchanged
    cp = exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True)
    job_c = await upload(client, h, ("bahar_listesi_noktali_virgul.csv", cp), ai="false")
    assert job_c["files"][0]["route"] == "fast:planning-list", job_c["files"][0]
    dry_c = await _dry(client, h, job_c["id"])
    assert _n(dry_c["counts"], "meeting_requests", "create") == 0, dry_c["counts"]["meeting_requests"]
    assert _share_unchanged(dry_c["counts"], "meeting_requests") >= 0.99, dry_c["counts"]["meeting_requests"]
    assert _share_unchanged(dry_c["counts"], "sections") >= 0.99, dry_c["counts"]["sections"]
