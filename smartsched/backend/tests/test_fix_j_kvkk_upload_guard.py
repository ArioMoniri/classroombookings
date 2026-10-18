"""FIX-J (E2EA-F01, E2EA2-F02): on a recording / test stack (``KVKK_UPLOAD_GUARD=1``, dev or test only) an
upload that still carries full person names, or that is byte-for-byte one of the seed workbooks, is refused
before it is stored or previewed. Masked copies (title + initials) pass. Every name here is synthetic."""

from __future__ import annotations

import io
import json

import pytest
from app.core import kvkk_guard
from app.core.config import get_settings
from openpyxl import Workbook

from tests.api_fixtures import login
from tests.conftest import BAHAR_LIST

#: synthetic people (never a real name)
NAMES = ["Deneme Örnekoğlu", "Sentetik Kişi Yapayoğlu"]


def _xlsx(cells: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Ders Kodu", "Öğretim Elemanı"])
    for c in cells:
        ws.append(["TST 101", c])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def guard(tmp_path, monkeypatch):
    names = tmp_path / "kvkk-names.json"
    names.write_text(json.dumps(NAMES), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "kvkk_upload_guard", True)
    monkeypatch.setattr(get_settings(), "kvkk_names_file", str(names))
    kvkk_guard.reset_cache()
    yield
    kvkk_guard.reset_cache()


def test_names_found_in_cells_comments_and_free_text(guard) -> None:
    assert kvkk_guard.unmasked_hits(_xlsx(["Dr. Öğr. Üyesi Deneme ÖRNEKOĞLU"]), "x.xlsx") == 1
    assert kvkk_guard.unmasked_hits(_xlsx(["Prof.Dr.Kişi Yapayoğlu, Arş. Gör. X"]), "x.xlsx") == 1
    assert kvkk_guard.unmasked_hits("kod;hoca\nTST 101;Sentetik Kişi Yapayoğlu\n".encode(), "x.csv") == 1


def test_masked_text_passes(guard) -> None:
    assert kvkk_guard.unmasked_hits(_xlsx(["Dr. Öğr. Üyesi D. Ö.", "S. K. Y."]), "x.xlsx") == 0
    assert kvkk_guard.unmasked_hits("kod;hoca\nTST 101;D. Ö.\n".encode(), "x.csv") == 0


def test_seed_workbook_is_refused_by_hash(guard) -> None:
    assert kvkk_guard.is_seed_workbook(BAHAR_LIST.read_bytes())
    assert not kvkk_guard.is_seed_workbook(_xlsx(["D. Ö."]))


def test_guard_is_off_by_default_and_never_in_prod(monkeypatch) -> None:
    kvkk_guard.reset_cache()
    assert not kvkk_guard.active()
    monkeypatch.setattr(get_settings(), "kvkk_upload_guard", True)
    assert kvkk_guard.active()
    monkeypatch.setattr(get_settings(), "environment", "prod")
    assert not kvkk_guard.active()


async def test_import_refuses_unmasked_upload_and_keeps_nothing(client, guard) -> None:
    h = await login(client)
    r = await client.post(
        "/api/v1/imports/planning-list",
        files={"file": ("liste.xlsx", _xlsx(["Dr. Deneme Örnekoğlu"]), "application/octet-stream")},
        data={"term_code": "2026-BAHAR", "dry_run": "true"},
        headers=h,
    )
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "kvkk_unmasked_names"
    assert "maskelenmemiş" in d["message_tr"] and "unmasked" in d["message_en"]
    assert "Örnekoğlu" not in json.dumps(d, ensure_ascii=False)  # the message never repeats a name
    jobs = (await client.get("/api/v1/imports", headers=h)).json()
    rows = jobs if isinstance(jobs, list) else jobs.get("items", [])
    assert all(j["status"] == "FAILED" for j in rows)
    from app.services import import_jobs

    assert all(not import_jobs.job_files(j["id"]) for j in rows)


async def test_import_refuses_the_raw_seed_workbook(client, guard) -> None:
    h = await login(client)
    r = await client.post(
        "/api/v1/imports/planning-list",
        files={"file": (BAHAR_LIST.name, BAHAR_LIST.read_bytes(), "application/octet-stream")},
        data={"term_code": "2026-BAHAR", "dry_run": "true"},
        headers=h,
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "kvkk_seed_workbook"
    assert "maskelenmiş kopya" in r.json()["detail"]["message_tr"]


async def test_import_accepts_a_masked_upload(client, guard) -> None:
    h = await login(client)
    r = await client.post(
        "/api/v1/imports/planning-list",
        files={"file": ("liste.xlsx", _xlsx(["Dr. D. Ö."]), "application/octet-stream")},
        data={"term_code": "2026-BAHAR", "dry_run": "true"},
        headers=h,
    )
    assert r.status_code == 202, r.text


async def test_council_refuses_unmasked_upload(client, guard) -> None:
    h = await login(client)
    r = await client.post(
        "/api/v1/council/jobs",
        files=[("files", ("liste.xlsx", _xlsx(["Sentetik Kişi Yapayoğlu"]), "application/octet-stream"))],
        data={"ai": "false"},
        headers=h,
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "kvkk_unmasked_names"
