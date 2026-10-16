"""Re-upload into a filled term (T-R1-25), without masking: commit the real Bahar list, then dry-run its English CSV
export (and the list itself) as new jobs against the same term. Nothing new may be planned: the export holds the
same requests and the same people."""

from __future__ import annotations

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST, EN_CSV
from tests.council.test_formats_api import upload

BODY = {"group": 0, "term": {"code": "2026-BAHAR", "week_count": 14}, "allow_pending": True}


async def _commit(client, h, job_id: int, dry: bool) -> dict:
    r = await client.post(f"/api/v1/council/jobs/{job_id}/commit", headers=h, json={**BODY, "dry_run": dry})
    assert r.status_code == 200, r.text
    return r.json()


async def test_reupload_of_the_export_plans_nothing_new(client):
    h = await login(client)
    first = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false")
    await _commit(client, h, first["id"], dry=False)

    again = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()), ai="false")
    counts = (await _commit(client, h, again["id"], dry=True))["counts"]
    print("XLSX", {k: v for k, v in counts.items()})
    export = await upload(client, h, (EN_CSV.name, EN_CSV.read_bytes()), ai="false")
    counts_csv = (await _commit(client, h, export["id"], dry=True))["counts"]
    print("CSV", {k: v for k, v in counts_csv.items()})
    assert counts.get("meeting_requests", {}).get("create", 0) == 0
    assert counts.get("instructors", {}).get("create", 0) == 0
    assert counts_csv.get("meeting_requests", {}).get("create", 0) == 0
    assert counts_csv.get("instructors", {}).get("create", 0) == 0
