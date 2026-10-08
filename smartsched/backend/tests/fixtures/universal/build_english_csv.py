"""Build ``bahar_requests_en.csv``: the real Bahar planning list as an English CSV.

* Source: ``tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx``, sheet 1. Every row that has a course
  code and a day (the meetings an institution would actually send) is copied, in order.
* The headers are translated to English, and the column order is changed (an institution's export
  rarely matches ours).
* Day names and delivery modes are translated with the fixed tables in ``_common``. Course names,
  programmes, instructors and notes stay as written (real data, not machine-translated).
* Times are written as ``HH:MM`` and the delimiter is a comma, as most English-locale exports do.
"""

from __future__ import annotations

import csv

import openpyxl
from _common import BAHAR_LIST, HERE, cell_text, translate_days, translate_mode

OUT = HERE / "bahar_requests_en.csv"

#: (English header, source column index in the Turkish sheet)
COLUMNS = [
    ("Course Code", 4),
    ("Course Title", 5),
    ("Section", 6),
    ("Department", 1),
    ("Faculty", 0),
    ("Year of Study", 2),
    ("Expected Students", 12),
    ("Weekday", 13),
    ("Start Time", 14),
    ("End Time", 15),
    ("Requested Room", 16),
    ("Assigned Room", 17),
    ("Lecturer", 18),
    ("Second Lecturer", 19),
    ("Delivery Mode", 20),
    ("Remarks", 21),
    ("Weeks", 23),
]


def build() -> int:
    wb = openpyxl.load_workbook(BAHAR_LIST, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows: list[list[str]] = []
    for values in ws.iter_rows(min_row=2, max_col=26, values_only=True):
        code = cell_text(values[4])
        day = cell_text(values[13])
        if not code or not day:
            continue
        out = []
        for header, idx in COLUMNS:
            text = cell_text(values[idx])
            if header == "Weekday":
                text = translate_days(text)
            elif header == "Delivery Mode":
                text = translate_mode(text)
            out.append(text)
        rows.append(out)
    wb.close()
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([h for h, _ in COLUMNS])
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    print(f"{OUT.name}: {build()} rows")
