"""Build ``final_exams_sheet.pdf``: one real sheet printed to PDF, as a planning office would e-mail it.

* Source: ``tests/fixtures/final_planlama_listesi_2026_v2.xlsx``, sheet ``Sayfa1``, the first
  ``ROWS`` rows that have a course code, in order.
* Eight of the sheet's columns are printed (a print area), with the sheet's own Turkish headers cut
  to the column width the way Excel's "fit to page" output looks. Every page repeats the header row.
* Text is drawn cell by cell at fixed column positions on landscape A4, so the PDF has a real text
  layer (no scan). The Intake agent must recover the columns from the layout.

Needs ``reportlab`` and a TrueType font with Turkish glyphs (DejaVu Sans on most Linux systems); both
are build-time only, not backend dependencies.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
from _common import EXAM_LIST, HERE, cell_text

OUT = HERE / "final_exams_sheet.pdf"
ROWS = 120

#: (source column index, header as printed, column width in points)
COLUMNS = [
    (3, "Ders Kodu", 62),
    (4, "Ders Adı", 170),
    (5, "Öğr. Sayısı", 58),
    (6, "Öğretim Elemanı", 150),
    (7, "Sınav Tarihi", 68),
    (8, "Başlangıç Saati", 72),
    (9, "Bitiş Saati", 60),
    (11, "Kesinleşen Derslik", 110),
]

FONT_CANDIDATES = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("/Library/Fonts/DejaVuSans.ttf"),
]


def _font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in FONT_CANDIDATES:
        if path.exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(path)))
            return "DejaVuSans"
    raise SystemExit("DejaVu Sans not found; install fonts-dejavu-core")


def _fit(text: str, width: float, font: str, size: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    text = " ".join(text.split())
    while text and stringWidth(text, font, size) > width - 6:
        text = text[:-1]
    return text


def build() -> int:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    wb = openpyxl.load_workbook(EXAM_LIST, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows: list[list[str]] = []
    for values in ws.iter_rows(min_row=2, max_col=14, values_only=True):
        if not cell_text(values[3]):
            continue
        rows.append([cell_text(values[idx]) for idx, _, _ in COLUMNS])
        if len(rows) >= ROWS:
            break
    wb.close()

    font, size, leading = _font(), 7.5, 11
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(str(OUT), pagesize=(page_w, page_h), invariant=1)
    c.setTitle("2026 Final Planlama Listesi - Sayfa1")
    xs: list[float] = []
    x = 30.0
    for _, _, w in COLUMNS:
        xs.append(x)
        x += w
    per_page = int((page_h - 90) // leading)
    for start in range(0, len(rows), per_page):
        c.setFont(font, 10)
        c.drawString(30, page_h - 36, "2026 Final Planlama Listesi v2 — Sayfa1")
        y = page_h - 60
        c.setFont(font, size)
        for (_, header, w), x in zip(COLUMNS, xs, strict=True):
            c.drawString(x, y, _fit(header, w, font, size))
        y -= leading
        for row in rows[start : start + per_page]:
            for text, (_, _, w), x in zip(row, COLUMNS, xs, strict=True):
                c.drawString(x, y, _fit(text, w, font, size))
            y -= leading
        c.showPage()
    c.save()
    return len(rows)


if __name__ == "__main__":
    print(f"{OUT.name}: {build()} rows")
