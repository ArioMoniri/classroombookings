"""V2 public read-only schedules (docs/product/booking-enhancements.md §V2): a day view per room or building that
anyone can open without signing in ("where is PHAR 240 today?").

Off by default. It counts as on only when an administrator switched it on through
``PUT /public-schedule/admin/settings``, which records a KVKK sign-off (who, user id, when, legal basis), exactly
like calendar sync (:func:`app.services.bookings_settings.kvkk_signed`). Off, an unknown room, an unknown building,
a room that is not bookable and a date outside the window all answer the same 404, so the pages cannot be used to
find out what exists.

Data minimisation (A4): the published timetable shows **course codes only** (``PHAR 240``; a cell of the imported
board that holds no course code, e.g. an instructor's name, becomes "Ders / Class"); reserved blocks show a label
only when it is one of the known generic ones (HAZIRLIK, UZEM, ETKİNLİK, SINAV), else "Ayrılmış / Reserved";
bookings are "Rezerve / Booked" without user, department, notes or ids, or hidden (``show_bookings = hidden``).
There are no personal names, no notes, no e-mail addresses and no database ids in a response. The API limits each
client address (:data:`app.core.throttle.PUBLIC_PER_ADDRESS`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import Building, User
from app.models.base import utcnow
from app.models.catalog import Room
from app.services import audit
from app.services import bookings as bsvc
from app.services.bookings_settings import get_group, kvkk_signed, set_group

#: days before / after today a public page may show
PAST_DAYS, FUTURE_DAYS = 7, 120
GENERIC_BLOCKS = {
    "HAZIRLIK": ("Hazırlık", "Preparatory school"),
    "UZEM": ("UZEM", "Distance learning"),
    "ETKİNLİK": ("Etkinlik", "Event"),
    "SINAV": ("Sınav", "Exam"),
}
LEGAL_BASIS = (
    "KVKK Art. 4(2)(ç) data minimisation: the public day view publishes no personal data (course codes, room "
    "codes and busy times only)"
)


class NotFound(Exception):
    """The one answer for off, unknown and out of range."""


async def settings(session: AsyncSession) -> dict[str, Any]:
    g = await get_group(session, "public")
    on = bool(g["schedule_enabled"]) and kvkk_signed(g["schedule_signoff"])
    show = g["show_bookings"] if g["show_bookings"] in ("busy", "hidden") else "busy"
    return {"enabled": on, "signoff": g["schedule_signoff"], "show_bookings": show}


async def update_settings(session: AsyncSession, admin: User, data: dict[str, Any]) -> dict[str, Any]:
    before = await settings(session)
    values: dict[str, Any] = {}
    if "show_bookings" in data and data["show_bookings"] is not None:
        if data["show_bookings"] not in ("busy", "hidden"):
            raise ValueError("show_bookings: busy or hidden")
        values["show_bookings"] = data["show_bookings"]
    if data.get("enabled") is not None and bool(data["enabled"]) != before["enabled"]:
        enabled = bool(data["enabled"])
        values["schedule_enabled"] = enabled
        values["schedule_signoff"] = {
            "enabled": enabled,
            "by": audit.user_label(admin),
            "by_user_id": admin.id,
            "at": utcnow().isoformat(timespec="seconds") + "Z",
            "features": ["public_schedule"],
            "legal_basis": LEGAL_BASIS,
        }
    if values:
        await set_group(session, "public", values)
        after = await settings(session)
        await audit.record(
            session,
            "public_schedule.settings",
            "setting",
            "public.schedule",
            before={"enabled": before["enabled"], "show_bookings": before["show_bookings"]},
            after={"enabled": after["enabled"], "show_bookings": after["show_bookings"]},
            actor=admin,
        )
    return await settings(session)


async def _gate(session: AsyncSession, d: date) -> dict[str, Any]:
    cfg = await settings(session)
    if not cfg["enabled"]:
        raise NotFound
    today = await bsvc.today(session)
    if not (today - timedelta(days=PAST_DAYS) <= d <= today + timedelta(days=FUTURE_DAYS)):
        raise NotFound
    return cfg


def _time(s: int, e: int) -> dict[str, str]:
    return {"start": f"{n.PERIODS[s - 1].start:%H:%M}", "end": f"{n.PERIODS[e - 1].end:%H:%M}"}


def _class_label(label: str) -> dict[str, str]:
    codes = [n.display_course_code(c) for c in n.extract_course_codes(label or "")]
    if codes:
        text = " / ".join(dict.fromkeys(codes))
        return {"tr": text, "en": text}
    return {"tr": "Ders", "en": "Class"}


def _block_label(label: str) -> dict[str, str]:
    key = n.tr_upper((n.clean_text(label) or "").strip())
    for k, (tr, en) in GENERIC_BLOCKS.items():
        if key.startswith(k):
            return {"tr": tr, "en": en}
    return {"tr": "Ayrılmış", "en": "Reserved"}


async def _public_rooms(session: AsyncSession) -> list[Room]:
    q = select(Room).where(Room.is_bookable.is_(True)).order_by(Room.code)
    return list((await session.execute(q)).scalars())


async def _items(session: AsyncSession, rooms: list[Room], d: date, show: str) -> dict[int, list[dict[str, Any]]]:
    ids = {r.id for r in rooms}
    tocc = await bsvc.timetable_occupancy(session, ids, d, d)
    bocc = await bsvc.booking_occupancy(session, ids, d, d) if show == "busy" else {}
    out: dict[int, list[dict[str, Any]]] = {r.id: [] for r in rooms}
    for r in rooms:
        rows: list[dict[str, Any]] = []
        for h in tocc.get((r.id, d), []):
            kind = "class" if h.kind == "timetable" else "reserved"
            label = _class_label(h.label) if kind == "class" else _block_label(h.label)
            rows.append(
                {"kind": kind, "start_period": h.start, "end_period": h.end, **_time(h.start, h.end), "label": label}
            )
        for h in bocc.get((r.id, d), []):
            if h.pending:
                continue
            rows.append(
                {
                    "kind": "booked",
                    "start_period": h.start,
                    "end_period": h.end,
                    **_time(h.start, h.end),
                    "label": {"tr": "Rezerve", "en": "Booked"},
                }
            )
        rows.sort(key=lambda x: (x["start_period"], x["end_period"], x["kind"], x["label"]["tr"]))
        uniq: list[dict[str, Any]] = []
        for x in rows:  # a class split over rooms or weeks may be listed twice
            if not uniq or uniq[-1] != x:
                uniq.append(x)
        out[r.id] = uniq
    return out


def _room_out(r: Room, building: str | None) -> dict[str, Any]:
    return {"code": r.code, "name": r.display_name, "building": building, "capacity": r.capacity or None}


async def _buildings(session: AsyncSession) -> dict[int, Building]:
    return {b.id: b for b in (await session.execute(select(Building))).scalars()}


async def index(session: AsyncSession) -> dict[str, Any]:
    """Buildings and their rooms (what a public page can open), only when switched on."""
    cfg = await settings(session)
    if not cfg["enabled"]:
        raise NotFound
    blds = await _buildings(session)
    groups: dict[str, dict[str, Any]] = {}
    for r in await _public_rooms(session):
        b = blds.get(r.building_id or 0)
        code = b.code if b else r.code[:1]
        g = groups.setdefault(code, {"code": code, "name": b.name if b else code, "rooms": []})
        g["rooms"].append(_room_out(r, code))
    return {"buildings": [groups[k] for k in sorted(groups)], "show_bookings": cfg["show_bookings"]}


def _canon_room(code: str) -> str | None:
    codes = n.parse_room_codes(n.clean_text(code) or "")
    return codes[0] if len(codes) == 1 else None


async def room_day(session: AsyncSession, code: str, d: date) -> dict[str, Any]:
    cfg = await _gate(session, d)
    canon = _canon_room(code)
    room = next((r for r in await _public_rooms(session) if r.code == canon), None) if canon else None
    if room is None:
        raise NotFound
    blds = await _buildings(session)
    b = blds.get(room.building_id or 0)
    items = (await _items(session, [room], d, cfg["show_bookings"]))[room.id]
    return {"date": d.isoformat(), "room": _room_out(room, b.code if b else room.code[:1]), "items": items}


async def building_day(session: AsyncSession, code: str, d: date) -> dict[str, Any]:
    cfg = await _gate(session, d)
    key = n.tr_upper((n.clean_text(code) or "").strip())
    blds = await _buildings(session)
    rooms = [
        r
        for r in await _public_rooms(session)
        if (blds[r.building_id].code if r.building_id in blds else r.code[:1]) == key
    ]
    if not key or not rooms:
        raise NotFound
    items = await _items(session, rooms, d, cfg["show_bookings"])
    b = next((x for x in blds.values() if x.code == key), None)
    return {
        "date": d.isoformat(),
        "building": {"code": key, "name": b.name if b else key},
        "rooms": [{**_room_out(r, key), "items": items[r.id]} for r in rooms],
    }
