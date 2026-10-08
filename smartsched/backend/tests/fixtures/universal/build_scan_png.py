"""Build ``final_exams_page1.png``: page 1 of ``final_exams_sheet.pdf`` rasterised, like a scanned printout.

The image has no text layer, so only the vision path (the model) can read it. Needs ``pdftoppm``
(poppler-utils) at build time only. Run ``build_exam_pdf.py`` first.
"""

from __future__ import annotations

import shutil
import subprocess

from _common import HERE

SRC = HERE / "final_exams_sheet.pdf"
OUT = HERE / "final_exams_page1.png"


def build() -> int:
    exe = shutil.which("pdftoppm")
    if exe is None:
        raise SystemExit("pdftoppm not found; install poppler-utils")
    stem = HERE / "final_exams_page1"
    subprocess.run([exe, "-png", "-r", "100", "-f", "1", "-l", "1", "-singlefile", str(SRC), str(stem)], check=True)
    return OUT.stat().st_size


if __name__ == "__main__":
    print(f"{OUT.name}: {build()} bytes")
