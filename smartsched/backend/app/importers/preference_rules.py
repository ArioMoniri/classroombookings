"""Free-text wishes of the planning / exam lists -> soft ``FILE`` rules with provenance (2026-10-15).

Two sources (docs/testing/2026-10-15-academician-needs.md §2.2-2.3):

* the request / venue cell ("Derslik Talebi", "Sınavın Yapılacağı Yer"): what the request fields cannot carry
  - an avoided building ("Mümkünse B Blok olmasın"), a building set ("A veya C blokta"), an avoided room,
  a furniture / accessibility feature - becomes an *active* soft rule (``review: "auto"``): it is the
  department's formal request, and before this module it already acted (inverted) through
  ``requested_building``;
* the notes column ("Derse Özel Açıklama", 565 non-empty Bahar cells): every wish becomes a soft rule that is
  *switched off until reviewed* (``enabled=False``, ``review: "pending"``), counted in
  ``report.extra["preferences"]``.

Free text never creates a hard rule. A feature becomes a rule only when the P10 catalogue
(``room_custom_fields.solver_tag``) or the rooms' own tags know it; everything else is an *unparsed*
preference, listed by ``data_issues.preference_checks``. Each rule's ``source_ref`` names the file, sheet, row
and column and carries a stable ``key`` (request identity + column + item), so a re-import updates the rule
and keeps the planner's review decision (``enabled``, ``review``) instead of duplicating it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.models import ConstraintRow, Room, RoomCustomField, Term

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


@dataclass
class _Rule:
    key: str
    kind: str
    params: dict[str, Any]
    weight: int
    nl_text: str
    cell: TextCell


async def _known_tags(session: AsyncSession) -> set[str]:
    """Solver tags a wish may use: those of the P10 feature catalogue and those rooms already carry."""
    tags = {
        str(t).upper()
        for (t,) in (await session.execute(select(RoomCustomField.solver_tag))).all()
        if t and str(t).strip()
    }
    for (room_tags,) in (await session.execute(select(Room.tags))).all():
        tags |= {str(t).upper() for t in room_tags or []}
    return tags


async def sync_text_preferences(
    session: AsyncSession,
    term: Term,
    cat: Catalog,
    cells: Sequence[TextCell],
    *,
    origin: str,
    kind: str,
    filename: str,
    sheet: str | None,
) -> dict[str, Any]:
    """Create / update the soft rules of ``cells`` for ``term``; ``origin`` (``planning-list`` /
    ``exam-list``) scopes the re-import identity, ``kind`` (``course`` / ``exam``) the solver events.
    Returns the counts for ``report.extra["preferences"]`` plus the unparsed items."""
    tags = await _known_tags(session)
    rules: list[_Rule] = []
    unparsed: list[dict[str, Any]] = []
    notes_rows = 0
    for cell in cells:
        items = n.parse_preference_text(cell.text)
        if cell.from_notes:
            notes_rows += 1
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
                ids = await cat.room_ids(it.params["room_codes"], create=False)
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
                usable = [t for t in n.feature_tags(feature) if t in tags]
                if not usable:
                    unparsed.append(
                        _unparsed(cell, it.text, "no room feature for this wish", {"feature": feature}, it.negated)
                    )
                    continue
                side = "forbidden_tags" if it.negated else "required_tags"
                rule = _Rule(key, "room_tags", {**base, side: usable[:1], "feature": feature}, weight, it.text, cell)
            else:
                unparsed.append(_unparsed(cell, it.text, "no rule could be read from this wish"))
            if rule is not None:
                rules.append(rule)

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
                    enabled=not r.cell.from_notes,
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


__all__ = ["TextCell", "sync_text_preferences"]
