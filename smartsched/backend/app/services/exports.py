"""Exports: xlsx (reproduces the weekly grid board), csv, ics."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.export_safety import ics_text, neutralize_workbook, safe_writer
from app.importers.normalize import PERIODS
from app.models import Assignment, Room, ScheduleRun, Term
from app.services.calendar import date_for, day_label, period_times
from app.services.grid import assignment_labels, build_grid


async def _rows(session: AsyncSession, run: ScheduleRun) -> list[dict[str, Any]]:
    term = await session.get(Term, run.term_id)
    assert term is not None
    assignments = (
        (
            await session.execute(
                select(Assignment)
                .where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                .order_by(Assignment.week, Assignment.day, Assignment.start_period)
            )
        )
        .scalars()
        .all()
    )
    labels = await assignment_labels(session, list(assignments))
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    out = []
    for a in assignments:
        weeks = [int(w) for w in (a.weeks or ([a.week] if a.week else []))]
        start, end = period_times(a.start_period, a.end_period)
        d = a.date or (date_for(term, weeks[0], a.day) if len(weeks) == 1 else None)
        out.append(
            {
                "assignment_id": a.id,
                "label": labels[a.id],
                "week": a.week if a.week else ",".join(map(str, weeks)),
                "day": a.day,
                "day_label": day_label(a.day),
                "date": d.isoformat() if d else "",
                "start_period": a.start_period,
                "end_period": a.end_period,
                "start": start,
                "end": end,
                "rooms": " / ".join(rooms[int(r)].display_name for r in a.room_ids or [] if int(r) in rooms),
                "origin": a.origin,
                "locked": a.is_locked,
                "notes": a.notes or "",
                "_weeks": weeks,
                "_room_ids": [int(r) for r in a.room_ids or []],
            }
        )
    return out


async def export_csv(session: AsyncSession, run: ScheduleRun) -> str:
    rows = await _rows(session, run)
    buf = io.StringIO()
    fields = [
        k
        for k in (
            rows[0].keys()
            if rows
            else [
                "assignment_id",
                "label",
                "week",
                "day",
                "day_label",
                "date",
                "start_period",
                "end_period",
                "start",
                "end",
                "rooms",
                "origin",
                "locked",
                "notes",
            ]
        )
        if not k.startswith("_")
    ]
    w = safe_writer(csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore"))  # review M8
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _ics_escape(s: str) -> str:
    return ics_text(s)  # RFC 5545 escaping, no CR/LF (review M8)


async def export_ics(session: AsyncSession, run: ScheduleRun) -> str:
    term = await session.get(Term, run.term_id)
    assert term is not None
    rows = await _rows(session, run)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmartSched//EN", "CALSCALE:GREGORIAN"]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for r in rows:
        weeks = r["_weeks"] or [1]
        for wk in weeks:
            d = date_for(term, wk, r["day"])
            if d is None:
                continue
            sp, ep = PERIODS[r["start_period"] - 1].start, PERIODS[r["end_period"] - 1].end
            start = datetime.combine(d, sp)
            end = datetime.combine(d, ep)
            if end <= start:
                end = start + timedelta(minutes=40)
            lines += [
                "BEGIN:VEVENT",
                f"UID:smartsched-run{run.id}-a{r['assignment_id']}-w{wk}@smartsched",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{start:%Y%m%dT%H%M%S}",
                f"DTEND:{end:%Y%m%dT%H%M%S}",
                f"SUMMARY:{_ics_escape(r['label'])}",
                f"LOCATION:{_ics_escape(r['rooms'])}",
                f"DESCRIPTION:{_ics_escape(r['notes'])}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


_FILLS = {
    "YELLOW": "FFFF00",
    "ORANGE": "FFC000",
    "PURPLE": "7030A0",
    "BLUE": "00B0F0",
    "GREEN": "92D050",
    "block": "FFFF00",
    "locked": "D9D9D9",
}


async def export_xlsx(session: AsyncSession, run: ScheduleRun, weeks: list[int] | None = None) -> bytes:
    """One sheet per week laid out like the planner's board: day labels merged over the rooms, room
    headers with capacity, 18 time-slot rows, vertically merged multi-period lessons."""
    term = await session.get(Term, run.term_id)
    assert term is not None
    if not weeks:
        found = sorted(
            {
                int(w)
                for (ws, wk) in (
                    await session.execute(select(Assignment.weeks, Assignment.week).where(Assignment.run_id == run.id))
                ).all()
                for w in (ws or ([wk] if wk else []))
            }
        )
        weeks = found or [1]
    wb = Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for wk in weeks:
        grid = await build_grid(session, run, wk)
        ws = wb.create_sheet(title=f"Hafta {wk}"[:31])
        ws.cell(1, 1, term.code).font = bold
        col = 2
        rooms_per_day = len(grid["days"][0]["rooms"]) if grid["days"] else 0
        for day in grid["days"]:
            if rooms_per_day == 0:
                break
            label = f"{day['date']} {day['label']}" if day["date"] else day["label"]
            ws.cell(1, col, label).font = bold
            ws.cell(1, col).alignment = center
            if rooms_per_day > 1:
                ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + rooms_per_day - 1)
            for i, room in enumerate(day["rooms"]):
                c = col + i
                cap = room["exam_capacity"] if run.kind == "EXAM" and room["exam_capacity"] else room["capacity"]
                tags = "\n" + " ".join(room["tags"]) if room["tags"] else ""
                ws.cell(2, c, f"{room['display_name']}\n({cap}){tags}").alignment = center
                ws.cell(2, c).font = bold
                ws.column_dimensions[get_column_letter(c)].width = 11
                cells = room["cells"]
                p = 0
                while p < len(cells):
                    cell = cells[p]
                    if cell is None or not cell["head"]:
                        p += 1
                        continue
                    r0 = 3 + cell["start_period"] - 1
                    r1 = 3 + cell["end_period"] - 1
                    xc = ws.cell(r0, c, cell["label"])
                    xc.alignment = center
                    fill = None
                    if cell["kind"] == "block":
                        fill = _FILLS["block"]
                    elif cell.get("locked"):
                        fill = _FILLS["locked"]
                    for t in cell.get("tags") or []:
                        fill = _FILLS.get(str(t), fill)
                    if fill:
                        xc.fill = PatternFill("solid", fgColor=fill)
                    if r1 > r0:
                        ws.merge_cells(start_row=r0, start_column=c, end_row=r1, end_column=c)
                    p = cell["end_period"]
            col += rooms_per_day
        for i, per in enumerate(PERIODS):
            ws.cell(3 + i, 1, f"{per.start:%H:%M}-{per.end:%H:%M}").font = bold
        ws.column_dimensions["A"].width = 13
        ws.freeze_panes = "B3"
    buf = io.BytesIO()
    neutralize_workbook(wb)  # review M8: formula-like text becomes plain text
    wb.save(buf)
    return buf.getvalue()
