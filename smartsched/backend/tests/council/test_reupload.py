"""Re-upload into a filled term (T-R1-25), without masking: commit the real Bahar list (planning-list importer, fast
path), then dry-run the list again and its English CSV export (general path) as new jobs against the same term.

The export holds the same requests read by another reader: the general writer matches them against the term's
committed rows (same section, days and times), takes only what a row lacks, and skips a file's second identical
row. What is left is the one row the planning-list importer refuses ('MDF-516', an unrecognised course code) and
the general reader accepts: a request the term really does not have yet."""

from __future__ import annotations

from tests.api_fixtures import login
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
