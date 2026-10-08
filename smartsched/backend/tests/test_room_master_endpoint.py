"""``POST /api/v1/imports/room-master`` (planner comparison §7.6: only the CLI could apply room_master.csv)."""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.conftest import FIXTURES
from tests.crbs_env import env  # noqa: F401

ROOM_MASTER = FIXTURES / "room_master.csv"


async def _upload(client, headers, path: Path, name: str | None = None):  # type: ignore[no-untyped-def]
    with path.open("rb") as f:
        return await client.post(
            "/api/v1/imports/room-master",
            files={"file": (name or path.name, f, "application/octet-stream")},
            headers=headers,
        )


async def _job(client, headers, r):  # type: ignore[no-untyped-def]
    assert r.status_code == 202, r.text
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{r.json()['id']}", headers=headers)).json()
    assert job["kind"] == "room-master" and job["status"] == "DONE", job
    return job


async def test_room_master_csv_through_the_api(client) -> None:
    h = await login(client)
    job = await _job(client, h, await _upload(client, h, ROOM_MASTER))
    assert job["summary"]["rows_imported"] == 87 and job["summary"]["extra"]["rooms"] == 87
    rooms = {r["code"]: r for r in (await client.get("/api/v1/rooms", headers=h)).json()}
    assert rooms["A204"]["capacity"] == 156 and rooms["A204"]["exam_capacity"] == 74
    assert "TIP" in rooms["A203"]["tags"] and "PC" in rooms["B207"]["tags"]
    # the uploaded file is kept with the job like every other import
    assert (await client.get(f"/api/v1/imports/{job['id']}/file", headers=h)).status_code == 200


async def test_room_master_xlsx_and_turkish_excel_csv(client, tmp_path) -> None:
    h = await login(client)
    rows = list(
        csv.reader(line for line in ROOM_MASTER.read_text(encoding="utf-8").splitlines() if not line.startswith("#"))
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append([int(v) if v.isdigit() else v for v in row])
    wb.save(tmp_path / "derslikler.xlsx")
    job = await _job(client, h, await _upload(client, h, tmp_path / "derslikler.xlsx"))
    assert job["summary"]["rows_imported"] == 87
    # Excel's Turkish "CSV (virgülle ayrılmış)" export: Windows-1254, semicolons, Turkish note text
    cp = tmp_path / "derslik_listesi.csv"
    cp.write_bytes("code;capacity;notes\nD 106;82;Güz panosu 60 diyor, Bahar 82\n".encode("cp1254"))
    job = await _job(client, h, await _upload(client, h, cp))
    rooms = {r["code"]: r for r in (await client.get("/api/v1/rooms", headers=h)).json()}
    assert rooms["D106"]["capacity"] == 82 and job["summary"]["warnings_count"] == 0


async def test_room_master_refuses_other_files(client, tmp_path) -> None:
    h = await login(client)
    bad = tmp_path / "rooms.pdf"
    bad.write_bytes(b"%PDF-1.4")
    r = await _upload(client, h, bad)
    assert r.status_code == 400 and ".csv or .xlsx" in r.json()["detail"]
    fake = tmp_path / "rooms.xlsx"
    fake.write_bytes(b"code,capacity\nA 101,58\n")  # not a zip container: refused by the safe-file check
    assert (await _upload(client, h, fake)).status_code == 400


async def test_room_master_permission(env) -> None:  # noqa: F811
    from tests.test_admin_gaps import _role

    rid = await _role(env, "Derslik yöneticisi", ["setup.rooms"])
    _, clerk = await env.user("derslik.master@uni.edu.tr", role=None, role_id=rid)
    _, teacher = await env.user("ogretmen.master@uni.edu.tr")
    assert (await _upload(env.client, teacher, ROOM_MASTER)).status_code == 403
    job = await _job(env.client, clerk, await _upload(env.client, clerk, ROOM_MASTER))
    assert job["summary"]["rows_imported"] == 87
