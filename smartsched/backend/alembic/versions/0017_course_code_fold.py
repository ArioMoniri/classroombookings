"""Course codes: Turkish letters folded in the code key (product-owner decision 2026-10-15).

``ÇEV 101`` and ``CEV 101`` are one course, and so are ``İŞL101`` and ``ISL101`` (review D10): the importers'
code key (``app.importers.normalize.course_key``) now folds Ç→C, Ş→S, Ğ→G, Ü→U, Ö→O, İ/I→I, in addition to the
0016 rules (no spaces, no leading zeros in the number). This data migration applies the wider key to an
existing database exactly like 0016 did: courses sharing a key are merged into the oldest one (its code and
``display_code``, i.e. the planner's first spelling, are kept), sections are re-pointed, and exam merge keys
use the folded code so the rows of one slot merge into one exam.

Downgrade is a no-op (merged course rows are not split again).

Revision ID: 0017_course_code_fold
Revises: 0016_course_code_keys
Create Date: 2026-10-15 15:30:00

"""

from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0017_course_code_fold"
down_revision = "0016_course_code_keys"
branch_labels = None
depends_on = None

#: frozen copies of ``normalize.LEADING_ZEROS_RX`` and ``normalize._CODE_FOLD`` (migrations never import app code)
_ZEROS = re.compile(r"(?<=[A-Za-zÇĞİÖŞÜçğıöşü ])0+(?=\d)")
_FOLD = str.maketrans("ÇŞĞÜÖİ", "CSGUOI")


def _key(code: str) -> str:
    up = re.sub(r"\s+", "", code or "").replace("i", "İ").replace("ı", "I").upper().replace("İ", "I")
    return _ZEROS.sub("", up.translate(_FOLD))


def merge_course_keys(conn: Any) -> dict[str, int]:
    """Merge courses that share a folded code key; fold exam merge keys.  Returns counts (for tests/logs)."""
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    merged = 0
    if {"courses", "sections"} <= tables:
        rows = conn.execute(sa.text("SELECT id, code FROM courses ORDER BY id")).all()
        keep: dict[str, int] = {}
        for cid, code in rows:
            k = _key(str(code or ""))
            if k not in keep:
                keep[k] = int(cid)
                continue
            conn.execute(
                sa.text("UPDATE sections SET course_id = :keep WHERE course_id = :dup"), {"keep": keep[k], "dup": cid}
            )
            conn.execute(sa.text("DELETE FROM courses WHERE id = :dup"), {"dup": cid})
            merged += 1
    exams = 0
    if "exam_requests" in tables:
        for eid, mk in conn.execute(
            sa.text("SELECT id, merge_key FROM exam_requests WHERE merge_key IS NOT NULL")
        ).all():
            parts = str(mk).rsplit(":", 3)
            if len(parts) != 4:
                continue
            new = ":".join([parts[0], _key(parts[1]), parts[2], parts[3]])
            if new != mk:
                conn.execute(sa.text("UPDATE exam_requests SET merge_key = :mk WHERE id = :id"), {"mk": new, "id": eid})
                exams += 1
    return {"courses_merged": merged, "exam_merge_keys": exams}


def upgrade() -> None:
    merge_course_keys(op.get_bind())


def downgrade() -> None:
    pass
