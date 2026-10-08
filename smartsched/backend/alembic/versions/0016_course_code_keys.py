"""Course codes: one course per code key (planner comparison follow-up, importer item 1b).

``SYS 18`` and ``SYS 018`` (``SYS 19`` / ``SYS 019``, ``SYS 23`` / ``SYS 023``, ``SYS 24`` / ``SYS 024``) are the
same lecture written with and without a leading zero.  The importers now look courses up by their code key
(``app.importers.normalize.course_key``: no spaces, ``İ`` folded, no leading zeros in the number), the same
normalisation the solver bridge's joint-lecture merge uses.  This data migration brings an existing database
in line: courses whose codes share a key are merged into the oldest one (its code and display spelling are
kept), sections are re-pointed, and the exam merge keys drop the leading zeros so ``SYS18`` and ``SYS018`` rows
of one slot merge into one exam.  Section and meeting identity keys keep the row's own spelling (re-imports
match as before).

Downgrade is a no-op (merged course rows are not split again).

Revision ID: 0016_course_code_keys
Revises: 0015_approvals
Create Date: 2026-10-08 17:40:00

"""

from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0016_course_code_keys"
down_revision = "0015_approvals"
branch_labels = None
depends_on = None

#: a frozen copy of ``app.importers.normalize.LEADING_ZEROS_RX`` (migrations never import app code)
_ZEROS = re.compile(r"(?<=[A-Za-zÇĞİÖŞÜçğıöşü ])0+(?=\d)")


def _key(code: str) -> str:
    up = re.sub(r"\s+", "", code or "").replace("i", "İ").replace("ı", "I").upper().replace("İ", "I")
    return _ZEROS.sub("", up)


def merge_course_keys(conn: Any) -> dict[str, int]:
    """Merge courses that share a code key; normalise exam merge keys.  Returns counts (for tests/logs)."""
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
