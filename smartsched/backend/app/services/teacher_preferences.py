"""P19-T2 "Tercih ekle": an academician's own preference for their classes (academician needs Q11 / Q12; F-05 S03).

Q12: the department form is the official request; the academician's own wish is a **lower-ranked soft preference**
that waits for coordinator review. Concretely:

* **who**: any signed-in user whose account is linked to an instructor record (``Instructor.user_id``, P19-L1), for
  meeting requests of sections that instructor teaches (``section_instructors``). Nobody else's classes (Q11);
* **what**: one of :data:`KINDS` - a room (``room_preference``), a building (``building_preference``) or a time
  window (``day_window``, only for a class whose time the department did not fix). Never hard, never untargeted,
  never a structural kind (capacity, tags, pins, bans, fixed times): every row names its classes (``event_ids``) and
  passes the hard-rule integrity guard (``constraint_guard``, D1) and the constraint catalogue;
* **lower rank**: the stored rule lists the department's own ask first and the academician's after it (a room
  list ``[department rooms..., wished rooms...]``, a building set ``{department building, wished buildings}``),
  with weight :data:`WEIGHT` (1, below the department's notes 5, learned 5 and a coordinator's wish 10). With the
  department's implicit preference on top, a room the department asked for always costs less than the wished one,
  and the wish decides only among the rooms the department did not name (``tests/test_p19_t2_teacher_preferences``
  proves it with the solver);
* **review**: stored as a ``constraints`` row with ``source = "TEACHER"``, switched off and
  ``source_ref.review = "pending"`` until a coordinator (``planning.edit``) accepts it - it then acts on the next
  solve or re-solve like any soft rule of the term - or rejects it with a written reason, which reaches the
  academician through :mod:`app.services.notify_dispatch` (``preference.rejected``; acceptance sends
  ``preference.accepted``). Coordinators see the rows in the moderation read models (Tercihler = ``/constraints``,
  the people / matchings / history rows and ``GET /terms/{id}/moderation/teacher-preferences``).

Audited: ``preference.submit``, ``preference.accept`` (a solving change: it is in the changes-since-publish list),
``preference.reject``, ``preference.withdraw``. Errors are ``{code, message, message_tr}``.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers import normalize as n
from app.models import (
    ConstraintRow,
    Instructor,
    MeetingRequest,
    Room,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.services import constraint_guard
from app.services.events import publish_event

SOURCE = "TEACHER"
#: the kinds an academician may wish for (soft, targeted; no structural kind)
KINDS = ("room_preference", "building_preference", "day_window")
#: the wizard's / form's short names
KIND_ALIASES = {"room": "room_preference", "building": "building_preference", "time": "day_window"}
#: the soft weight multiplier of an academician's wish: below the department's notes (5), learned (5) and a
#: coordinator's wish (10); the department's own ask is also listed first in the rule (see the module docstring)
WEIGHT = 1
STATUSES = ("pending", "accepted", "rejected")
MAX_REQUESTS = 50
MAX_ROOMS = 5
MAX_PENDING = 50
NOTE_MAX = 500
REASON_MIN = 3
PERIODS = 18
KIND_TEXT: dict[str, tuple[str, str]] = {
    "room_preference": ("Oda tercihi", "Room preference"),
    "building_preference": ("Bina tercihi", "Building preference"),
    "day_window": ("Saat tercihi", "Time preference"),
}
_BUILDING_RX = re.compile(r"^([A-ZÇĞİÖŞÜ])(?:\s*-?\s*(?:BLOK|BLOĞU|BLOKTA|BLOK'TA|BLOKU))?$")


class PreferenceError(Exception):
    def __init__(self, status: int, code: str, message: str, message_tr: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr, self.extra = status, code, message, message_tr, extra

    @property
    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "message_tr": self.message_tr, **self.extra}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def _ints(values: Iterable[Any] | None) -> list[int]:
    out: list[int] = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _ref(row: ConstraintRow) -> dict[str, Any]:
    return dict(row.source_ref) if isinstance(row.source_ref, dict) else {}


def status_of(row: ConstraintRow) -> str:
    st = str(_ref(row).get("review") or "pending")
    return st if st in STATUSES else "pending"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _label(mr: MeetingRequest) -> str:
    sec = mr.section
    code = sec.course.display_code if sec.course else f"#{sec.course_id}"
    return f"{code}{f' §{sec.label}' if sec.label else ''}"


def _building_of(room: Room) -> str:
    return room.code[:1] if room.code else ""


# --------------------------------------------------------------------------------------------- who and which classes


async def linked_instructors(session: AsyncSession, user: User) -> list[Instructor]:
    return list(
        (
            await session.execute(select(Instructor).where(Instructor.user_id == user.id).order_by(Instructor.id))
        ).scalars()
    )


async def _require_link(session: AsyncSession, user: User) -> list[Instructor]:
    linked = await linked_instructors(session, user)
    if not linked:
        raise PreferenceError(
            403,
            "not_linked",
            "your account is not linked to an instructor record; ask the planning office to link it",
            "Hesabınız bir öğretim elemanı kaydına bağlı değil; planlama biriminden bağlamasını isteyin",
        )
    return linked


def _meetings_query() -> Any:
    return select(MeetingRequest).options(
        selectinload(MeetingRequest.section).selectinload(Section.course),
        selectinload(MeetingRequest.section)
        .selectinload(Section.instructors)
        .selectinload(SectionInstructor.instructor),
    )


async def _own_requests(
    session: AsyncSession, linked: list[Instructor], request_ids: list[int], section_id: int | None
) -> list[MeetingRequest]:
    ids = list(dict.fromkeys(request_ids))
    q = _meetings_query().where(MeetingRequest.archived.is_(False))
    if section_id is not None:
        q = q.where(MeetingRequest.section_id == section_id)
        if ids:
            q = q.where(MeetingRequest.id.in_(ids))
    elif ids:
        q = q.where(MeetingRequest.id.in_(ids))
    else:
        raise PreferenceError(
            422,
            "no_classes",
            "name the classes of the preference (request_ids or section_id)",
            "Tercihin hangi derslere ait olduğunu seçin",
        )
    rows = list((await session.execute(q.order_by(MeetingRequest.id))).scalars())
    if not rows or (ids and len({m.id for m in rows}) != len(ids)):
        raise PreferenceError(404, "not_found", "class not found", "Ders bulunamadı")
    if len(rows) > MAX_REQUESTS:
        raise PreferenceError(
            422,
            "too_many",
            f"one preference covers at most {MAX_REQUESTS} classes",
            f"Bir tercih en çok {MAX_REQUESTS} dersi kapsar",
        )
    mine = {i.id for i in linked}
    others = [m for m in rows if not mine & {si.instructor_id for si in m.section.instructors}]
    if others:
        raise PreferenceError(
            403,
            "not_yours",
            "you can add preferences only for the classes you teach",
            "Yalnızca verdiğiniz derslere tercih ekleyebilirsiniz",
            request_ids=[m.id for m in others][:20],
        )
    terms = {m.section.term_id for m in rows}
    if len(terms) != 1:
        raise PreferenceError(
            422, "several_terms", "one preference covers one term", "Bir tercih tek bir dönemi kapsar"
        )
    return rows


# --------------------------------------------------------------------------------------------- the wish


def _kind(value: Any) -> str:
    k = str(value or "").strip().lower()
    k = KIND_ALIASES.get(k, k)
    if k not in KINDS:
        raise PreferenceError(
            422,
            "kind",
            f"an academician's preference is a room, a building or a time window ({', '.join(KINDS)})",
            "Akademisyen tercihi bir oda, bir bina ya da bir saat aralığı olabilir",
        )
    return k


def _soft_only(body: Mapping[str, Any]) -> None:
    hardness = body.get("hardness")
    if hardness is not None and str(hardness).strip().lower() != "soft":
        raise PreferenceError(
            422,
            "hard",
            "an academician's preference is always soft; the department form is the official request (Q12)",
            "Akademisyen tercihi her zaman yumuşaktır; resmi talep bölüm formudur",
        )
    if body.get("weight") is not None and int(body["weight"]) != WEIGHT:
        raise PreferenceError(
            422,
            "weight",
            f"an academician's preference always ranks below the department's request (weight {WEIGHT})",
            f"Akademisyen tercihi her zaman bölüm talebinin ardından gelir (ağırlık {WEIGHT})",
        )


async def _wished_rooms(session: AsyncSession, body: Mapping[str, Any]) -> list[Room]:
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    by_code = {r.code: r for r in rooms.values()}
    out: list[Room] = []
    unknown: list[str] = []
    for rid in _ints(body.get("room_ids")):
        if rid in rooms:
            out.append(rooms[rid])
        else:
            unknown.append(f"#{rid}")
    for text in body.get("rooms") or []:
        codes = n.parse_room_codes(text)  # "C 404", "c\xa0404", "C404 / A105" (NBSP and case folded)
        if not codes:
            unknown.append(str(text))
        for code in codes:
            if code in by_code:
                out.append(by_code[code])
            else:
                unknown.append(n.display_room_code(code))
    if unknown:
        raise PreferenceError(
            422, "unknown_room", f"unknown room {', '.join(unknown)}", f"Bilinmeyen oda: {', '.join(unknown)}"
        )
    out = list({r.id: r for r in out}.values())
    if not out:
        raise PreferenceError(422, "no_room", "name the room you prefer", "Tercih ettiğiniz odayı seçin")
    if len(out) > MAX_ROOMS:
        raise PreferenceError(422, "too_many_rooms", f"name at most {MAX_ROOMS} rooms", f"En çok {MAX_ROOMS} oda seçin")
    closed = [r.display_name for r in out if not r.is_bookable]
    if closed:
        raise PreferenceError(
            422,
            "room_closed",
            f"{', '.join(closed)} is not used for classes",
            f"{', '.join(closed)} derslerde kullanılmıyor",
        )
    return out


async def _wished_buildings(session: AsyncSession, body: Mapping[str, Any]) -> list[str]:
    known = {_building_of(r) for r in (await session.execute(select(Room))).scalars() if r.code}
    out: list[str] = []
    bad: list[str] = []
    for raw in body.get("buildings") or []:
        text = n.clean_text(raw)  # NBSP, zero-width and repeated spaces
        folded = (text or "").replace("i", "İ").replace("ı", "I").upper().strip()
        m = _BUILDING_RX.match(folded)
        if m and m.group(1) in known:
            out.append(m.group(1))
        else:
            bad.append(str(raw))
    if bad:
        raise PreferenceError(
            422, "unknown_building", f"unknown building {', '.join(bad)}", f"Bilinmeyen bina: {', '.join(bad)}"
        )
    out = list(dict.fromkeys(out))
    if not out:
        raise PreferenceError(422, "no_building", "name the building you prefer", "Tercih ettiğiniz binayı seçin")
    return out


def _period(value: Any, kind: str) -> int | None:
    """A period number (1..18) or a clock time as the lists write it (``10.10``, ``10:10``, ``15.50``)."""
    if value is None or value == "":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    t = n.parse_time(value)
    if t is None:
        raise PreferenceError(422, "time", f"unreadable time {value!r}", f"Okunamayan saat: {value}")
    match = n.time_to_period(t, kind)
    if match.period is None:
        raise PreferenceError(422, "time", f"{value} is outside the day's periods", f"{value} ders saatleri dışında")
    return int(match.period)


def _window(body: Mapping[str, Any]) -> dict[str, Any]:
    earliest = _period(body.get("earliest") if body.get("earliest") is not None else body.get("not_before"), "start")
    latest = _period(body.get("latest") if body.get("latest") is not None else body.get("not_after"), "end")
    lo, hi = earliest or 1, latest or PERIODS
    if not (1 <= lo <= hi <= PERIODS) or (earliest is None and latest is None):
        raise PreferenceError(
            422,
            "window",
            f"give the earliest and / or latest period (1..{PERIODS}, earliest <= latest)",
            f"En erken ve / veya en geç ders saatini girin (1..{PERIODS}, erken <= geç)",
        )
    out: dict[str, Any] = {"earliest": lo, "latest": hi}
    days = []
    for d in body.get("days") or []:
        parsed = n.parse_day(d).days if not isinstance(d, int) else [d]  # "Salı", "sali", 2
        days += [int(x) for x in parsed]
    if any(not 1 <= d <= 7 for d in days) or (body.get("days") and not days):
        raise PreferenceError(422, "days", "days are 1 (Monday) .. 7 (Sunday)", "Günler 1 (Pazartesi) .. 7 (Pazar)")
    if days:
        out["days"] = sorted(set(days))
    return out


def _compose(kind: str, mrs: list[MeetingRequest], wish: dict[str, Any]) -> list[dict[str, Any]]:
    """One rule per distinct department ask: the department's rooms / building first, the wish after (Q12)."""
    groups: dict[tuple[Any, ...], list[MeetingRequest]] = defaultdict(list)
    for mr in mrs:
        if kind == "room_preference":
            key: tuple[Any, ...] = tuple(_ints(mr.requested_room_ids))
        elif kind == "building_preference":
            key = (str(mr.requested_building).upper(),) if mr.requested_building else ()
        else:
            key = ()
        groups[key].append(mr)
    out: list[dict[str, Any]] = []
    for dept, members in groups.items():
        ids = [m.id for m in members]
        if kind == "room_preference":
            extra = [r for r in wish["room_ids"] if r not in dept]
            if not extra:
                continue
            out.append({"params": {"event_ids": ids, "room_ids": [*dept, *extra]}, "department": list(dept)})
        elif kind == "building_preference":
            extra = [b for b in wish["buildings"] if b not in dept]
            if not extra:
                continue
            out.append({"params": {"event_ids": ids, "buildings": [*dept, *extra]}, "department": list(dept)})
        else:
            out.append({"params": {"event_ids": ids, **wish}, "department": []})
    return out


def _check_rule(kind: str, params: dict[str, Any]) -> None:
    from app.ai.catalog import validate_params

    issues = validate_params(kind, dict(params), "soft")
    issues += constraint_guard.guard_rule(kind, params, "soft", source=SOURCE, may_waive=False, reason=None)
    if not constraint_guard.is_targeted_params(params) or kind not in KINDS:
        issues.append("an academician's preference must name its classes")
    if issues:
        raise PreferenceError(
            422,
            "invalid_rule",
            "the preference cannot be stored: " + "; ".join(issues[:5]),
            "Tercih kaydedilemedi: kural denetimi geçmedi",
            issues=issues[:10],
        )


def _texts(kind: str, labels: list[str], wish: Mapping[str, Any], rooms: Mapping[int, Room]) -> dict[str, str]:
    what = ", ".join(labels[:3]) + (" …" if len(labels) > 3 else "")
    if kind == "room_preference":
        names = ", ".join(rooms[r].display_name for r in wish.get("room_ids") or [] if r in rooms)
        return _t(f"{what}: oda tercihi {names}", f"{what}: room preference {names}")
    if kind == "building_preference":
        names = ", ".join(wish.get("buildings") or [])
        return _t(f"{what}: {names} blok tercihi", f"{what}: building {names} preferred")
    span = f"P{wish.get('earliest', 1)}–P{wish.get('latest', PERIODS)}"
    return _t(f"{what}: ders saatleri {span} arasında", f"{what}: classes within {span}")


# --------------------------------------------------------------------------------------------- submit / list / withdraw


EFFECTIVE = _t(
    "Koordinatör onaylarsa bir sonraki çözümde bölüm talebinden sonra gelen bir tercih olarak uygulanır",
    "If the coordinator accepts it, it applies at the next solve, ranked below the department's request",
)


async def submit(
    session: AsyncSession, user: User, body: Mapping[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    """``POST /moderation/me/preferences``: store the wish as switched-off soft rules waiting for review.

    ``dry_run``: every check of a real submit (link, own classes, kind, rooms / buildings, fixed times, the
    department's ask, the pending cap, the rule guard) and the same ``items`` / ``effective`` answer, but nothing is
    stored or audited (``dry_run: true``, ``status: "preview"``, ``submission`` and item ids null)."""
    linked = await _require_link(session, user)
    _soft_only(body)
    kind = _kind(body.get("kind"))
    mrs = await _own_requests(session, linked, _ints(body.get("request_ids")), body.get("section_id"))
    term_id = mrs[0].section.term_id
    note = n.clean_text(body.get("note"))
    if note and len(note) > NOTE_MAX:
        raise PreferenceError(
            422, "note", f"the note is at most {NOTE_MAX} characters", f"Not en çok {NOTE_MAX} karakter olabilir"
        )
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    wish: dict[str, Any]
    if kind == "room_preference":
        wish = {"room_ids": [r.id for r in await _wished_rooms(session, body)]}
    elif kind == "building_preference":
        wish = {"buildings": await _wished_buildings(session, body)}
    else:
        fixed = [m for m in mrs if m.start_period is not None]
        if fixed:
            raise PreferenceError(
                422,
                "fixed_by_department",
                "the department form fixes the day and time of "
                + ", ".join(_label(m) for m in fixed[:3])
                + "; a time preference cannot change it (ask the coordinator)",
                "Bölüm formu " + ", ".join(_label(m) for m in fixed[:3]) + " için gün ve saati sabitliyor; saat "
                "tercihi bunu değiştiremez (koordinatöre danışın)",
                request_ids=[m.id for m in fixed][:20],
            )
        wish = _window(body)
    rules = _compose(kind, mrs, wish)
    if not rules:
        raise PreferenceError(
            422,
            "already_requested",
            "the department form already asks for this for these classes",
            "Bölüm formu bu dersler için bunu zaten istiyor",
        )
    pending = sum(
        1
        for r in (
            await session.execute(
                select(ConstraintRow).where(
                    ConstraintRow.term_id == term_id,
                    ConstraintRow.source == SOURCE,
                    ConstraintRow.created_by == user.id,
                )
            )
        ).scalars()
        if status_of(r) == "pending"
    )
    if pending + len(rules) > MAX_PENDING:
        raise PreferenceError(
            409,
            "too_many_pending",
            f"you have {pending} preferences waiting for review (at most {MAX_PENDING})",
            f"İncelenmeyi bekleyen {pending} tercihiniz var (en çok {MAX_PENDING})",
        )
    submission = uuid.uuid4().hex[:12]
    labels = {m.id: _label(m) for m in mrs}
    mine = {i.id for i in linked}
    instructor_id = next(
        (si.instructor_id for m in mrs for si in m.section.instructors if si.instructor_id in mine), linked[0].id
    )
    created: list[ConstraintRow] = []
    for rule in rules:
        params = rule["params"]
        _check_rule(kind, params)
        rids = list(params["event_ids"])
        texts = _texts(kind, [labels[i] for i in rids], wish, rooms)
        row = ConstraintRow(
            term_id=term_id,
            run_id=None,
            kind=kind,
            params=params,
            hardness="soft",
            weight=WEIGHT,
            source=SOURCE,
            nl_text=texts["tr"],
            enabled=False,  # waits for a coordinator (Q12); accepted -> on for the next solve
            created_by=user.id,
            source_ref={
                "review": "pending",
                "submission": submission,
                "user_id": user.id,
                "instructor_id": instructor_id,
                "request_ids": rids,
                "section_ids": sorted({m.section_id for m in mrs if m.id in set(rids)}),
                "wish": wish,
                "department": rule["department"],
                "rank": "below_department",
                "note": note,
                "text": texts,
                "submitted_at": _now(),
            },
        )
        created.append(row)
    if dry_run:
        return {
            "dry_run": True,
            "submission": None,
            "status": "preview",
            "items": await items_out(session, created),
            "effective": EFFECTIVE,
        }
    session.add_all(created)
    await session.flush()
    await publish_event(
        session,
        "preference.submit",
        "constraint",
        created[0].id,
        after={
            "constraint_ids": [r.id for r in created],
            "submission": submission,
            "kind": kind,
            "wish": wish,
            "request_ids": [m.id for m in mrs],
            "instructor_id": instructor_id,
        },
        actor=user,
        term_id=term_id,
    )
    await session.commit()
    return {
        "dry_run": False,
        "submission": submission,
        "status": "pending",
        "items": await items_out(session, created),
        "effective": EFFECTIVE,
    }


async def wishable_rooms(session: AsyncSession, user: User, *, may_view_all: bool = False) -> dict[str, Any]:
    """``GET /moderation/me/rooms``: the rooms the "Tercih ekle" room picker offers - every bookable room (the ones
    :func:`_wished_rooms` accepts), with what a picker shows (code, name, capacity, building, tags). Never notes,
    owners, photos or custom fields. For an account linked to an instructor (403 ``not_linked`` otherwise) or a
    user with ``planning.view``."""
    if not may_view_all:
        await _require_link(session, user)
    q = select(Room).options(selectinload(Room.building)).where(Room.is_bookable.is_(True))
    items = [
        {
            "id": r.id,
            "code": r.code,
            "name": r.display_name,
            "capacity": int(r.capacity or 0),
            "building": _building_of(r),
            "building_name": r.building.name if r.building else None,
            "tags": [str(t) for t in (r.tags or [])],
            "bookable": True,
        }
        for r in (await session.execute(q)).scalars()
    ]
    items.sort(key=lambda x: (x["building"], x["code"]))
    return {"items": items, "count": len(items)}


async def items_out(session: AsyncSession, rows: list[ConstraintRow]) -> list[dict[str, Any]]:
    if not rows:
        return []
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    rids = sorted({i for r in rows for i in _ints(_ref(r).get("request_ids") or (r.params or {}).get("event_ids"))})
    labels: dict[int, str] = {}
    if rids:
        for mr in (await session.execute(_meetings_query().where(MeetingRequest.id.in_(rids[:5000])))).scalars():
            labels[mr.id] = _label(mr)
    iids = sorted({int(_ref(r).get("instructor_id") or 0) for r in rows} - {0})
    names = (
        {
            i.id: i.full_name
            for i in (await session.execute(select(Instructor).where(Instructor.id.in_(iids)))).scalars()
        }
        if iids
        else {}
    )
    return [item_out(r, labels, rooms, names) for r in rows]


def item_out(
    row: ConstraintRow, labels: Mapping[int, str], rooms: Mapping[int, Room], names: Mapping[int, str]
) -> dict[str, Any]:
    ref = _ref(row)
    params = dict(row.params or {})
    wish = dict(ref.get("wish") or {})
    rids = _ints(ref.get("request_ids") or params.get("event_ids"))
    iid = int(ref.get("instructor_id") or 0) or None
    dept = ref.get("department") or []
    kind_tr, kind_en = KIND_TEXT.get(row.kind, (row.kind, row.kind))
    if row.kind == "room_preference":
        wish["rooms"] = [rooms[r].display_name for r in _ints(wish.get("room_ids")) if r in rooms]
        dept_out: dict[str, Any] = {
            "room_ids": _ints(dept),
            "rooms": [rooms[r].display_name for r in _ints(dept) if r in rooms],
        }
    elif row.kind == "building_preference":
        dept_out = {"buildings": list(dept)}
    else:
        dept_out = {}
    return {
        "id": row.id,
        "constraint_id": row.id,
        "term_id": row.term_id,
        "status": status_of(row),
        "enabled": bool(row.enabled),
        "kind": row.kind,
        "kind_label": _t(kind_tr, kind_en),
        "submission": ref.get("submission"),
        "request_ids": rids,
        "labels": [labels[i] for i in rids if i in labels],
        "instructor": {"id": iid, "name": names.get(iid or 0)} if iid else None,
        "user_id": ref.get("user_id"),
        "wish": wish,
        "department": dept_out,
        "rank": "below_department",
        "text": ref.get("text") or _t(row.nl_text or "", row.nl_text or ""),
        "note": ref.get("note"),
        "hardness": row.hardness,
        "weight": row.weight,
        "params": params,
        "submitted_at": ref.get("submitted_at"),
        "decided_at": ref.get("decided_at"),
        "decided_by": ref.get("decided_by"),
        "reason": ref.get("reason"),
        "reason_code": ref.get("reason_code"),
    }


async def _rows(session: AsyncSession, *where: Any) -> list[ConstraintRow]:
    q = select(ConstraintRow).where(ConstraintRow.source == SOURCE, *where).order_by(ConstraintRow.id.desc())
    return list((await session.execute(q)).scalars())


async def mine(session: AsyncSession, user: User, term_id: int | None = None) -> dict[str, Any]:
    """``GET /moderation/me/preferences``: the caller's own wishes with their status and the coordinator's reason."""
    linked = await linked_instructors(session, user)
    where = [ConstraintRow.created_by == user.id]
    if term_id is not None:
        where.append(ConstraintRow.term_id == term_id)
    rows = await _rows(session, *where)
    items = await items_out(session, rows)
    return {
        "linked": bool(linked),
        "instructor_id": linked[0].id if linked else None,
        "term_id": term_id,
        "counts": {s: sum(1 for i in items if i["status"] == s) for s in STATUSES},
        "total": len(items),
        "items": items,
    }


async def withdraw(session: AsyncSession, user: User, cid: int) -> None:
    """``DELETE /moderation/me/preferences/{id}``: the academician takes back a wish that is still pending (every
    row of the same submission goes)."""
    row = await session.get(ConstraintRow, cid)
    if row is None or row.source != SOURCE or row.created_by != user.id:
        raise PreferenceError(404, "not_found", "preference not found", "Tercih bulunamadı")
    if status_of(row) != "pending":
        raise PreferenceError(
            409,
            "decided",
            f"the preference was already {status_of(row)}",
            "Tercih için karar verilmiş; geri çekilemez",
        )
    group = await _submission(session, row)
    before = [{"id": r.id, "kind": r.kind, "params": r.params} for r in group]
    term_id = row.term_id
    for r in group:
        await session.delete(r)
    await session.flush()
    await publish_event(
        session,
        "preference.withdraw",
        "constraint",
        cid,
        before={"rules": before, "submission": _ref(row).get("submission")},
        actor=user,
        term_id=term_id,
    )
    await session.commit()


async def _submission(session: AsyncSession, row: ConstraintRow) -> list[ConstraintRow]:
    sub = _ref(row).get("submission")
    if not sub:
        return [row]
    same = [r for r in await _rows(session, ConstraintRow.term_id == row.term_id) if _ref(r).get("submission") == sub]
    return sorted(same, key=lambda r: r.id) or [row]


# --------------------------------------------------------------------------------------------- coordinator


async def decide(
    session: AsyncSession,
    actor: User,
    cid: int,
    decision: str,
    *,
    reason: str | None = None,
    reason_code: str | None = None,
    with_submission: bool = True,
) -> dict[str, Any]:
    """``POST /moderation/preferences/{id}/decide`` (``planning.edit``): ``accept`` switches the rule(s) on for the next
    solve; ``reject`` needs a written reason, which the academician receives. One "Tercih ekle" is one decision:
    the other rows of the same submission (one per distinct department ask) are decided with it unless
    ``with_submission`` is false."""
    if decision not in ("accept", "reject"):
        raise PreferenceError(422, "decision", "decision is accept or reject", "Karar 'accept' ya da 'reject' olmalı")
    row = await session.get(ConstraintRow, cid)
    if row is None or row.source != SOURCE:
        raise PreferenceError(404, "not_found", "preference not found", "Tercih bulunamadı")
    if status_of(row) != "pending":
        raise PreferenceError(
            409,
            "decided",
            f"the preference was already {status_of(row)}",
            "Bu tercih için zaten karar verildi",
            current=status_of(row),
        )
    why = n.clean_text(reason)
    if decision == "reject" and len(why or "") < REASON_MIN:
        raise PreferenceError(
            422,
            "reason_required",
            "a rejection needs a written reason; the academician reads it",
            "Ret için yazılı bir gerekçe gerekli; akademisyen bu gerekçeyi görür",
        )
    group = [r for r in (await _submission(session, row) if with_submission else [row]) if status_of(r) == "pending"]
    for r in group:
        if decision == "accept":
            _check_rule(r.kind, dict(r.params or {}))  # the guard again: params may have been edited meanwhile
    status = "accepted" if decision == "accept" else "rejected"
    for r in group:
        ref = _ref(r)
        ref.update(
            review=status,
            decided_by=actor.id,
            decided_at=_now(),
            reason=why,
            reason_code=(reason_code or "").strip()[:32] or None,
        )
        r.source_ref = ref
        r.enabled = decision == "accept"
    await session.flush()
    rids = sorted({i for r in group for i in _ints((r.params or {}).get("event_ids"))})
    await publish_event(
        session,
        f"preference.{decision}",
        "constraint",
        row.id,
        before={"review": "pending", "enabled": False},
        after={
            "review": status,
            "enabled": decision == "accept",
            "constraint_ids": [r.id for r in group],
            "submission": _ref(row).get("submission"),
            # the changes-since-publish list reads the touched requests from params.event_ids
            "params": {"event_ids": rids},
            "rules": [{"id": r.id, "kind": r.kind, "params": r.params} for r in group],
        },
        actor=actor,
        reason=why,
        term_id=row.term_id,
    )
    notified = await _notify(session, row, group, status, why)
    await session.commit()
    items = await items_out(session, group)
    return {
        "decision": decision,
        "status": status,
        "decided_ids": [r.id for r in group],
        "notified": notified,
        "items": items,
        "effective": _t("Bir sonraki çözümde etkili olur", "Takes effect at the next solve")
        if decision == "accept"
        else None,
    }


async def _notify(
    session: AsyncSession, row: ConstraintRow, group: list[ConstraintRow], status: str, reason: str | None
) -> bool:
    """The academician's notice (``preference.accepted`` / ``preference.rejected``) through notify_dispatch."""
    from app.services import notify_dispatch as nd
    from app.services.bookings_notify import _language

    ref = _ref(row)
    uid = ref.get("user_id") or row.created_by
    user = await session.get(User, int(uid)) if uid else None
    if user is None or not user.is_active:
        return False
    lang = "tr" if (await _language(session, user)) == "tr" else "en"
    items = await items_out(session, group)
    labels = sorted({lab for it in items for lab in it["labels"]})
    what = ", ".join(labels[:3]) + (" …" if len(labels) > 3 else "")
    text = dict(ref.get("text") or {})
    term = await session.get(Term, row.term_id) if row.term_id else None
    code = term.code if term else ""
    if status == "rejected":
        title = f"{what}: tercihiniz kabul edilmedi" if lang == "tr" else f"{what}: your preference was not accepted"
        body = f"{text.get('tr', '')}\nGerekçe: {reason}" if lang == "tr" else f"{text.get('en', '')}\nReason: {reason}"
    else:
        title = f"{what}: tercihiniz kabul edildi" if lang == "tr" else f"{what}: your preference was accepted"
        body = (
            f"{text.get('tr', '')}\n{code} için bir sonraki çözümde, bölüm talebinden sonra gelen bir tercih olarak "
            "uygulanır."
            if lang == "tr"
            else f"{text.get('en', '')}\nIt applies at the next {code} solve, ranked below the department's request."
        )
    notice = nd.Notice(
        event=f"preference.{status}",
        key=f"preference:{ref.get('submission') or row.id}:{status}",
        title=title,
        body=body,
        link="/moderation/me",
        data={
            "constraint_ids": [r.id for r in group],
            "term_id": row.term_id,
            "status": status,
            "reason": reason,
            "request_ids": sorted({i for it in items for i in it["request_ids"]}),
            "labels": labels,
        },
    )
    res = await nd.dispatch(session, user, notice)
    return any(d.status in ("sent", "skipped") for d in res)


async def term_list(
    session: AsyncSession, term: Term, instructor_ids: frozenset[int] | None, status: str | None = None
) -> dict[str, Any]:
    """``GET /terms/{id}/moderation/teacher-preferences``: the term's academician wishes, newest first;
    ``instructor_ids`` limits them to those people (Q11: an academician sees their own)."""
    rows = await _rows(session, ConstraintRow.term_id == term.id)
    if instructor_ids is not None:
        rows = [r for r in rows if int(_ref(r).get("instructor_id") or 0) in instructor_ids]
    counts = {s: sum(1 for r in rows if status_of(r) == s) for s in STATUSES}
    wanted = {s.strip() for s in (status or "").split(",") if s.strip() and s.strip() != "all"}
    if wanted:
        rows = [r for r in rows if status_of(r) in wanted]
    items = await items_out(session, rows)
    return {"term_id": term.id, "counts": counts, "total": len(items), "items": items}


async def by_request(session: AsyncSession, term_id: int) -> dict[int, list[dict[str, Any]]]:
    """request id -> brief academician wishes on it (the moderation read models' ``teacher_preferences``)."""
    rows = await _rows(session, ConstraintRow.term_id == term_id)
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        ref = _ref(r)
        brief = {
            "id": r.id,
            "status": status_of(r),
            "kind": r.kind,
            "text": ref.get("text") or _t(r.nl_text or "", r.nl_text or ""),
            "submitted_at": ref.get("submitted_at"),
            "reason": ref.get("reason"),
            "instructor_id": ref.get("instructor_id"),
        }
        for rid in _ints(ref.get("request_ids") or (r.params or {}).get("event_ids")):
            out[rid].append(brief)
    return dict(out)


async def pending_by_instructor(session: AsyncSession, term_id: int) -> dict[int, int]:
    out: dict[int, int] = defaultdict(int)
    for r in await _rows(session, ConstraintRow.term_id == term_id):
        if status_of(r) == "pending" and _ref(r).get("instructor_id"):
            out[int(_ref(r)["instructor_id"])] += 1
    return dict(out)


async def counts_for_user(session: AsyncSession, user: User) -> dict[str, int]:
    rows = await _rows(session, ConstraintRow.created_by == user.id)
    return {s: sum(1 for r in rows if status_of(r) == s) for s in STATUSES}


__all__ = [
    "KINDS",
    "SOURCE",
    "WEIGHT",
    "PreferenceError",
    "by_request",
    "decide",
    "item_out",
    "mine",
    "pending_by_instructor",
    "status_of",
    "submit",
    "term_list",
    "withdraw",
]
