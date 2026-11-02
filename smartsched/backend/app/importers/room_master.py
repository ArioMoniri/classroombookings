"""Room master: the planner's authoritative room list (``python -m app.cli import room-master file.csv`` or
``POST /api/v1/imports/room-master``; a CSV, or an ``.xlsx`` whose first sheet has the same columns).

Columns (header row required, order free, ``;`` or ``,`` delimited, UTF-8 with or without BOM):

``code, capacity, exam_capacity, tags, building, floor, bookable[, notes, owner_faculty, merged_from]``

* ``code``: any spelling the importers understand (``A 101``, ``C z01``, ``B Blok Bilg. Lab.``).
* ``capacity`` / ``exam_capacity``: integers; an empty cell leaves the stored value unchanged.
* ``tags``: ``PC``, ``TIP``, … separated by ``|``, ``;``, ``/`` or spaces; the cell *replaces* the tag
  list (``-`` clears it); empty = unchanged.
* ``building``: building code (``A``); ``floor``: free text (``0`` = ground floor).
* ``bookable``: ``1/0``, ``yes/no``, ``true/false``, ``evet/hayır``; empty = derived (bookable when the
  room has a capacity).
* ``owner_faculty`` (optional): the faculty that owns the room (``Tıp Fakültesi``); only its members (and
  administrators) may book it (app/services/room_faculty.py). ``-`` clears it; empty = unchanged.
* ``merged_from`` (optional): codes of rooms merged into this one (``B 407``), separated like tags. Those rooms are
  retired and their future bookings move here when the slot is free (else they are reported).
* Lines starting with ``#`` are comments.

Values set here are marked in ``custom_fields.master`` and are never overwritten by a later workbook
import (the workbook value is reported as a warning instead).

The master is the authoritative room list (owner report 2026-11-02 item 1), applied as an idempotent upsert:

* a room an earlier master listed (``custom_fields.master`` set) that this file no longer lists, or a room named in
  ``merged_from``, is **retired**: not bookable, ``custom_fields.retired`` says why and since when. It is never
  deleted: bookings, runs and the import history keep pointing at it. Its future bookings are reported (merged
  rooms: moved first); a later master that lists it again brings it back;
* rooms only the workbooks know (never in a master) are left alone;
* every ungrouped bookable room joins its building's room group (``A Blok`` ...), so the booking grid and
  "Boş derslik bul" show it (``app/services/room_groups.py``).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_files import Limits, UnsafeFileError, is_zip_container, open_workbook, run_isolated
from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.models.booking import BOOKED, PENDING, Booking, BookingSlot
from app.models.catalog import Room

COLUMNS = (
    "code",
    "capacity",
    "exam_capacity",
    "tags",
    "building",
    "floor",
    "bookable",
    "notes",
    "owner_faculty",
    "merged_from",
)
_TRUE = {"1", "yes", "y", "true", "evet", "e", "x"}
_FALSE = {"0", "no", "n", "false", "hayır", "hayir", "h"}


def _bool(value: str | None) -> bool | None:
    v = n.tr_casefold(value or "").strip()
    if not v:
        return None
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"not a yes/no value: {value!r}")


def _int(value: str | None) -> int | None:
    v = (value or "").strip()
    if not v:
        return None
    out = n.parse_int_loose(v)
    if out is None or out < 0:
        raise ValueError(f"not a non-negative integer: {value!r}")
    return out


def _tags(value: str | None) -> list[str] | None:
    v = (value or "").strip()
    if not v:
        return None
    if v == "-":
        return []
    parts = [n.tr_upper(t.strip()) for t in v.replace("|", " ").replace(";", " ").replace("/", " ").split()]
    return list(dict.fromkeys(p for p in parts if p))


def _codes(value: str | None, line: int) -> list[str]:
    v = (value or "").strip()
    if not v:
        return []
    out: list[str] = []
    for part in v.replace("|", ";").replace("/", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        codes = n.parse_room_codes(part)
        if len(codes) != 1:
            raise ValueError(f"cannot read merged room code {part!r}")
        out.append(codes[0])
    return list(dict.fromkeys(out))


def parse_room_master(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse the CSV text into row dicts (typed values, ``None`` = unchanged) and error strings."""
    lines = [ln for ln in text.lstrip("﻿").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return [], ["empty room master"]
    dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
    reader = csv.DictReader(io.StringIO("\n".join(lines)), dialect=dialect)
    header = [n.tr_casefold(h or "").strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    if "code" not in header:
        return [], [f"room master needs a 'code' column; got {header}"]
    unknown = [h for h in header if h and h not in COLUMNS]
    errors: list[str] = [f"unknown column(s) ignored: {unknown}"] if unknown else []
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(reader, start=2):
        codes = n.parse_room_codes(raw.get("code"))
        if len(codes) != 1:
            errors.append(f"line {i}: cannot read room code {raw.get('code')!r}")
            continue
        try:
            rows.append(
                {
                    "line": i,
                    "code": codes[0],
                    "capacity": _int(raw.get("capacity")),
                    "exam_capacity": _int(raw.get("exam_capacity")),
                    "tags": _tags(raw.get("tags")),
                    "building": (raw.get("building") or "").strip().upper() or None,
                    "floor": (raw.get("floor") or "").strip() or None,
                    "bookable": _bool(raw.get("bookable")),
                    "notes": (raw.get("notes") or "").strip() or None,
                    "owner_faculty": (raw.get("owner_faculty") or "").strip() or None,
                    "merged_from": _codes(raw.get("merged_from"), i),
                }
            )
        except ValueError as exc:
            errors.append(f"line {i}: {exc}")
    return rows, errors


def xlsx_to_csv_text(path: str | Path) -> str:
    """The first sheet of a room-master workbook as ``;`` separated text (header row first), read with the
    safe workbook reader (zip pre-inspection, row / column caps)."""
    wb = open_workbook(path, read_only=True, data_only=True, max_rows=5000, max_cols=len(COLUMNS) + 4)
    try:
        ws = wb.worksheets[0]
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";", lineterminator="\n")
        for values in ws.iter_rows(values_only=True):
            cells = [
                "" if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v) for v in values
            ]
            if any(c.strip() for c in cells):
                writer.writerow(cells)
        return buf.getvalue()
    finally:
        wb.close()


def read_room_master_text(path: str | Path) -> str:
    """CSV text of a room master: UTF-8 (with or without BOM), else Windows-1254 (Turkish Excel's "CSV"
    export); ``.xlsx`` / ``.xlsm`` workbooks are converted from their first sheet."""
    if is_zip_container(Path(path).name):
        return xlsx_to_csv_text(path)
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1254")


async def import_room_master(session: AsyncSession, path: str | Path, *, filename: str | None = None) -> ImportReport:
    """Apply a room master (CSV or xlsx, see the module doc) - the CLI ``import room-master`` and
    ``POST /imports/room-master``."""
    report = ImportReport(kind="room-master", filename=filename or Path(path).name)
    cap = Limits.from_settings().max_upload_bytes
    if Path(path).stat().st_size > cap:
        raise UnsafeFileError(413, f"room master larger than {cap // (1024 * 1024)} MiB")
    if is_zip_container(Path(path).name):
        text = await run_isolated(xlsx_to_csv_text, path)  # off the loop, memory-capped child
    else:
        text = read_room_master_text(path)
    rows, errors = parse_room_master(text)
    for e in errors:
        report.warn(e)
    report.rows_total = len(rows) + sum(1 for e in errors if e.startswith("line "))
    cat = Catalog(session, report)
    seen: set[str] = set()
    for r in rows:
        if r["code"] in seen:
            report.warn(f"line {r['line']}: duplicate room {r['code']}; last one wins")
        seen.add(r["code"])
        room = await cat.room(r["code"])
        assert room is not None
        fields = dict(room.custom_fields or {})
        master = set(fields.get("master") or [])
        changed = False
        for attr in ("capacity", "exam_capacity"):
            if r[attr] is not None:
                master.add(attr)
                if getattr(room, attr) != r[attr]:
                    setattr(room, attr, r[attr])
                    changed = True
        if r["tags"] is not None:
            master.add("tags")  # RF-06: the master's tags are the room's tags; workbooks no longer add to them
            if list(room.tags or []) != r["tags"]:
                room.tags = r["tags"]
                changed = True
        if r["building"]:
            b = await cat.building(r["building"])
            if room.building_id != b.id:
                room.building_id = b.id
                changed = True
        if r["floor"] is not None and room.floor != r["floor"]:
            room.floor = r["floor"]
            changed = True
        if r["notes"] and room.notes != r["notes"]:
            room.notes = r["notes"]
            changed = True
        if r["owner_faculty"] is not None:
            master.add("owner_faculty")
            owner = None if r["owner_faculty"] == "-" else await cat.faculty(r["owner_faculty"])
            owner_id = owner.id if owner is not None else None
            if room.owner_faculty_id != owner_id:
                room.owner_faculty_id = owner_id
                changed = True
        if fields.pop("retired", None) is not None:  # listed again: back in service
            report.warn(f"line {r['line']}: room {r['code']} was retired; listed again, back in service")
            changed = True
        bookable = r["bookable"]
        if bookable is None:
            bookable = bool(room.capacity or room.exam_capacity)
        if room.is_bookable != bookable:
            room.is_bookable = bookable
            changed = True
        fields.pop("auto_unbookable", None)
        fields["master"] = sorted(master)
        fields["capacity_source"] = f"room-master:{report.filename}"
        if fields != (room.custom_fields or {}):
            room.custom_fields = fields
            changed = True
        if changed:
            report.updated["rooms"] += 1
        report.rows_imported += 1
    await _retire(session, report, rows, seen)
    from app.services.room_groups import groups_from_buildings

    groups = await groups_from_buildings(session, bookable_only=True)
    report.extra["room_groups"] = sorted(g.name for g in groups)
    no_cap = sorted(r["code"] for r in rows if r["code"] in cat.touched_rooms and not _has_capacity(cat, r["code"]))
    if no_cap:
        report.warn(f"{len(no_cap)} room(s) in the master still have no capacity: {', '.join(no_cap)}")
    report.extra["rooms"] = len(seen)
    await session.commit()
    return report


async def _retire(session: AsyncSession, report: ImportReport, rows: list[dict[str, Any]], listed: set[str]) -> None:
    """Retire the rooms the master no longer lists (and the rooms merged into a listed one); move or report their
    future bookings. Idempotent: an already retired room is not touched again."""
    from app.services import bookings as bsvc

    merged_into: dict[str, str] = {}
    for r in rows:
        for src in r["merged_from"]:
            if src in listed:
                report.warn(f"line {r['line']}: {src} is merged into {r['code']} but still listed; not retired")
                continue
            merged_into[src] = r["code"]
    rooms = {room.code: room for room in (await session.execute(select(Room))).scalars()}
    today = await bsvc.today(session)
    retired: list[str] = []
    moved: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    for code, room in sorted(rooms.items()):
        if code in listed:
            continue
        fields = dict(room.custom_fields or {})
        into = merged_into.get(code)
        if into is None and "master" not in fields:
            continue  # never in a master: a workbook-only room, left alone
        already = fields.get("retired")
        if not already:
            fields["retired"] = {
                "reason": "merged" if into else "not_listed",
                "into": into,
                "since": today.isoformat(),
                "source": report.filename,
            }
            fields.pop("auto_unbookable", None)
            room.custom_fields = fields
            room.is_bookable = False
            retired.append(code)
            report.updated["rooms_retired"] += 1
        target = rooms.get(into) if into else None
        for b in await _future_bookings(session, room.id, today):
            item = {
                "booking_id": b.id,
                "room": room.display_name,
                "date": b.date.isoformat(),
                "periods": f"P{b.start_period}-P{b.end_period}",
                "status": b.status,
            }
            if target is not None and await _move(session, b, room, target):
                moved.append({**item, "to": target.display_name})
            else:
                left.append(item)
    if retired:
        report.warn(f"{len(retired)} room(s) retired (no longer bookable, history kept): {', '.join(retired)}")
    if moved:
        report.warn(f"{len(moved)} future booking(s) moved into the room they were merged into")
    if left:
        report.warn(
            f"{len(left)} future booking(s) remain in retired rooms; move or cancel them: "
            + ", ".join(f"#{x['booking_id']} {x['room']} {x['date']}" for x in left[:20])
        )
    report.extra["rooms_retired"] = retired
    report.extra["merged"] = merged_into
    report.extra["bookings_moved"] = moved
    report.extra["bookings_in_retired_rooms"] = left


async def _future_bookings(session: AsyncSession, room_id: int, today: Any) -> list[Booking]:
    q = (
        select(Booking)
        .where(Booking.room_id == room_id, Booking.date >= today, Booking.status.in_((BOOKED, PENDING)))
        .order_by(Booking.date, Booking.start_period, Booking.id)
    )
    return list((await session.execute(q)).scalars())


async def _move(session: AsyncSession, b: Booking, room: Room, target: Room) -> bool:
    """Move one booking of a merged room into the room it was merged into when that slot is free there; audited
    (``booking.move``, actor system). ``False`` = not moved (the slot is taken), reported by the caller."""
    from app.services import bookings as bsvc
    from app.services.events import publish_event

    if not target.is_bookable:
        return False
    held = await bsvc.find_conflict(session, target.id, b.date, b.start_period, b.end_period)
    if held is not None:
        return False
    before = bsvc.snap(b)
    b.room_id = target.id
    await session.execute(update(BookingSlot).where(BookingSlot.booking_id == b.id).values(room_id=target.id))
    await session.flush()
    await publish_event(
        session,
        "booking.move",
        "booking",
        b.id,
        before=before,
        after=bsvc.snap(b),
        reason=f"{room.display_name} merged into {target.display_name} (room master)",
        term_id=b.term_id,
    )
    return True


def _has_capacity(cat: Catalog, code: str) -> bool:
    room = cat._rooms[code]
    return bool(room.capacity or room.exam_capacity)


__all__ = ["COLUMNS", "import_room_master", "parse_room_master", "read_room_master_text", "xlsx_to_csv_text"]
