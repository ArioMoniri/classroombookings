"""Review M4: re-importing the real Bahar v5 planning list keeps meeting identity, skips unchanged rows,
keeps planner edits (conflict report) and remaps draft / rule ids of replaced rows. The modified workbook
copies are built here with openpyxl from the fixture."""

from __future__ import annotations

from pathlib import Path

import openpyxl
from app.core.db import get_session_factory
from app.importers.identity import is_legacy_key
from app.importers.planning_list import import_planning_list
from app.models import ConstraintRow, ImportedSnapshot, MeetingRequest, Section, StudioDraft
from sqlalchemy import select

from tests import studio_support
from tests.conftest import BAHAR_LIST
from tests.studio_support import meeting_id, room

bahar = studio_support.bahar

COL = {"day": 14, "start": 15, "end": 16, "venue": 17, "definitive": 18}  # 1-based columns of Sayfa1


def workbook_copy(dst: Path, edits: dict[tuple[int, str], object]) -> Path:
    """``BAHAR_LIST`` with cells ``(excel row, column name) -> value`` replaced."""
    wb = openpyxl.load_workbook(BAHAR_LIST, data_only=True)  # formulas -> their cached values
    ws = wb.worksheets[0]
    for (row, col), value in edits.items():
        ws.cell(row=row, column=COL[col]).value = value
    wb.save(dst)
    return dst


async def _mr(mid: int) -> MeetingRequest:
    async with get_session_factory()() as s:
        mr = await s.get(MeetingRequest, mid)
        assert mr is not None
        return mr


async def _reimport(path: Path, **kw):
    async with get_session_factory()() as s:
        return await import_planning_list(s, path, "2026-BAHAR", **kw)


async def test_m4_unchanged_reimport_writes_nothing_and_legacy_keys_migrate(bahar, tmp_path):
    same = workbook_copy(tmp_path / "same.xlsx", {})
    # simulate a database imported before the fix: content-hash keys
    async with get_session_factory()() as s:
        rows = list(
            (
                await s.execute(
                    select(MeetingRequest)
                    .join(Section)
                    .where(Section.term_id == bahar.term_id, MeetingRequest.archived.is_(False))
                )
            ).scalars()
        )
        before = {m.id for m in rows}
        for i, m in enumerate(rows):
            m.source_key = f"PL:2026-BAHAR:{i:016x}#0"
        await s.commit()
    rep = await _reimport(same)
    assert rep.extra["rekeyed_legacy"] == len(before)
    assert rep.created["meeting_requests"] == 0 and rep.updated["meeting_requests_archived"] == 0
    assert rep.updated["meeting_requests"] == 0, rep.updated
    assert rep.extra["unchanged"]["meeting_requests"] == rep.rows_imported
    async with get_session_factory()() as s:
        after = {
            m.id: m.source_key
            for m in (
                await s.execute(
                    select(MeetingRequest)
                    .join(Section)
                    .where(Section.term_id == bahar.term_id, MeetingRequest.archived.is_(False))
                )
            ).scalars()
        }
    assert set(after) == before and not any(is_legacy_key("2026-BAHAR", k) for k in after.values())


async def test_m4_reimport_keeps_identity_edits_and_remaps(bahar, tmp_path):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    phar240 = await meeting_id("PHAR 240", day=1, start=1)  # LOCKED, Mon P1-P3
    x = await meeting_id("PHAR 220", day=5, start=8)  # no definitive room yet
    venue_row = await meeting_id("PHAR 290", day=3, start=9)
    mx, m240, mv = await _mr(x), await _mr(phar240), await _mr(venue_row)
    # a meeting whose day changes in the new file (identity changes -> archived + new row)
    async with get_session_factory()() as s:
        w = (
            (
                await s.execute(
                    select(MeetingRequest)
                    .join(Section)
                    .where(
                        Section.term_id == bahar.term_id,
                        MeetingRequest.day == 2,
                        MeetingRequest.archived.is_(False),
                        MeetingRequest.id.not_in([x, phar240, venue_row]),
                    )
                    .order_by(MeetingRequest.id)
                )
            )
            .scalars()
            .first()
        )
        assert w is not None
        sibs = (
            (
                await s.execute(
                    select(MeetingRequest.id).where(
                        MeetingRequest.section_id == w.section_id, MeetingRequest.archived.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        rule = ConstraintRow(
            term_id=bahar.term_id, kind="room_forbid", params={"event_ids": [x, w.id], "room_ids": [1]},
            hardness="soft", weight=3, source="ADMIN", enabled=True,
        )  # fmt: skip
        s.add(rule)
        await s.commit()
        rule_id, w_id, w_row = rule.id, w.id, w.source_row_index
    a204 = (await room("A204")).id
    d = (await c.get(url, headers=h)).json()
    r = await c.put(
        url,
        json={"version": d["version"], "excluded_event_ids": [x, w_id], "pins": [{"event_id": x, "room_ids": [a204]}]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # the planner moves PHAR 240 to P2-P4 in the studio
    r = await c.put("/api/v1/studio/meetings/bulk", json={"ids": [phar240], "patch": {"start_period": 2}}, headers=h)
    assert r.json()["updated"] == 1

    new = workbook_copy(
        tmp_path / "v6.xlsx",
        {
            (mx.source_row_index, "definitive"): "A 105",  # the planning office fills the definitive room
            (m240.source_row_index, "start"): "10:10",  # the file moves PHAR 240 too: conflict
            (m240.source_row_index, "end"): "12:30",
            (mv.source_row_index, "venue"): "A 206",  # an unedited field changes: applied
            (w_row, "day"): "Perşembe",  # Tuesday -> Thursday: a new meeting replaces W
        },
    )
    rep = await _reimport(new)
    ex = rep.extra
    assert rep.created["meeting_requests"] == 1 and rep.updated["meeting_requests_archived"] == 1
    assert ex["unchanged"]["meeting_requests"] >= rep.rows_imported - 4
    assert 2 <= rep.updated["meeting_requests"] <= 3, rep.updated
    # identity survives filling in the definitive room
    mx2 = await _mr(x)
    assert not mx2.archived and mx2.definitive_room_ids == [(await room("A105")).id] and mx2.status == "LOCKED"
    assert (await _mr(venue_row)).requested_room_ids == [(await room("A206")).id]
    # the planner's edit is kept and reported
    m240b = await _mr(phar240)
    assert (m240b.start_period, m240b.end_period) == (2, 4)
    conflict = [cf for cf in ex["conflicts"] if cf["id"] == phar240 and cf["field"] == "start_period"]
    assert conflict and conflict[0]["planner"] == 2 and conflict[0]["file"] == 3 and conflict[0]["resolution"] == "kept"
    row = next(
        it
        for it in (await c.get(f"{url}/classes", params={"limit": 2000}, headers=h)).json()["items"]
        if it["id"] == phar240
    )
    assert {f["field"]: f["imported"] for f in row["changed_fields"]}["start_period"] == 3  # revert -> new file
    # ids of the replaced meeting are remapped in the draft and in the rule
    (new_w,) = [int(v) for k, v in ex["remapped_ids"].items() if int(k) == w_id]
    assert new_w not in sibs and (await _mr(w_id)).archived and (await _mr(new_w)).day == 4
    async with get_session_factory()() as s:
        draft = (
            await s.execute(
                select(StudioDraft).where(StudioDraft.term_id == bahar.term_id, StudioDraft.kind == "COURSE")
            )
        ).scalar_one()
        assert sorted(draft.excluded_event_ids) == sorted([x, new_w]) and draft.pins[0]["event_id"] == x
        assert (await s.get(ConstraintRow, rule_id)).params["event_ids"] == [x, new_w]
        snap = (
            await s.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == "meeting", ImportedSnapshot.entity_id == phar240
                )
            )
        ).scalar_one()
        assert snap.values["start_period"] == 3
    # "take" applies the file's values
    rep = await _reimport(new, on_conflict="take")
    assert (await _mr(phar240)).start_period == 3 and rep.extra["conflicts"][0]["resolution"] == "taken"
