"""P10 typed room features (docs/product/booking-enhancements.md §4.1).

CRBS custom fields (``room_custom_fields``: TEXT, CHECKBOX, SELECT; display only) become a feature catalogue
with types BOOLEAN (CHECKBOX is its alias), NUMBER, SELECT (enum), MULTISELECT and TEXT, flags ``filterable`` /
``public``, an icon, a unit, a category and a ``solver_tag``.

The solver contract is unchanged: it keeps reading ``rooms.tags`` (PC, TIP, LAB, AMPHI ...). A feature with a
``solver_tag`` *is* that tag:

* a BOOLEAN feature with a solver tag reads its value from ``rooms.tags`` (so the importers' PC / TIP tags show as
  feature values without any copy) and writes it back there (add or remove only that tag);
* other typed features with a solver tag add the tag when their value is "true" (NUMBER > 0, an option chosen,
  any text) and remove it when no feature with that tag is true any more;
* manual tags (tags no feature maps) are never touched.

Every write is audited (``room.features``, ``room_feature.*``) through :mod:`app.services.audit`."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import ExamRequest, MeetingRequest, RoomCustomField, RoomCustomFieldOption, RoomCustomFieldValue, User
from app.models.catalog import Room
from app.services import audit

TYPES = ("BOOLEAN", "CHECKBOX", "NUMBER", "SELECT", "MULTISELECT", "TEXT")
BOOL_TYPES = frozenset({"BOOLEAN", "CHECKBOX"})
CATEGORIES = ("av", "seating", "accessibility", "lab", "other")

#: Turkish / English labels of the tags the importers and the solver use (adopt-tags names features after them)
TAG_LABELS: dict[str, tuple[str, str]] = {
    "PC": ("Bilgisayar laboratuvarı", "lab"),
    "TIP": ("Tıp Fakültesi dersliği", "other"),
    "LAB": ("Laboratuvar", "lab"),
    "AMPHI": ("Amfi", "seating"),
    "AMFI": ("Amfi", "seating"),
    "STEP_FREE": ("Engelli erişimi", "accessibility"),
}
#: words people type for a tag (Turkish-insensitive), used by the finder's text matching
TAG_SYNONYMS: dict[str, tuple[str, ...]] = {
    "PC": ("pc", "bilgisayar", "bilg. lab", "bilgisayar lab", "bilgisayar laboratuvarı", "computer", "computer lab"),
    "TIP": ("tıp", "tip", "medicine", "tıp fakültesi"),
    "LAB": ("lab", "laboratuvar", "laboratory"),
    "AMPHI": ("amfi", "amfi tiyatro", "amphi", "amphitheatre", "amphitheater"),
}

#: the optional starter catalogue (spec §2.1 P10): created only when an administrator asks, never seeded
TEMPLATE: tuple[dict[str, Any], ...] = (
    {"name": "Projeksiyon", "type": "BOOLEAN", "category": "av", "icon": "projector"},
    {"name": "Akıllı tahta", "type": "BOOLEAN", "category": "av", "icon": "presentation"},
    {"name": "PC sayısı", "type": "NUMBER", "category": "lab", "unit": "adet", "icon": "monitor"},
    {"name": "Mikrofon", "type": "BOOLEAN", "category": "av", "icon": "mic"},
    {
        "name": "Engelli erişimi",
        "type": "BOOLEAN",
        "category": "accessibility",
        "icon": "accessibility",
        "solver_tag": "STEP_FREE",
    },
    {"name": "Kayıt sistemi", "type": "BOOLEAN", "category": "av", "icon": "video"},
)


class FeatureError(Exception):
    def __init__(self, status: int, code: str, message: str, **data: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.data}


def norm_type(t: str) -> str:
    t = n.tr_upper(n.clean_text(t) or "")
    return "BOOLEAN" if t == "CHECKBOX" else t


def norm_tag(tag: str | None) -> str | None:
    text = n.clean_text(tag)
    return n.tr_upper(text).replace(" ", "_")[:16] if text else None


# --------------------------------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------------------------------


async def catalogue(session: AsyncSession) -> list[RoomCustomField]:
    q = select(RoomCustomField).order_by(RoomCustomField.pos, RoomCustomField.name, RoomCustomField.id)
    return list((await session.execute(q)).scalars())


def field_out(f: RoomCustomField, counts: dict[str, int] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": f.id,
        "name": f.name,
        "type": f.type,
        "kind": norm_type(f.type),
        "options": [{"id": o.id, "value": o.value} for o in f.options],
        "filterable": bool(f.filterable) if f.filterable is not None else True,
        "public": bool(f.public) if f.public is not None else True,
        "icon": f.icon,
        "unit": f.unit,
        "solver_tag": f.solver_tag,
        "category": f.category,
        "pos": f.pos or 0,
    }
    if counts is not None:
        out["counts"] = counts
    return out


def find_option(f: RoomCustomField, value: Any) -> RoomCustomFieldOption | None:
    """An option by id or by its text, Turkish-case-insensitively (İ/ı, NBSP)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        hit = next((o for o in f.options if o.id == int(value)), None)
        if hit is not None:
            return hit
    text = n.clean_text(value)
    if not text:
        return None
    key = n.tr_casefold(text)
    return next((o for o in f.options if n.tr_casefold(o.value) == key), None)


def find_field(fields: Iterable[RoomCustomField], ref: Any) -> RoomCustomField | None:
    """A field by id or name (Turkish-case-insensitive, exact name first, then a unique prefix/containment)."""
    fields = list(fields)
    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
        hit = next((f for f in fields if f.id == int(ref)), None)
        if hit is not None:
            return hit
    text = n.clean_text(ref)
    if not text:
        return None
    key = n.tr_casefold(text)
    exact = [f for f in fields if n.tr_casefold(f.name) == key]
    if exact:
        return exact[0]
    near = [f for f in fields if key in n.tr_casefold(f.name)]
    return near[0] if len(near) == 1 else None


# --------------------------------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------------------------------


@dataclass
class Stored:
    value: str | None = None
    value_num: float | None = None
    value_json: list[Any] | None = None


def coerce(f: RoomCustomField, raw: Any) -> Stored:
    """A user value -> storage, with Turkish input rules (``evet``/``var``/``x``, ``4,5``, NBSP, option text).
    Raises ``ValueError`` with a message for the per-cell report."""
    kind = norm_type(f.type)
    if raw is None or (isinstance(raw, str) and n.clean_text(raw) is None and kind != "BOOLEAN"):
        return Stored()
    if kind == "BOOLEAN":
        if isinstance(raw, str) and n.clean_text(raw) is None:
            return Stored("0")
        b = raw if isinstance(raw, bool) else n.parse_bool_loose(raw)
        if b is None:
            raise ValueError(f"{f.name}: {raw!r} is not yes/no (evet/hayır)")
        return Stored("1" if b else "0")
    if kind == "NUMBER":
        if isinstance(raw, bool):
            raise ValueError(f"{f.name}: a number is expected")
        text = n.clean_text(raw) if not isinstance(raw, int | float) else None
        if text is not None and text.lstrip().startswith("-"):
            raise ValueError(f"{f.name}: cannot be negative")
        num = float(raw) if isinstance(raw, int | float) else n.parse_float_loose(text)
        if num is None:
            raise ValueError(f"{f.name}: {raw!r} is not a number")
        if num < 0:
            raise ValueError(f"{f.name}: cannot be negative")
        shown = str(int(num)) if float(num).is_integer() else str(num)
        return Stored(shown, float(num))
    if kind == "SELECT":
        opt = find_option(f, raw)
        if opt is None:
            raise ValueError(f"{f.name}: {raw!r} is not one of {', '.join(o.value for o in f.options)}")
        return Stored(str(opt.id))
    if kind == "MULTISELECT":
        items = raw if isinstance(raw, list | tuple) else [p for p in str(raw).replace(",", ";").split(";")]
        ids: list[int] = []
        for item in items:
            if isinstance(item, str) and n.clean_text(item) is None:
                continue
            opt = find_option(f, item)
            if opt is None:
                raise ValueError(f"{f.name}: {item!r} is not one of {', '.join(o.value for o in f.options)}")
            if opt.id not in ids:
                ids.append(opt.id)
        return Stored(None, None, sorted(ids)) if ids else Stored()
    text = n.clean_text(raw)
    if text and len(text) > 255:
        raise ValueError(f"{f.name}: at most 255 characters")
    return Stored(text)


def decode(f: RoomCustomField, row: RoomCustomFieldValue | None, room: Room | None = None) -> Any:
    """Typed value of ``f`` for a room. BOOLEAN features with a solver tag read ``rooms.tags``."""
    kind = norm_type(f.type)
    if kind == "BOOLEAN" and f.solver_tag and room is not None:
        return f.solver_tag in (room.tags or [])
    if row is None:
        return False if kind == "BOOLEAN" else None
    if kind == "BOOLEAN":
        return row.value == "1"
    if kind == "NUMBER":
        return row.value_num if row.value_num is not None else n.parse_float_loose(row.value)
    if kind == "SELECT":
        return int(row.value) if row.value and row.value.isdigit() else None
    if kind == "MULTISELECT":
        return list(row.value_json or [])
    return row.value


def display(f: RoomCustomField, value: Any) -> Any:
    """Human value: option texts instead of ids."""
    kind = norm_type(f.type)
    if kind == "SELECT":
        return next((o.value for o in f.options if o.id == value), None)
    if kind == "MULTISELECT":
        return [o.value for o in f.options if o.id in (value or [])]
    return value


def truthy(f: RoomCustomField, value: Any) -> bool:
    kind = norm_type(f.type)
    if kind == "NUMBER":
        return bool(value) and float(value) > 0
    if kind == "MULTISELECT":
        return bool(value)
    return bool(value) and value is not False


async def value_rows(session: AsyncSession, room_ids: Iterable[int] | None = None) -> dict[int, dict[int, Any]]:
    """{room_id: {field_id: row}}"""
    q = select(RoomCustomFieldValue)
    if room_ids is not None:
        ids = list(room_ids)
        if not ids:
            return {}
        q = q.where(RoomCustomFieldValue.room_id.in_(ids))
    out: dict[int, dict[int, Any]] = {}
    for v in (await session.execute(q)).scalars():
        out.setdefault(v.room_id, {})[v.field_id] = v
    return out


async def room_values(
    session: AsyncSession,
    rooms: list[Room],
    fields: list[RoomCustomField] | None = None,
) -> dict[int, dict[int, Any]]:
    """Typed feature values: {room_id: {field_id: value}} (one query for all rooms)."""
    fields = fields if fields is not None else await catalogue(session)
    rows = await value_rows(session, [r.id for r in rooms])
    return {r.id: {f.id: decode(f, rows.get(r.id, {}).get(f.id), r) for f in fields} for r in rooms}


async def legacy_values(session: AsyncSession, room: Room) -> dict[str, Any]:
    """``GET /room-admin/rooms/{id}/fields``: ``{field_id: value}`` (CHECKBOX/BOOLEAN bool, SELECT option id,
    NUMBER float, MULTISELECT option ids, TEXT text); only fields with a stored value or a solver tag."""
    fields = await catalogue(session)
    rows = (await value_rows(session, [room.id])).get(room.id, {})
    out: dict[str, Any] = {}
    for f in fields:
        if f.id in rows or (norm_type(f.type) == "BOOLEAN" and f.solver_tag):
            out[str(f.id)] = decode(f, rows.get(f.id), room)
    return out


async def mirror(session: AsyncSession, room: Room, fields: list[RoomCustomField] | None = None) -> None:
    """``rooms.custom_fields`` (by field name, for the AI layer and the room UI) and ``rooms.tags`` (solver tags)."""
    fields = fields if fields is not None else await catalogue(session)
    rows = (await value_rows(session, [room.id])).get(room.id, {})
    names = {f.name for f in fields}
    keep = {k: v for k, v in (room.custom_fields or {}).items() if k not in names}
    tag_on: dict[str, bool] = {}
    for f in fields:
        value = decode(f, rows.get(f.id), room)
        if f.solver_tag and norm_type(f.type) != "BOOLEAN":
            tag_on[f.solver_tag] = tag_on.get(f.solver_tag, False) or truthy(f, value)
        if value in (None, "", []) or (rows.get(f.id) is None and not f.solver_tag):
            continue
        keep[f.name] = display(f, value)
    room.custom_fields = keep
    if tag_on:
        bool_tags = {
            f.solver_tag
            for f in fields
            if f.solver_tag and norm_type(f.type) == "BOOLEAN" and f.solver_tag in (room.tags or [])
        }
        tags = list(room.tags or [])
        for tag, on in tag_on.items():
            if on and tag not in tags:
                tags.append(tag)
            elif not on and tag in tags and tag not in bool_tags:
                tags.remove(tag)
        if tags != list(room.tags or []):
            room.tags = tags


def _set_tag(room: Room, tag: str, on: bool) -> None:
    tags = list(room.tags or [])
    if on and tag not in tags:
        tags.append(tag)
    elif not on and tag in tags:
        tags.remove(tag)
    room.tags = tags


async def set_values(
    session: AsyncSession, room: Room, values: dict[Any, Any], actor: User | None = None
) -> dict[int, Any]:
    """Write ``{field id or name: value}`` for one room (all or nothing), mirror tags, audit ``room.features``."""
    fields = await catalogue(session)
    by_id = {f.id: f for f in fields}
    rows = (await value_rows(session, [room.id])).get(room.id, {})
    before_vals = {f.id: decode(f, rows.get(f.id), room) for f in fields}
    errors: list[str] = []
    plan: list[tuple[RoomCustomField, Stored]] = []
    for key, raw in values.items():
        f = find_field(fields, key)
        if f is None:
            raise FeatureError(404, "field_not_found", f"feature {key!r} not found")
        try:
            plan.append((by_id[f.id], coerce(f, raw)))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise FeatureError(422, "invalid_values", "; ".join(errors), errors=errors)
    before_tags = list(room.tags or [])
    for f, st in plan:
        row = rows.get(f.id)
        if row is None:
            row = RoomCustomFieldValue(room_id=room.id, field_id=f.id)
            session.add(row)
            rows[f.id] = row
        row.value, row.value_num, row.value_json = st.value, st.value_num, st.value_json
        if norm_type(f.type) == "BOOLEAN" and f.solver_tag:
            _set_tag(room, f.solver_tag, st.value == "1")
    await session.flush()
    await mirror(session, room, fields)
    after_vals = {f.id: decode(f, rows.get(f.id), room) for f in fields}
    changed = [fid for fid in after_vals if after_vals[fid] != before_vals.get(fid)]
    if changed or before_tags != list(room.tags or []):
        await audit.record(
            session,
            "room.features",
            "room",
            room.id,
            before={**{by_id[i].name: before_vals[i] for i in changed}, "tags": before_tags},
            after={**{by_id[i].name: after_vals[i] for i in changed}, "tags": list(room.tags or [])},
            actor=actor,
        )
    return after_vals


# --------------------------------------------------------------------------------------------------
# Catalogue edits with their impact on the solver tags
# --------------------------------------------------------------------------------------------------


async def requests_needing(session: AsyncSession, tag: str) -> int:
    """Meeting and exam requests that ask for ``tag`` (e.g. PC: "Bilg. Lab. Zorunlu")."""
    count = 0
    for model in (MeetingRequest, ExamRequest):
        for tags in (await session.execute(select(model.requested_tags))).scalars():
            if tag in (tags or []):
                count += 1
    return count


async def impact(session: AsyncSession, tag: str, exclude_field_id: int | None = None) -> dict[str, Any]:
    """What removing ``tag`` from the rooms a feature drives would do: rooms losing it, requests needing it."""
    others = [
        f
        for f in await catalogue(session)
        if f.solver_tag == tag and f.id != exclude_field_id and norm_type(f.type) != "BOOLEAN"
    ]
    rooms = [r for r in (await session.execute(select(Room))).scalars() if tag in (r.tags or [])]
    vals = await room_values(session, rooms, others) if others else {}
    losing = [r for r in rooms if not any(truthy(f, vals.get(r.id, {}).get(f.id)) for f in others)]
    need = await requests_needing(session, tag)
    return {
        "tag": tag,
        "rooms": [r.display_name for r in sorted(losing, key=lambda r: r.code)],
        "room_count": len(losing),
        "requests_needing": need,
        "message": f"removes {tag} from {len(losing)} room(s); {need} request(s) need {tag}",
        "message_tr": f"{len(losing)} odadan {tag} kaldırılır; {need} talep {tag} istiyor",
    }


@dataclass
class FieldSpec:
    name: str
    type: str
    options: list[str] = field(default_factory=list)
    filterable: bool = True
    public: bool = True
    icon: str | None = None
    unit: str | None = None
    solver_tag: str | None = None
    category: str | None = None


def _validate(spec: FieldSpec) -> FieldSpec:
    spec.name = n.clean_text(spec.name) or ""
    if not spec.name:
        raise FeatureError(422, "name", "a feature needs a name")
    spec.type = n.tr_upper(n.clean_text(spec.type) or "")
    if spec.type not in TYPES:
        raise FeatureError(422, "type", f"type must be one of {', '.join(TYPES)}")
    spec.options = [o[:64] for o in (n.clean_text(x) for x in spec.options) if o]
    if norm_type(spec.type) in ("SELECT", "MULTISELECT") and not spec.options:
        raise FeatureError(422, "options", f"a {spec.type} feature needs options")
    folded = [n.tr_casefold(o) for o in spec.options]
    if len(set(folded)) != len(folded):
        raise FeatureError(422, "options", "options must differ (Turkish case-insensitive)")
    if spec.unit and norm_type(spec.type) != "NUMBER":
        spec.unit = None
    if spec.category and spec.category not in CATEGORIES:
        raise FeatureError(422, "category", f"category must be one of {', '.join(CATEGORIES)}")
    spec.solver_tag = norm_tag(spec.solver_tag)
    return spec


async def _name_taken(session: AsyncSession, name: str, exclude: int | None = None) -> bool:
    key = n.tr_casefold(name)
    return any(n.tr_casefold(f.name) == key and f.id != exclude for f in await catalogue(session))


async def create_field(session: AsyncSession, spec: FieldSpec, actor: User | None = None) -> RoomCustomField:
    spec = _validate(spec)
    if await _name_taken(session, spec.name):
        raise FeatureError(409, "name_taken", f"a feature named {spec.name!r} exists")
    pos = (await session.execute(select(func.max(RoomCustomField.pos)))).scalar() or 0
    f = RoomCustomField(
        name=spec.name[:64],
        type=spec.type,
        pos=pos + 1,
        filterable=spec.filterable,
        public=spec.public,
        icon=spec.icon,
        unit=spec.unit,
        solver_tag=spec.solver_tag,
        category=spec.category,
    )
    f.options = [RoomCustomFieldOption(value=v, pos=i) for i, v in enumerate(spec.options)]
    session.add(f)
    await session.flush()
    await audit.record(session, "room_feature.create", "room_feature", f.id, after=field_out(f), actor=actor)
    return f


async def update_field(
    session: AsyncSession, f: RoomCustomField, spec: FieldSpec, actor: User | None = None, *, confirm: bool = False
) -> RoomCustomField:
    """Options are matched by text (Turkish-insensitive), so values survive renames of other options. Turning a
    solver tag off (or changing it) that rooms rely on needs ``confirm`` (409 with the impact otherwise)."""
    spec = _validate(spec)
    if await _name_taken(session, spec.name, exclude=f.id):
        raise FeatureError(409, "name_taken", f"a feature named {spec.name!r} exists")
    before = field_out(f)
    old_tag, old_kind = f.solver_tag, norm_type(f.type)
    new_kind = norm_type(spec.type)
    if old_kind == "BOOLEAN" and new_kind != "BOOLEAN" and old_tag:
        raise FeatureError(422, "type", "turn the solver tag off before changing the type of a yes/no feature")
    tag_rooms: list[Room] = []
    if old_tag and old_tag != spec.solver_tag:
        imp = await impact(session, old_tag, exclude_field_id=f.id)
        if imp["room_count"] and not confirm:
            raise FeatureError(409, "solver_tag_impact", imp["message"], impact=imp)
        tag_rooms = [r for r in (await session.execute(select(Room))).scalars() if old_tag in (r.tags or [])]
        # materialise the tag-derived values before the link changes
        if old_kind == "BOOLEAN":
            rows = await value_rows(session, [r.id for r in tag_rooms])
            for r in tag_rooms:
                row = rows.get(r.id, {}).get(f.id)
                if row is None:
                    session.add(RoomCustomFieldValue(room_id=r.id, field_id=f.id, value="1"))
                else:
                    row.value = "1"
    old_by_value = {n.tr_casefold(o.value): o for o in f.options}
    new_opts = []
    if new_kind in ("SELECT", "MULTISELECT"):
        for i, v in enumerate(spec.options):
            o = old_by_value.pop(n.tr_casefold(v), None) or RoomCustomFieldOption(value=v)
            o.value, o.pos = v, i
            new_opts.append(o)
    removed = {o.id for o in old_by_value.values()}
    f.name, f.type = spec.name[:64], spec.type
    f.filterable, f.public, f.icon, f.unit, f.category = (
        spec.filterable,
        spec.public,
        spec.icon,
        spec.unit,
        spec.category,
    )
    f.solver_tag = spec.solver_tag
    f.options = new_opts
    await session.flush()
    for fv in (
        await session.execute(select(RoomCustomFieldValue).where(RoomCustomFieldValue.field_id == f.id))
    ).scalars():
        if new_kind == "SELECT" and fv.value and fv.value.isdigit() and int(fv.value) in removed:
            fv.value = None
        elif new_kind == "MULTISELECT" and fv.value_json:
            fv.value_json = [i for i in fv.value_json if i not in removed] or None
        if new_kind != old_kind:
            fv.value, fv.value_num, fv.value_json = None, None, None
    await session.flush()
    for r in tag_rooms:
        if old_tag and old_tag in (r.tags or []):
            imp_other = [g for g in await catalogue(session) if g.solver_tag == old_tag and g.id != f.id]
            if not imp_other:
                _set_tag(r, old_tag, False)
    affected = {
        rid
        for rid in (
            await session.execute(select(RoomCustomFieldValue.room_id).where(RoomCustomFieldValue.field_id == f.id))
        ).scalars()
    } | {r.id for r in tag_rooms}
    fields = await catalogue(session)
    for rid in affected:
        room = await session.get(Room, rid)
        if room is not None:
            if before["name"] != f.name:
                room.custom_fields = {k: v for k, v in (room.custom_fields or {}).items() if k != before["name"]}
            if f.solver_tag and new_kind == "BOOLEAN":
                rows = (await value_rows(session, [rid])).get(rid, {})
                row = rows.get(f.id)
                if row is not None and row.value == "1":
                    _set_tag(room, f.solver_tag, True)
            await mirror(session, room, fields)
    await audit.record(
        session, "room_feature.update", "room_feature", f.id, before=before, after=field_out(f), actor=actor
    )
    return f


async def delete_field(
    session: AsyncSession, f: RoomCustomField, actor: User | None = None, *, confirm: bool = False
) -> dict[str, Any]:
    """Removes the feature; its solver tag leaves the rooms only when no other feature sets the same tag, and only
    with ``confirm`` when rooms carry it (409 with the impact otherwise)."""
    before = field_out(f)
    imp: dict[str, Any] | None = None
    tag = f.solver_tag
    other_same_tag = [g for g in await catalogue(session) if g.solver_tag == tag and g.id != f.id] if tag else []
    if tag and not other_same_tag:
        imp = await impact(session, tag, exclude_field_id=f.id)
        if imp["room_count"] and not confirm:
            raise FeatureError(409, "solver_tag_impact", imp["message"], impact=imp)
    room_ids = set(
        (
            await session.execute(select(RoomCustomFieldValue.room_id).where(RoomCustomFieldValue.field_id == f.id))
        ).scalars()
    )
    if tag and not other_same_tag:
        for r in (await session.execute(select(Room))).scalars():
            if tag in (r.tags or []):
                _set_tag(r, tag, False)
                room_ids.add(r.id)
    name = f.name
    await session.delete(f)
    await session.flush()
    for rid in room_ids:
        r = await session.get(Room, rid)
        if r is not None and name in (r.custom_fields or {}):
            r.custom_fields = {k: v for k, v in r.custom_fields.items() if k != name}
    await audit.record(session, "room_feature.delete", "room_feature", before["id"], before=before, actor=actor)
    return {"deleted": before["id"], "impact": imp}


async def adopt_tags(session: AsyncSession, actor: User | None = None) -> list[RoomCustomField]:
    """Migrate the free-text room tags into typed features: one BOOLEAN feature (with that ``solver_tag``) per tag
    present on rooms that no feature maps yet. Values are not copied: the feature reads ``rooms.tags``."""
    mapped = {f.solver_tag for f in await catalogue(session) if f.solver_tag}
    present: list[str] = []
    for tags in (await session.execute(select(Room.tags))).scalars():
        for t in tags or []:
            tag = norm_tag(str(t))
            if tag and tag not in mapped and tag not in present:
                present.append(tag)
    created = []
    for tag in sorted(present):
        label, category = TAG_LABELS.get(tag, (tag, "other"))
        name = label if not await _name_taken(session, label) else f"{label} ({tag})"
        created.append(
            await create_field(session, FieldSpec(name=name, type="BOOLEAN", solver_tag=tag, category=category), actor)
        )
    return created


async def apply_template(session: AsyncSession, actor: User | None = None) -> list[RoomCustomField]:
    """The suggested catalogue, skipping names that exist (only on an administrator's request)."""
    created = []
    for item in TEMPLATE:
        if await _name_taken(session, item["name"]):
            continue
        created.append(await create_field(session, FieldSpec(**item), actor))
    return created


# --------------------------------------------------------------------------------------------------
# Facets and filters
# --------------------------------------------------------------------------------------------------


async def facets(session: AsyncSession, rooms: list[Room], *, include_private: bool) -> list[dict[str, Any]]:
    """Filterable features with value counts over ``rooms`` (the rooms the user may view)."""
    fields = [f for f in await catalogue(session) if (f.filterable is not False) and (include_private or f.public)]
    vals = await room_values(session, rooms, fields)
    out = []
    for f in fields:
        counts: dict[str, int] = {}
        kind = norm_type(f.type)
        for r in rooms:
            v = vals[r.id][f.id]
            if kind == "BOOLEAN":
                key = ["false", "true"][bool(v)]
                counts[key] = counts.get(key, 0) + 1
            elif kind == "MULTISELECT":
                for oid in v or []:
                    counts[str(oid)] = counts.get(str(oid), 0) + 1
            elif v not in (None, ""):
                key = str(int(v)) if kind == "NUMBER" and float(v).is_integer() else str(v)
                counts[key] = counts.get(key, 0) + 1
        out.append(field_out(f, counts))
    return out


@dataclass
class Criterion:
    field: RoomCustomField
    op: str = "eq"
    value: Any = True

    def label(self) -> str:
        if norm_type(self.field.type) == "BOOLEAN":
            return self.field.name
        val = display(self.field, self.value) if norm_type(self.field.type) in ("SELECT",) else self.value
        sym = {"gte": "≥", "lte": "≤", "eq": "=", "has": "∋", "contains": "~"}.get(self.op, self.op)
        return f"{self.field.name} {sym} {val}"


def criterion(fields: list[RoomCustomField], ref: Any, op: str | None, value: Any) -> Criterion:
    f = find_field(fields, ref)
    if f is None:
        raise FeatureError(422, "feature_not_found", f"feature {ref!r} not found")
    kind = norm_type(f.type)
    if kind == "BOOLEAN":
        b = True if value is None else (value if isinstance(value, bool) else n.parse_bool_loose(value))
        if b is None:
            raise FeatureError(422, "feature_value", f"{f.name}: {value!r} is not yes/no")
        return Criterion(f, "eq", b)
    if kind == "NUMBER":
        num = value if isinstance(value, int | float) and not isinstance(value, bool) else n.parse_float_loose(value)
        if num is None:
            raise FeatureError(422, "feature_value", f"{f.name}: {value!r} is not a number")
        return Criterion(f, op if op in ("gte", "lte", "eq") else "gte", float(num))
    if kind in ("SELECT", "MULTISELECT"):
        wanted = value if isinstance(value, list) else [value]
        ids = []
        for w in wanted:
            opt = find_option(f, w)
            if opt is None:
                raise FeatureError(422, "feature_value", f"{f.name}: {w!r} is not an option")
            ids.append(opt.id)
        return Criterion(f, "in" if kind == "SELECT" else "has", ids)
    text = n.clean_text(value)
    if not text:
        raise FeatureError(422, "feature_value", f"{f.name}: a text is needed")
    return Criterion(f, "contains", n.tr_casefold(text))


def matches(c: Criterion, value: Any) -> bool:
    kind = norm_type(c.field.type)
    if kind == "BOOLEAN":
        return bool(value) == bool(c.value)
    if value is None:
        return False
    if kind == "NUMBER":
        v = float(value)
        return {"gte": v >= c.value, "lte": v <= c.value, "eq": v == c.value}[c.op]
    if kind == "SELECT":
        return value in c.value
    if kind == "MULTISELECT":
        return set(c.value) <= set(value or [])
    return c.value in n.tr_casefold(str(value))


# --------------------------------------------------------------------------------------------------
# Bulk CSV (room code + one column per feature)
# --------------------------------------------------------------------------------------------------

ROOM_HEADERS = {"code", "room", "oda", "derslik", "oda kodu", "derslik kodu", "kod"}


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254"):  # cp1254 = Turkish Windows (Excel "CSV")
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _rows(text: str) -> list[list[str]]:
    first = text.splitlines()[0] if text else ""
    delim = max((";", ",", "\t"), key=first.count)
    return list(csv.reader(io.StringIO(text), delimiter=delim))


async def bulk_values(
    session: AsyncSession, data: bytes, actor: User | None = None, *, dry_run: bool = True, skip_errors: bool = False
) -> dict[str, Any]:
    """Per-cell report; applies when ``dry_run`` is false and there are no errors (or ``skip_errors``).
    Empty cells change nothing; ``-`` clears a value (a yes/no feature becomes "no")."""
    rows = _rows(_decode(data))
    if not rows:
        raise FeatureError(422, "empty", "the file is empty")
    header = [n.clean_text(h) or "" for h in rows[0]]
    if not header or n.tr_casefold(header[0]) not in ROOM_HEADERS:
        raise FeatureError(422, "header", "the first column must be the room code (kod / oda / derslik / code)")
    fields = await catalogue(session)
    columns: list[RoomCustomField | None] = []
    unknown = []
    for h in header[1:]:
        f = find_field(fields, h)
        columns.append(f)
        if f is None and h:
            unknown.append(h)
    rooms = {r.code: r for r in (await session.execute(select(Room))).scalars()}
    report: list[dict[str, Any]] = []
    plan: list[tuple[Room, dict[int, Any]]] = []
    errors = 0
    for line, row in enumerate(rows[1:], start=2):
        if not any((c or "").strip() for c in row):
            continue
        raw_code = n.clean_text(row[0]) if row else None
        codes = n.parse_room_codes(raw_code) if raw_code else []
        room = rooms.get(codes[0]) if codes else rooms.get(n.tr_upper(raw_code or "").replace(" ", ""))
        if room is None:
            report.append({"line": line, "room": raw_code, "status": "error", "message": "room not found"})
            errors += 1
            continue
        values: dict[int, Any] = {}
        for col, f in enumerate(columns, start=1):
            if f is None or col >= len(row):
                continue
            cell = row[col]
            if not (cell or "").replace("\xa0", " ").strip():
                continue
            raw: Any = None if n.clean_text(cell) is None else cell
            cell_rep: dict[str, Any] = {"line": line, "room": room.display_name, "field": f.name, "value": cell}
            try:
                coerce(f, raw if raw is not None else ("" if norm_type(f.type) == "BOOLEAN" else None))
                values[f.id] = raw if raw is not None else ("" if norm_type(f.type) == "BOOLEAN" else None)
                cell_rep["status"] = "ok"
            except ValueError as exc:
                cell_rep.update(status="error", message=str(exc))
                errors += 1
            report.append(cell_rep)
        if values:
            plan.append((room, values))
    applied = 0
    if not dry_run:
        if errors and not skip_errors:
            raise FeatureError(422, "bulk_errors", f"{errors} cell(s) have errors; nothing was applied", report=report)
        for room, values in plan:  # cells with errors never entered ``values``
            await set_values(session, room, values, actor)
            applied += len(values)
    return {
        "dry_run": dry_run,
        "rooms": len(plan),
        "cells": sum(len(v) for _, v in plan),
        "errors": errors,
        "unknown_columns": unknown,
        "applied": applied,
        "report": report,
    }
