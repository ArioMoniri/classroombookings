"""Re-upload into a filled term (T-R1-25), without masking: commit the real Bahar list (planning-list importer, fast
path), then dry-run the list again and its English CSV export (general path) as new jobs against the same term.

The export holds the same requests read by another reader: the general writer matches them against the term's
committed rows (same section, days and times), takes only what a row lacks, and skips a file's second identical
row. What is left is the one row the planning-list importer refuses ('MDF-516', an unrecognised course code) and
the general reader accepts: a request the term really does not have yet."""

from __future__ import annotations

import pytest

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
    # I5 / D14: the workbook's 1,511 requests, never a second copy of the rows the CSV already wrote
    total = await _active_meetings()
    # the general reader also accepts two rows the importer refuses (MDF-516: an unrecognised course code; PET 593: no
    # day): the term holds them once, from Job B
    assert 1511 <= total <= 1513, total
    # the workbook alone against this term: everything it knows is there and unchanged; it only archives the two
    probe = await _dry(
        client, h, (await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false"))["id"]
    )
    assert (
        _n(probe["counts"], "meeting_requests", "create") == 0
        and _n(probe["counts"], "meeting_requests", "unchanged") >= 1500
    )
    assert _n(probe["counts"], "meeting_requests", "update") <= total - 1511, probe["counts"]["meeting_requests"]
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


def _ui_body(job: dict) -> dict:
    """The body the onboarding commit panel sends: planner group 0 and the group's own guess of the term length
    (commit-panel.tsx: term.week_count = group.week_count) - 16 for the workbook + English CSV, 14 for the export."""
    g = job["plan"]["groups"][0]
    return {
        "group": 0,
        "term": {"code": "2026-BAHAR", "name": "2026 Bahar", "week_count": g["week_count"]},
        "allow_pending": True,
    }


@pytest.mark.parametrize("term_weeks", [19, None], ids=["term-exists-19-weeks", "term-made-by-the-first-commit"])
async def test_the_cp1254_export_after_the_workbook_rewrites_no_weeks(client, term_weeks):
    """R3-S-04 (T-R2-19): the staff tester's order on a fresh stack. The term exists (stack.sh makes it with 19
    weeks) or the first commit makes it; Job A (the workbook + its English CSV) is committed the way the UI sends
    it (the planner group's guess, 16 weeks); then the office's cp1254 ';' export of the same unchanged list (Job C,
    whose group guesses 14 weeks) is dry-run the same way. One term, one length: whatever the file guesses, the
    importers read 'Tüm dönem' as the term's weeks, so Job C rewrites no weeks and is >= 99 % unchanged."""
    h = await login(client)
    if term_weeks is not None:
        r = await client.post(
            "/api/v1/terms",
            headers=h,
            json={"code": "2026-BAHAR", "name": "2026 Bahar", "is_active": True, "week_count": term_weeks},
        )
        assert r.status_code == 201, r.text
    job_a = await upload(
        client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), (EN_CSV.name, EN_CSV.read_bytes()), ai="false"
    )
    r = await client.post(f"/api/v1/council/jobs/{job_a['id']}/commit", headers=h, json=_ui_body(job_a))
    assert r.status_code == 200, r.text

    cp = exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True)
    job_c = await upload(client, h, ("bahar_listesi_noktali_virgul.csv", cp), ai="false")
    assert job_c["files"][0]["route"] == "fast:planning-list", job_c["files"][0]
    r = await client.post(
        f"/api/v1/council/jobs/{job_c['id']}/commit", headers=h, json={**_ui_body(job_c), "dry_run": True}
    )
    assert r.status_code == 200, r.text
    dry = r.json()
    mr = dry["counts"]["meeting_requests"]
    weeks_rewritten = [
        row["id"]
        for row in dry["rows"]
        if row["entity"] == "meeting_requests" and any(f["field"] == "weeks" for f in row.get("fields") or [])
    ]
    assert weeks_rewritten == [], (len(weeks_rewritten), mr)
    assert _n(dry["counts"], "meeting_requests", "create") == 0, mr
    assert _share_unchanged(dry["counts"], "meeting_requests") >= 0.99, mr
    assert _share_unchanged(dry["counts"], "sections") >= 0.99, dry["counts"]["sections"]


def _cp1254() -> tuple[str, bytes]:
    return (
        "bahar_listesi_noktali_virgul.csv",
        exports.csv_bytes(BAHAR_LIST, delimiter=";", encoding="cp1254", decimal=",", dotted_times=True),
    )


def _xlsx() -> tuple[str, bytes]:
    return (BAHAR_LIST.name, BAHAR_LIST.read_bytes())


def _en_csv() -> tuple[str, bytes]:
    return (EN_CSV.name, EN_CSV.read_bytes())


async def _weeks_by_id() -> dict[int, list[int]]:
    from app.core.db import get_session_factory
    from app.models import MeetingRequest
    from sqlalchemy import select

    async with get_session_factory()() as s:
        rows = (await s.execute(select(MeetingRequest).where(MeetingRequest.archived.is_(False)))).scalars().all()
        return {m.id: list(m.weeks or []) for m in rows}


@pytest.mark.parametrize(
    ("first", "second", "same_list"),
    [(_xlsx, _xlsx, True), (_xlsx, _cp1254, True), (_cp1254, _xlsx, True), (_en_csv, _xlsx, False)],
    ids=["xlsx-then-xlsx", "xlsx-then-cp1254", "cp1254-then-xlsx", "en-csv-then-xlsx"],
)
async def test_an_unchanged_list_in_any_export_rewrites_no_weeks_in_a_19_week_term(client, first, second, same_list):
    """R3-M-02 / R3-S-04: the admin tester's fresh stack. 2026-BAHAR exists with 19 weeks; the first file is committed
    the way the UI sends it (the planner group's own guess of the length), the second is dry-run and then committed
    the way the tester called the API (``term_id`` only). Every request keeps the week list it had (the term's
    weeks, whatever reader or guess), checked row by row in the database. The same list in another format is also
    >= 99 % unchanged with nothing created; the English CSV is a shorter export (1,348 of the workbook's 1,524 rows),
    so after it the workbook adds its own rows and refines the rest, but rewrites no weeks."""
    h = await login(client)
    r = await client.post(
        "/api/v1/terms",
        headers=h,
        json={"code": "2026-BAHAR", "name": "2026 Bahar", "is_active": True, "week_count": 19},
    )
    assert r.status_code == 201, r.text
    term_id = r.json()["id"]
    job1 = await upload(client, h, first(), ai="false")
    r = await client.post(f"/api/v1/council/jobs/{job1['id']}/commit", headers=h, json=_ui_body(job1))
    assert r.status_code == 200, r.text
    before = await _weeks_by_id()
    assert before and max(max(w, default=0) for w in before.values()) <= 19  # never past the term's own length
    job2 = await upload(client, h, second(), ai="false")
    body = {"group": 0, "term_id": term_id, "allow_pending": True}
    r = await client.post(f"/api/v1/council/jobs/{job2['id']}/commit", headers=h, json={**body, "dry_run": True})
    assert r.status_code == 200, r.text
    dry = r.json()
    mr = dry["counts"]["meeting_requests"]
    if same_list:
        assert _n(dry["counts"], "meeting_requests", "create") == 0, mr
        assert _share_unchanged(dry["counts"], "meeting_requests") >= 0.99, mr
    r = await client.post(f"/api/v1/council/jobs/{job2['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    after = await _weeks_by_id()
    rewritten = [i for i, w in before.items() if i in after and after[i] != w]
    assert rewritten == [], (len(rewritten), mr)
