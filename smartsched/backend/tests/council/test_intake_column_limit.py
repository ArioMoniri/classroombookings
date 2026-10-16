"""The /onboarding intake (council API) accepts the real university exports whose sheets declare formatted
columns out to XFD, while sheets with more than ``sheet_max_cols`` *used* columns are still refused.

Regression for the README recording (2026-10-16): the owner's Bahar and Güz planning lists were refused with
"16376 columns, limit 1024" although only 25-26 columns hold values; the CLI importer reads them fine."""

from __future__ import annotations

import io
import zipfile

import pytest
from app.core import safe_files
from app.council import formats
from app.importers.planning_list import parse_planning_list

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST, GUZ_LIST
from tests.council.test_formats_api import refused, upload

# the names the owner's files carry (Turkish İ/ü/ğ in the filename must not matter)
REAL = [(BAHAR_LIST, "Bahar Derslik Planlama Listesi v5.xlsx"), (GUZ_LIST, "2026-2027 Güz Derslik Planlama v2.xlsx")]


def _xlsx(sheet_xml: str) -> bytes:
    """A minimal valid workbook with one worksheet body (``<sheetData>`` and friends)."""
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sayfa1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + sheet_xml + "</worksheet>"
        ),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in parts.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _styled_to_xfd(rows: int = 40, data_cols: int = 30) -> bytes:
    """Data in ``data_cols`` columns; every row also carries styled empty cells out to XFD (as Excel writes a
    sheet whose whole rows were formatted), and the dimension declares A1:XFD<rows>."""
    out = [f'<dimension ref="A1:XFD{rows}"/><sheetData>']
    for r in range(1, rows + 1):
        cells = [f'<c r="{_col(c)}{r}" t="inlineStr"><is><t>Ders {r}.{c}</t></is></c>' for c in range(1, data_cols + 1)]
        cells += [f'<c r="{_col(c)}{r}" s="1"/>' for c in (data_cols + 1, 1000, 5000, 16_384)]
        out.append(f'<row r="{r}" spans="1:16384">{"".join(cells)}</row>')
    out.append("</sheetData>")
    return _xlsx("".join(out))


def _wide_data(cols: int = 1100, rows: int = 3) -> bytes:
    """More than 1024 columns that really hold values."""
    out = ["<sheetData>"]
    for r in range(1, rows + 1):
        cells = "".join(f'<c r="{_col(c)}{r}"><v>{c}</v></c>' for c in range(1, cols + 1))
        out.append(f'<row r="{r}">{cells}</row>')
    out.append("</sheetData>")
    return _xlsx("".join(out))


@pytest.mark.parametrize(("path", "name"), REAL, ids=["bahar", "guz"])
def test_real_planning_lists_pass_the_full_load_caps(path, name):
    """The caps (rows, columns, cells, merges) measure used cells: the real lists' declared 16 375 columns
    are styles, and the strict full-load check (the board importer's) accepts them."""
    data = path.read_bytes()
    rep = safe_files.inspect_zip(data)
    sheet = rep.sheets["xl/worksheets/sheet1.xml"]
    assert sheet.cols <= 30, sheet  # 25-26 populated columns, not the styled XFD range
    safe_files.check_full_load(rep, safe_files.Limits.from_settings())
    assert formats.precheck(name, data) == "xlsx"


async def test_onboarding_accepts_the_real_bahar_and_guz_lists(client):
    """Both owner files through POST /council/jobs (what /onboarding calls): accepted, read by the planning-list
    importer, and every row the CLI importer reads (``python -m app.cli import planning-list``) is a record."""
    h = await login(client)
    job = await upload(client, h, *[(name, path.read_bytes()) for path, name in REAL])
    assert job["status"] in ("DONE", "REVIEW", "READY"), job.get("error")
    for (path, name), f in zip(REAL, job["files"], strict=True):
        assert f["filename"] == name
        assert f["status"] == "DONE", (f["status"], f["message"])
        assert f["route"] == "fast:planning-list"
        cli_rows = len(parse_planning_list(path).rows)
        assert cli_rows > 1000  # Bahar 1 5xx, Güz 1 0xx
        assert f["counts"].get("meeting") == cli_rows, f["counts"]


async def test_styles_out_to_xfd_with_30_data_columns_are_accepted(client):
    data = _styled_to_xfd()
    rep = safe_files.inspect_zip(data)
    ext = rep.sheets["xl/worksheets/sheet1.xml"]
    assert (ext.cols, ext.rows) == (30, 40)
    safe_files.check_full_load(rep, safe_files.Limits.from_settings())  # strict 1024-column cap
    wb = safe_files.open_workbook(data, read_only=True)
    assert wb.worksheets[0].max_column == 30
    wb = safe_files.open_workbook(data, read_only=False)  # the board importer's full load
    assert wb.worksheets[0].cell(1, 30).value == "Ders 1.30"
    h = await login(client)
    job = await upload(client, h, ("styled_xfd.xlsx", data))
    f = job["files"][0]
    assert f["status"] == "DONE", (f["status"], f["message"])


async def test_more_than_1024_real_data_columns_are_still_refused(client):
    data = _wide_data()
    with pytest.raises(safe_files.UnsafeFileError) as exc:
        safe_files.check_full_load(safe_files.inspect_zip(data), safe_files.Limits.from_settings())
    assert exc.value.status == 413 and "1100 columns" in exc.value.message
    h = await login(client)
    status, text = await refused(client, h, "wide.xlsx", data)
    assert status == 413, text
    assert "1100 columns" in text and "limit 1024" in text
