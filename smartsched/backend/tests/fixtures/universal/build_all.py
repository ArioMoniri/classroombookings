"""Rebuild every universal-council fixture from the real workbooks (run from ``smartsched/backend``).

python tests/fixtures/universal/build_all.py
"""

from __future__ import annotations

import build_english_csv
import build_exam_pdf
import build_rules_memo
import build_scan_png
import build_transposed_grid

if __name__ == "__main__":
    print("bahar_requests_en.csv:", build_english_csv.build(), "rows")
    print("final_exams_sheet.pdf:", build_exam_pdf.build(), "rows")
    notes, rooms = build_rules_memo.build()
    print(f"rules_memo.docx: {notes} notes, {rooms} rooms")
    cells, merges = build_transposed_grid.build()
    print(f"bahar_week1_transposed.xlsx: {cells} cells, {merges} merged ranges")
    print("final_exams_page1.png:", build_scan_png.build(), "bytes")
