"""Free-text wishes of the planning / exam lists -> soft ``FILE`` rules with provenance (2026-10-15).

Two sources (docs/testing/2026-10-15-academician-needs.md §2.2-2.3):

* the request / venue cell ("Derslik Talebi", "Sınavın Yapılacağı Yer"): what the request fields cannot carry
  - an avoided building ("Mümkünse B Blok olmasın"), a building set ("A veya C blokta"), an avoided room,
  a furniture / accessibility feature - becomes an *active* soft rule (``review: "auto"``): it is the
  department's formal request, and before this module it already acted (inverted) through
  ``requested_building``;
* the notes column ("Derse Özel Açıklama", 565 non-empty Bahar cells): every wish becomes a soft rule that acts
  while it waits for review (``review: "pending"``; the planner accepts it or switches it off), counted in
  ``report.extra["preferences"]``; a lock or placement against a wish is a data issue
  (``data_issues.preference_checks``, persona A-06 / A-07).

Free text never creates a hard rule. A feature becomes a rule only when the P10 catalogue
(``room_custom_fields.solver_tag``) or the rooms' own tags know it; everything else is an *unparsed*
preference, listed by ``data_issues.preference_checks``. Each rule's ``source_ref`` names the file, sheet, row
and column and carries a stable ``key`` (request identity + column + item), so a re-import updates the rule
and keeps the planner's review decision (``enabled``, ``review``) instead of duplicating it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.models import ConstraintRow, Room, RoomCustomField, RoomCustomFieldOption, Term

WEIGHT_NORMAL = 5
WEIGHT_STRONG = 8  # "mutlaka", "zorunlu": still soft (free text)


@dataclass
class TextCell:
    """One free-text cell of one request."""

    request_id: int
    request_key: str  # the request's stable source key (re-import identity)
    row: int
    column: str  # the header text of the column, as the planner sees it
    text: str
    from_notes: bool  # notes column (pending review) vs request column (active)
    #: request column only: the venue parser already read something (rooms, count, seats, tags), so wish
    #: wording alone is no "unparsed" preference; ``covered_tags`` are in ``requested_tags`` already
    structured: bool = False
    covered_tags: tuple[str, ...] = ()


@dataclass
class _Rule:
    key: str
    kind: str
    params: dict[str, Any]
    weight: int
    nl_text: str
    cell: TextCell


@dataclass
class _Catalogue:
    tags: set[str]  # solver tags of the P10 catalogue + tags rooms already carry
    named: list[tuple[str, str]]  # (folded feature name + option values, solver tag) of tagged features

    def tags_for(self, feature: str, software: str | None) -> list[str]:
        """Solver tags satisfying a wish: the lexicon's tags the rooms / catalogue know, else a catalogue feature
        whose name or options name it ("JASP yüklü", a "Yazılım" feature with option "JAMOVI", "Engelli erişimi")."""
        if software:
            needle = n.fold(software)
            return [t for text, t in self.named if needle in text][:1]
        known = [t for t in n.feature_tags(feature) if t in self.tags]
        if known:
            return known[:1]
        phrases = next((ph for key, ph, _t in n.FEATURE_LEXICON if key == feature), ())
        return [t for text, t in self.named if any(ph in text for ph in phrases)][:1]


async def _catalogue(session: AsyncSession) -> _Catalogue:
    tags: set[str] = set()
    named: list[tuple[str, str]] = []
    options: dict[int, list[str]] = {}
    for fid, value in (
        await session.execute(select(RoomCustomFieldOption.field_id, RoomCustomFieldOption.value))
    ).all():
        options.setdefault(int(fid), []).append(str(value or ""))
    for fid, name, tag in (
        await session.execute(select(RoomCustomField.id, RoomCustomField.name, RoomCustomField.solver_tag))
    ).all():
        if tag and str(tag).strip():
            tags.add(str(tag).upper())
            named.append((n.fold(" ".join([str(name or ""), *options.get(int(fid), [])])), str(tag).upper()))
    for (room_tags,) in (await session.execute(select(Room.tags))).all():
        tags |= {str(t).upper() for t in room_tags or []}
    return _Catalogue(tags, named)


RoomLookup = Callable[[list[str]], Awaitable[list[int]]]


async def read_cells(
    session: AsyncSession, cells: Sequence[TextCell], *, origin: str, kind: str, room_ids: RoomLookup
) -> tuple[list[_Rule], list[dict[str, Any]]]:
    """Classify every wish of ``cells``: the soft rules to write, and the unparsed wishes (no structure, a
    feature no room has, rooms not in the room list). Writes nothing (``data_issues`` re-reads with it)."""
    catalogue = await _catalogue(session)
    rules: list[_Rule] = []
    unparsed: list[dict[str, Any]] = []
    for cell in cells:
        items = n.parse_preference_text(cell.text)
        for i, it in enumerate(items):
            key = f"{origin}|{cell.request_key}|{cell.column}|{i}"
            weight = WEIGHT_STRONG if it.strong else WEIGHT_NORMAL
            base: dict[str, Any] = {"event_ids": [cell.request_id], "kinds": [kind]}
            rule: _Rule | None = None
            if it.kind == "avoid_building":
                rule = _Rule(key, "building_preference", {**base, **it.params}, weight, it.text, cell)
            elif it.kind == "building_preference":
                if cell.from_notes or len(it.params["buildings"]) > 1:  # one building: requested_building has it
                    rule = _Rule(key, "building_preference", {**base, **it.params}, weight, it.text, cell)
            elif it.kind in ("room_preference", "room_alternatives", "avoid_room"):
                if it.kind != "avoid_room" and not cell.from_notes:
                    continue  # the request cell's rooms are requested_room_ids already
                ids = await room_ids(list(it.params["room_codes"]))
                if not ids:
                    unparsed.append(_unparsed(cell, it.text, "rooms not in the room list", it.params))
                    continue
                params = {**base, "room_ids": ids}
                if it.kind == "room_alternatives":
                    params["room_groups"] = it.params["room_groups"]
                rule = _Rule(
                    key, "room_forbid" if it.kind == "avoid_room" else "room_preference", params, weight, it.text, cell
                )
            elif it.kind == "feature":
                feature = str(it.params["feature"])
                software = it.params.get("software")
                if not it.negated and set(n.feature_tags(feature)) & set(cell.covered_tags):
                    continue  # "amfi", "bilgisayar lab" in the request cell: requested_tags has it
                usable = catalogue.tags_for(feature, software)
                if not usable:
                    extra = {"feature": feature, **({"software": software} if software else {})}
                    unparsed.append(_unparsed(cell, it.text, "no room feature for this wish", extra, it.negated))
                    continue
                side = "forbidden_tags" if it.negated else "required_tags"
                params = {**base, side: usable, "feature": feature, **({"software": software} if software else {})}
                rule = _Rule(key, "room_tags", params, weight, it.text, cell)
            elif not cell.structured:
                unparsed.append(_unparsed(cell, it.text, "no rule could be read from this wish"))
            if rule is not None:
                rules.append(rule)
    return rules, unparsed


async def sync_text_preferences(
    session: AsyncSession,
    term: Term,
    cat: Catalog,
    cells: Sequence[TextCell],
    *,
    origin: str,
    kind: str,
    filename: str | None,
    sheet: str | None,
) -> dict[str, Any]:
    """Create / update the soft rules of ``cells`` for ``term``; ``origin`` (``planning-list`` /
    ``exam-list``) scopes the re-import identity, ``kind`` (``course`` / ``exam``) the solver events.
    Returns the counts for ``report.extra["preferences"]`` plus the unparsed items."""

    async def lookup(codes: list[str]) -> list[int]:
        return await cat.room_ids(codes, create=False)

    rules, unparsed = await read_cells(session, cells, origin=origin, kind=kind, room_ids=lookup)
    notes_rows = sum(1 for c in cells if c.from_notes)
    prefix = f"{origin}|"
    existing = {
        str((c.source_ref or {}).get("key")): c
        for c in (
            await session.execute(
                select(ConstraintRow).where(ConstraintRow.term_id == term.id, ConstraintRow.source == "FILE")
            )
        ).scalars()
        if str((c.source_ref or {}).get("key") or "").startswith(prefix)
    }
    seen: set[str] = set()
    created = updated = pending = 0
    for r in rules:
        seen.add(r.key)
        ref = {
            "file": filename,
            "sheet": sheet,
            "row": r.cell.row,
            "column": r.cell.column,
            "excerpt": r.cell.text[:300],
            "review": "pending" if r.cell.from_notes else "auto",
            "key": r.key,
        }
        row = existing.get(r.key)
        if row is None:
            session.add(
                ConstraintRow(
                    term_id=term.id,
                    kind=r.kind,
                    params=r.params,
                    hardness="soft",
                    weight=r.weight,
                    source="FILE",
                    source_ref=ref,
                    nl_text=r.nl_text,
                    enabled=True,  # soft wishes act while they wait for review (persona A-06 / A-07)
                )
            )
            created += 1
            pending += r.cell.from_notes
            continue
        # a re-import: the file's reading is refreshed, the planner's decision (enabled / review) is kept
        decided = (row.source_ref or {}).get("review")
        row.kind, row.params, row.hardness, row.nl_text = r.kind, r.params, "soft", r.nl_text
        row.source_ref = {**ref, "review": decided or ref["review"]}
        updated += 1
        pending += decided == "pending"
    removed = 0
    for key, row in existing.items():
        # a wish that left the file: drop it unless the planner accepted it (then it is theirs)
        if key not in seen and (row.source_ref or {}).get("review") in ("pending", "auto"):
            await session.delete(row)
            removed += 1
    return {
        "notes_rows": notes_rows,
        "rules": len(rules),
        "created": created,
        "updated": updated,
        "removed": removed,
        "pending_review": pending,
        "active": sum(1 for r in rules if not r.cell.from_notes),
        "unparsed": len(unparsed),
        "unparsed_items": unparsed[:200],
    }


def _unparsed(
    cell: TextCell, text: str, reason: str, params: dict[str, Any] | None = None, negated: bool = False
) -> dict[str, Any]:
    return {
        "row": cell.row,
        "column": cell.column,
        "request_id": cell.request_id,
        "text": text,
        "reason": reason,
        "negated": negated,
        **(params or {}),
    }


__all__ = ["TextCell", "read_cells", "request_cells", "sync_text_preferences"]


NOTES_COLUMN = "Derse Özel Açıklama"
REQUEST_COLUMN = "Derslik Talebi"
EXAM_VENUE_COLUMN = "Sınavın Yapılacağı Yer"


async def request_cells(session: AsyncSession, term_id: int, exam: bool) -> list[TextCell]:
    """The free-text cells of a term's requests as stored (for re-reading): meeting notes (the joined note
    parts the planner wrote; the importer's own "no room needed" note is skipped) and request / venue text."""
    from app.models import ExamRequest, MeetingRequest, Section

    cells: list[TextCell] = []
    if exam:
        for ex in (
            await session.execute(
                select(ExamRequest).where(ExamRequest.term_id == term_id, ExamRequest.archived.is_(False))
            )
        ).scalars():
            if ex.requested_venue_text:
                v = n.parse_venue_request(ex.requested_venue_text)
                structured = bool(v.room_codes or v.min_capacity or v.room_count or v.tags or v.invigilators)
                cells.append(
                    TextCell(
                        ex.id,
                        ex.source_key or str(ex.id),
                        ex.source_row_index or 0,
                        EXAM_VENUE_COLUMN,
                        ex.requested_venue_text,
                        False,
                        structured,
                        tuple(v.tags),
                    )
                )
        return cells
    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == term_id, MeetingRequest.archived.is_(False))
    )
    for mr in (await session.execute(q)).scalars():
        key, row = mr.source_key or str(mr.id), mr.source_row_index or 0
        for part in (mr.notes or "").split(" | "):
            part = part.strip()
            if part and not part.startswith(
                ("Derslik dışı mekân (", "Alternatif derslikler /", "Sınıf yılları birleşik")
            ):
                cells.append(TextCell(mr.id, key, row, NOTES_COLUMN, part, True))
        if mr.requested_room_text:
            v = n.parse_venue_request(mr.requested_room_text)
            structured = bool(v.room_codes or v.min_capacity or v.room_count or v.tags)
            cells.append(
                TextCell(mr.id, key, row, REQUEST_COLUMN, mr.requested_room_text, False, structured, tuple(v.tags))
            )
    return cells
