"""RF-08 (audit Part B "The xlsx files themselves", fix list 8): imports made by the CLI - the deploy seed among them -
are recorded like uploads. Each one becomes an ``import_jobs`` row with an actor (``system``; ``source`` ``seed`` or
``cli``), its report (counts, warnings, skipped rows) and the original file, so /import lists it and
``GET /imports/{id}/file`` downloads it. Uploads record who imported (``created_by_id``, ``actor = user``) and every
finished import writes an ``import.run`` audit event.

Real fixture files: room_master.csv and the Güz board.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app import cli
from app.core import db as dbmod
from app.models import AuditEvent, ImportJob
from app.workers.queue import get_queue
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401
from tests.conftest import FIXTURES, GUZ_GRID

API = "/api/v1"
ROOM_MASTER = FIXTURES / "room_master.csv"
REPO = Path(__file__).resolve().parents[3]


async def _cli(tmp_path: Path, *argv: str) -> int:
    args = cli.build_parser().parse_args(["--database-url", f"sqlite+aiosqlite:///{tmp_path}/api.db", *argv])
    return await cli._run_import(args)


async def _events(action: str) -> list[AuditEvent]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(AuditEvent).where(AuditEvent.action == action))).scalars())


async def test_seed_imports_show_in_history_with_actor_report_and_file(client, tmp_path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    assert await _cli(tmp_path, "import", "room-master", str(ROOM_MASTER), "--source", "seed") == 0
    assert (
        await _cli(
            tmp_path, "import", "weekly-grid", str(GUZ_GRID), "--term", "2026-GUZ", "--year", "2026", "--source", "seed"
        )
        == 0
    )
    jobs = (await client.get(f"{API}/imports", headers=h)).json()
    assert [j["kind"] for j in jobs] == ["weekly-grid", "room-master"]
    grid, master = jobs
    for j in jobs:
        assert j["status"] == "DONE" and j["actor"] == "system" and j["source"] == "seed"
        assert j["created_by_id"] is None and j["finished_at"] is not None
    assert grid["filename"] == GUZ_GRID.name and grid["term_code"] == "2026-GUZ"
    assert grid["summary"]["created"]["blocks"] > 600 and "warnings" in grid["summary"]
    assert master["summary"]["rows_imported"] > 50

    r = await client.get(f"{API}/imports/{grid['id']}/file", headers=h)
    assert r.status_code == 200 and r.content == GUZ_GRID.read_bytes()
    assert GUZ_GRID.name in r.headers["content-disposition"]
    r = await client.get(f"{API}/imports/{master['id']}/file", headers=h)
    assert r.status_code == 200 and r.content == ROOM_MASTER.read_bytes()

    runs = await _events("import.run")
    assert {(e.actor_type, e.actor_label, e.entity_id) for e in runs} == {
        ("system", "seed", str(grid["id"])),
        ("system", "seed", str(master["id"])),
    }
    assert runs[0].after is not None and runs[0].after["status"] == "DONE"


async def test_a_failed_cli_import_is_recorded_without_keeping_the_file(client, tmp_path) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    # the Güz board given as an exam list: refused by the header check
    assert await _cli(tmp_path, "import", "exam-list", str(GUZ_GRID), "--term", "2026-FINAL") != 0
    job = (await client.get(f"{API}/imports", headers=h)).json()[0]
    assert job["status"] == "FAILED" and job["actor"] == "system" and job["source"] == "cli" and job["error"]
    r = await client.get(f"{API}/imports/{job['id']}/file", headers=h)
    assert r.status_code == 404


async def test_upload_records_the_user_and_an_import_run_event(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    with ROOM_MASTER.open("rb") as f:
        r = await client.post(
            f"{API}/imports/room-master", files={"file": (ROOM_MASTER.name, f, "text/csv")}, headers=h
        )
    assert r.status_code == 202, r.text
    await get_queue().wait_idle()
    job = (await client.get(f"{API}/imports/{r.json()['id']}", headers=h)).json()
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    assert job["actor"] == "user" and job["created_by_id"] == me["id"] and job["source"] == "upload"
    assert job["created_by_name"]
    async with dbmod.get_session_factory()() as s:
        row = await s.get(ImportJob, job["id"])
        assert row is not None and row.created_by_id == me["id"]
    runs = await _events("import.run")
    assert [(e.actor_type, e.actor_id, e.entity_id) for e in runs] == [("user", me["id"], str(job["id"]))]


def test_the_deploy_seed_marks_its_imports_as_seed() -> None:
    spec = importlib.util.spec_from_file_location("rf08_seed", REPO / "smartsched/deploy/seed/seed.py")
    assert spec and spec.loader
    seed = importlib.util.module_from_spec(spec)
    sys.modules["rf08_seed"] = seed
    spec.loader.exec_module(seed)
    imports = [s for s in seed.INSTITUTION if s.argv[0] == "import"]
    assert len(imports) == 7
    for s in imports:
        assert s.argv[-2:] == ("--source", "seed"), s.name
        cli.build_parser().parse_args([a.replace("{files}", "/seed/files") for a in s.argv])  # the CLI accepts it
