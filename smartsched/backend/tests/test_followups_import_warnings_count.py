"""Backend follow-ups 2026-10-16 item 6 (admin persona M-21): the import job summary says how many warnings there are
in all (``warnings_count``) next to the first 500 it lists, so the import report can say "507 uyarı, ilk 500
gösteriliyor" (``warnings_shown``, ``warnings_truncated``); a viewer, who never sees the warning texts, still gets
the counts. Real file: the 2026 Bahar planning list."""

from __future__ import annotations

from app.importers.report import ImportReport
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST
from tests.crbs_support import make_user


def test_report_counts_every_warning_and_says_when_the_list_is_cut() -> None:
    rep = ImportReport(kind="weekly-grid")
    for i in range(507):
        rep.warn(f"room A 103 has capacity 47 and 33 ({i})", row=i + 3)
    d = rep.to_dict()
    assert d["warnings_count"] == 507 and len(d["warnings"]) == 500
    assert d["warnings_shown"] == 500 and d["warnings_truncated"] is True
    small = ImportReport(kind="planning-list")
    small.warn("unparseable start time", row=12)
    s = small.to_dict()
    assert s["warnings_count"] == s["warnings_shown"] == 1 and s["warnings_truncated"] is False


async def test_bahar_list_job_summary_carries_the_warning_counts(client) -> None:  # type: ignore[no-untyped-def]
    h = await login(client)
    with BAHAR_LIST.open("rb") as f:
        r = await client.post(
            "/api/v1/imports/planning-list",
            files={"file": (BAHAR_LIST.name, f, "application/octet-stream")},
            data={"term_code": "2026-BAHAR"},
            headers=h,
        )
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{job_id}", headers=h)).json()
    assert job["status"] == "DONE", job
    s = job["summary"]
    assert s["warnings_count"] > 0 and s["warnings_shown"] == len(s["warnings"]) <= 500
    assert s["warnings_truncated"] is (s["warnings_count"] > s["warnings_shown"])
    assert sum(w["count"] for w in s["warning_summary"]) <= s["warnings_count"]
    print(f"Bahar planning list: {s['warnings_count']} warnings, {s['warnings_shown']} listed")
    # the job list carries the same counts (the import history table)
    listed = next(j for j in (await client.get("/api/v1/imports", headers=h)).json() if j["id"] == job_id)
    assert listed["summary"]["warnings_count"] == s["warnings_count"]
    # a viewer gets the counts, never the texts
    _vid, viewer = await make_user(client, h, "izleyici@uni.edu.tr", role="VIEWER")
    vjob = (await client.get(f"/api/v1/imports/{job_id}", headers=viewer)).json()
    assert vjob["summary"]["redacted"] is True and "warnings" not in vjob["summary"]
    assert vjob["summary"]["warnings_count"] == s["warnings_count"]
    assert vjob["summary"]["warnings_truncated"] is s["warnings_truncated"]
    assert vjob["summary"]["warnings_shown"] == s["warnings_shown"]
