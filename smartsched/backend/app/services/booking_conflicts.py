"""P2 conflict resolver after publishing (docs/product/booking-enhancements.md §P2 and §4.4).

When a timetable run is published (``POST /runs/{id}/activate`` -> event ``run.activate``), :func:`detect` stores
one ``booking_conflicts`` row per active booking or open request of the run's term (from today on) whose slot the
run's classes now hold. The planner then works through the resolver:

* :func:`plan` -- the open conflicts grouped by series (a 14-week series is one row), each with ranked options:
  ``move_room`` (same time, a free room that fits: the booking's headcount or else the old room's capacity, the
  booking's features or else the old room's solver tags, same building first; the T1 finder ranks them),
  ``move_period`` (same room, an adjacent period), ``move_day`` (same room and period, another weekday of that
  week; single bookings), ``cancel`` (with a reason; an open request is declined) and ``override`` (keep the
  booking although the timetable holds the slot; ``planning.admin`` only). With no move option the row says why
  ("Yayınlanan programla çakıştı, uygun oda bulunamadı").
* :func:`apply` -- a batch of decisions, all or nothing (any invalid item rolls every item back, nothing is
  written), audited (``booking.move`` / ``booking.cancel`` / ``approval.reject`` bulk events and
  ``booking_conflict.resolve``), and **one digest per owner** through :mod:`app.services.notify_dispatch`
  (``booking.conflict_resolved``: "Rezervasyonlarınız yeni programa göre güncellendi: 3 değişiklik"). Applying
  the same payload twice changes nothing the second time and sends nothing twice.
* :func:`auto` -- the top option of every conflict whose score clears :data:`AUTO_SCORE`, as a dry-run payload
  the planner accepts in bulk.

A plan belongs to its run: once another run of the same term and kind is published its open rows become
``IGNORED`` (``superseded``) and the plan of the old run answers 409 ``plan_stale``.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingSlot, Building, ScheduleRun, Term, User
from app.models.base import utcnow
from app.models.booking import BOOKED, CANCELLED, PENDING, REJECTED
from app.models.catalog import Room
from app.models.conflicts import IGNORED, OPEN, RESOLVED, BookingConflict
from app.services import audit
from app.services import bookings as bsvc
from app.services import notify_dispatch as nd
from app.services.bookings_calendar import CalendarError, date_infos, term_info
from app.services.bookings_perms import Access
from app.services.events import DomainEvent, publish_event, subscribe

log = logging.getLogger(__name__)

EVENT = "booking.conflict_resolved"
# registered next to the built-in events (the preferences screen lists it; users may switch channels per event)
nd.EVENTS.setdefault(
    EVENT,
    ("Rezervasyonum yayınlanan programa göre değişti", "My booking changed to fit a published timetable"),
)

ACTIONS = ("move_room", "move_period", "move_day", "cancel", "override")
SCOPES = ("one", "future", "all")
#: auto-pick threshold: a room option whose finder score (wasted-seat share + unrequested-tag penalty - building
#: bonus) is at most this, or any same-room period / day move
AUTO_SCORE = 0.5
NO_ROOM_TR = "Yayınlanan programla çakıştı, uygun oda bulunamadı"
NO_ROOM_EN = "Clashes with the published timetable; no suitable room was found"
SHIFTS = (1, -1, 2, -2)


class ConflictError(Exception):
    def __init__(self, status: int, code: str, message: str, message_tr: str, **data: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.message_tr, self.data = status, code, message, message_tr, data

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "message_en": self.message,
            "message_tr": self.message_tr,
            **self.data,
        }


# --------------------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------------------


async def detect(session: AsyncSession, run: ScheduleRun, actor: User | None = None) -> dict[str, int]:
    """Store the clashes of ``run`` (published) with the term's bookings and requests from today on; close the open
    rows of runs it replaced. Idempotent: an existing (run, booking) row is kept as it is."""
    today = await bsvc.today(session)
    superseded = list(
        (
            await session.execute(
                select(BookingConflict)
                .join(ScheduleRun, ScheduleRun.id == BookingConflict.run_id)
                .where(
                    BookingConflict.status == OPEN,
                    BookingConflict.run_id != run.id,
                    ScheduleRun.term_id == run.term_id,
                    ScheduleRun.kind == run.kind,
                )
            )
        ).scalars()
    )
    now = utcnow()
    for c in superseded:
        c.status, c.resolved_at = IGNORED, now
        c.resolution = {"action": "superseded", "by_run_id": run.id, "at": now.isoformat()}
    rows = list(
        (
            await session.execute(
                select(Booking).where(
                    Booking.term_id == run.term_id,
                    Booking.status.in_((BOOKED, PENDING)),
                    Booking.date >= today,
                )
            )
        ).scalars()
    )
    existing = {
        c.booking_id: c
        for c in (await session.execute(select(BookingConflict).where(BookingConflict.run_id == run.id))).scalars()
    }
    found: dict[int, bsvc.Held] = {}
    if rows:
        occ = await bsvc.timetable_occupancy(
            session, {b.room_id for b in rows}, min(b.date for b in rows), max(b.date for b in rows)
        )
        for b in rows:
            held = next(
                (
                    h
                    for h in occ.get((b.room_id, b.date), [])
                    if h.kind == "timetable" and h.run_id == run.id and h.overlaps(b.start_period, b.end_period)
                ),
                None,
            )
            if held is not None:
                found[b.id] = held
    new = 0
    for b in rows:
        held = found.get(b.id)
        if held is None or b.id in existing:
            continue
        session.add(
            BookingConflict(
                run_id=run.id,
                term_id=run.term_id,
                booking_id=b.id,
                series_id=b.series_id,
                room_id=b.room_id,
                date=b.date,
                start_period=b.start_period,
                end_period=b.end_period,
                held={
                    "assignment_id": held.ref_id,
                    "label": held.label,
                    "start_period": held.start,
                    "end_period": held.end,
                },
                detected_at=now,
                status=OPEN,
            )
        )
        new += 1
    cleared = 0
    for bid, c in existing.items():
        if c.status == OPEN and bid not in found:
            c.status, c.resolved_at = IGNORED, now
            c.resolution = {"action": "cleared", "at": now.isoformat()}
            cleared += 1
    await session.flush()
    out = {
        "new": new,
        "open": new + sum(1 for c in existing.values() if c.status == OPEN),
        "cleared": cleared,
        "superseded": len(superseded),
    }
    if new or cleared or superseded:
        await audit.record(
            session, "booking_conflict.detect", "run", run.id, after=out, actor=actor, term_id=run.term_id
        )
    return out


async def on_run_activated(session: AsyncSession, ev: DomainEvent) -> None:
    """``run.activate`` subscriber: detection inside the publish transaction, in a SAVEPOINT so that a failure here
    can never undo the publish."""
    run = await session.get(ScheduleRun, int(ev.entity_id))
    if run is None:
        return
    actor = await session.get(User, ev.actor_id) if ev.actor_id else None
    sp = await session.begin_nested()
    try:
        await detect(session, run, actor)
    except Exception:  # noqa: BLE001 - the publish stands; the planner can re-scan (POST .../detect)
        await sp.rollback()
        log.exception("conflict detection for run %s failed", run.id)
        return
    await sp.commit()


subscribe("run.activate", on_run_activated)


# --------------------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------------------


async def active_run(session: AsyncSession, run_id: int) -> ScheduleRun:
    run = await session.get(ScheduleRun, run_id)
    if run is None:
        raise ConflictError(404, "run_not_found", "run not found", "program bulunamadı")
    if not run.is_active:
        raise ConflictError(
            409,
            "plan_stale",
            f"run {run_id} is not the published timetable any more; open the resolver of the published run",
            f"{run_id} numaralı program artık yayında değil; yayındaki programın çakışmalarını açın",
        )
    return run


def _group_key(c: BookingConflict) -> str:
    return f"series:{c.series_id}" if c.series_id else f"booking:{c.booking_id}"


def _period_text(s: int, e: int) -> str:
    from app.importers import normalize as n

    return f"{n.PERIODS[s - 1].start:%H:%M}-{n.PERIODS[e - 1].end:%H:%M}"


async def _building_code(session: AsyncSession, room: Room) -> str | None:
    if room.building_id:
        b = await session.get(Building, room.building_id)
        if b is not None:
            return b.code
    return room.code[:1] or None


async def _span_period(session: AsyncSession, info: Any, room: Room, d: date, s: int, e: int) -> int | None:
    from app.services.approvals import _period_for_span

    try:
        return await _period_for_span(session, info, room, d, s, e)
    except CalendarError:
        return None


async def _owner(session: AsyncSession, b: Booking) -> User | None:
    for uid in (b.user_id, b.created_by):
        if uid:
            u = await session.get(User, uid)
            if u is not None and u.is_active:
                return u
    return None


async def _options(
    session: AsyncSession,
    access: Access,
    run: ScheduleRun,
    room: Room,
    first: Booking,
    clash: list[BookingConflict],
    exclude: set[int],
) -> tuple[list[dict[str, Any]], str | None]:
    from app.services import find_room as fr

    term = await session.get(Term, run.term_id)
    info = await term_info(session, term) if term else None
    dates = sorted({c.date for c in clash})
    s, e = first.start_period, first.end_period
    headcount = first.headcount or room.capacity or 0
    opts: list[dict[str, Any]] = []
    reason_detail: str | None = None
    if info is not None:
        q = fr.FindQuery(
            term_id=run.term_id,
            dates=dates,
            start=s,
            end=e,
            headcount=headcount,
            tags=[str(t) for t in (room.tags or [])],
            preferred_building=await _building_code(session, room),
            include_busy=False,
            flex_periods=0,
            limit=8,
        )
        try:
            res = await fr.find_rooms(session, access, q)
        except fr.FindError as exc:
            res = {"results": []}
            reason_detail = exc.message_tr
        for x in res["results"]:
            if x["room_id"] == room.id or x["status"] not in ("free", "requestable"):
                continue
            if x["start_period"] != s or x["end_period"] != e:
                continue
            opts.append(
                {
                    "id": f"room:{x['room_id']}",
                    "kind": "move_room",
                    "room_id": x["room_id"],
                    "room": x["name"],
                    "capacity": x["capacity"],
                    "building": x["building"],
                    "start_period": s,
                    "end_period": e,
                    "dates": [d.isoformat() for d in dates],
                    "score": x["fit"]["score"],
                    "reason": {
                        "tr": f"{x['name']} aynı saatte boş ({x['reason']['tr']})",
                        "en": f"{x['name']} is free at the same time ({x['reason']['en']})",
                    },
                }
            )
            if len([o for o in opts if o["kind"] == "move_room"]) >= 5:
                break
        # same room, an adjacent period on every clashing date
        for shift in SHIFTS:
            ns, ne = s + shift, e + shift
            if ns < 1 or ne > 18:
                continue
            ok = True
            for d in dates:
                if await _span_period(session, info, room, d, ns, ne) is None:
                    ok = False
                    break
                if await bsvc.find_conflict(session, room.id, d, ns, ne, exclude=exclude) is not None:
                    ok = False
                    break
            if ok:
                opts.append(
                    {
                        "id": f"period:{ns}-{ne}",
                        "kind": "move_period",
                        "room_id": room.id,
                        "room": room.display_name,
                        "start_period": ns,
                        "end_period": ne,
                        "dates": [d.isoformat() for d in dates],
                        "score": 0.1 * abs(shift),
                        "reason": {
                            "tr": f"{room.display_name} {_period_text(ns, ne)} boş ({shift:+d} ders saati)",
                            "en": f"{room.display_name} free {_period_text(ns, ne)} ({shift:+d} period)",
                        },
                    }
                )
        # same room and period, another weekday of the same week (single bookings)
        if len(dates) == 1:
            d0 = dates[0]
            today = await bsvc.today(session)
            monday = d0 - timedelta(days=d0.isoweekday() - 1)
            others = [monday + timedelta(days=i) for i in range(5) if monday + timedelta(days=i) != d0]
            others = [d for d in others if d >= today]
            infos = await date_infos(session, info, others) if others else {}
            for d in others:
                if not infos[d].open or await _span_period(session, info, room, d, s, e) is None:
                    continue
                if await bsvc.find_conflict(session, room.id, d, s, e, exclude=exclude) is None:
                    opts.append(
                        {
                            "id": f"day:{d.isoformat()}",
                            "kind": "move_day",
                            "room_id": room.id,
                            "room": room.display_name,
                            "start_period": s,
                            "end_period": e,
                            "dates": [d.isoformat()],
                            "score": 0.3 + 0.01 * abs((d - d0).days),
                            "reason": {
                                "tr": f"{room.display_name} {fr.DAY_TR[d.isoweekday()]} {d:%d.%m} aynı saatte boş",
                                "en": f"{room.display_name} free on {fr.DAY_EN[d.isoweekday()]} {d:%d.%m} at the "
                                "same time",
                            },
                        }
                    )
    opts.sort(key=lambda o: (o["score"], ACTIONS.index(o["kind"]), o["id"]))
    no_room = None
    if not opts:
        need = f"{headcount} kişilik" + (
            f", {', '.join(str(t) for t in room.tags or [])} özellikli" if room.tags else ""
        )
        no_room = reason_detail or f"{need} boş oda yok ({', '.join(f'{d:%d.%m.%Y}' for d in dates)})"
    opts.append(
        {
            "id": "cancel",
            "kind": "cancel",
            "default_reason": NO_ROOM_TR if no_room else "Yayınlanan programla çakıştı",
            "reason": {"tr": "Rezervasyonu gerekçesiyle iptal et", "en": "Cancel the booking with a reason"},
        }
    )
    if access.can("planning.admin"):
        opts.append(
            {
                "id": "override",
                "kind": "override",
                "admin_only": True,
                "link": f"/calendar?run={run.id}",
                "reason": {
                    "tr": "Rezervasyonu koru (yönetici kararı; programın düzeltilmesi gerekir)",
                    "en": "Keep the booking (administrator decision; the timetable needs adjusting)",
                },
            }
        )
    return opts, no_room


async def _booking_line(session: AsyncSession, b: Booking, room: Room | None) -> dict[str, Any]:
    owner = await session.get(User, b.user_id) if b.user_id else None
    return {
        "booking_id": b.id,
        "status": b.status,
        "date": b.date.isoformat(),
        "start_period": b.start_period,
        "end_period": b.end_period,
        "time": _period_text(b.start_period, b.end_period),
        "room_id": b.room_id,
        "room": room.display_name if room else None,
        "user_id": b.user_id,
        "user": audit.user_label(owner),
        "notes": b.notes,
        "headcount": b.headcount,
    }


async def plan(session: AsyncSession, access: Access, run_id: int) -> dict[str, Any]:
    run = await active_run(session, run_id)
    rows = list(
        (
            await session.execute(
                select(BookingConflict)
                .where(BookingConflict.run_id == run.id, BookingConflict.status == OPEN)
                .order_by(BookingConflict.date, BookingConflict.start_period, BookingConflict.id)
            )
        ).scalars()
    )
    groups: dict[str, list[BookingConflict]] = defaultdict(list)
    for c in rows:
        groups[_group_key(c)].append(c)
    out_groups: list[dict[str, Any]] = []
    for key, items in groups.items():
        bookings = [await session.get(Booking, c.booking_id) for c in items]
        live = [(c, b) for c, b in zip(items, bookings, strict=True) if b is not None]
        if not live:
            continue
        first = live[0][1]
        room = await session.get(Room, first.room_id)
        if room is None:
            continue
        ids = {b.id for _, b in live}
        if first.series_id:
            ids |= set(
                (
                    await session.execute(
                        select(Booking.id).where(Booking.series_id == first.series_id, Booking.status == BOOKED)
                    )
                ).scalars()
            )
        options, no_room = await _options(session, access, run, room, first, [c for c, _ in live], ids)
        out_groups.append(
            {
                "key": key,
                "series_id": first.series_id,
                "kind": "series" if first.series_id else "booking",
                "requested": first.status == PENDING,
                "room_id": room.id,
                "room": room.display_name,
                "default_scope": "one",
                "conflicts": [
                    {"conflict_id": c.id, **await _booking_line(session, b, room), "held": c.held} for c, b in live
                ],
                "options": options,
                "no_room_reason": {"tr": f"{NO_ROOM_TR}: {no_room}", "en": NO_ROOM_EN} if no_room else None,
            }
        )
    series = sum(1 for g in out_groups if g["series_id"])
    n_conf = sum(len(g["conflicts"]) for g in out_groups)
    return {
        "run_id": run.id,
        "term_id": run.term_id,
        "open": n_conf,
        "groups": out_groups,
        "banner": {
            "tr": f"Yayınlanan programla çakışan {n_conf} rezervasyon ({series} seri) · Çöz",
            "en": f"{n_conf} booking(s) clash with the published timetable ({series} series) · Resolve",
        }
        if n_conf
        else None,
    }


async def summary(session: AsyncSession) -> dict[str, Any]:
    """Open conflicts of every published run (the planner's banner)."""
    q = (
        select(BookingConflict, ScheduleRun)
        .join(ScheduleRun, ScheduleRun.id == BookingConflict.run_id)
        .where(BookingConflict.status == OPEN, ScheduleRun.is_active.is_(True))
    )
    per: dict[int, dict[str, Any]] = {}
    for c, run in (await session.execute(q)).all():
        item = per.setdefault(
            run.id,
            {
                "run_id": run.id,
                "term_id": run.term_id,
                "kind": run.kind,
                "label": run.label,
                "open": 0,
                "_series": set(),
            },
        )
        item["open"] += 1
        if c.series_id:
            item["_series"].add(c.series_id)
    runs = []
    for item in per.values():
        series = len(item.pop("_series"))
        item["series"] = series
        item["message_tr"] = f"Yayınlanan programla çakışan {item['open']} rezervasyon ({series} seri) · Çöz"
        item["message_en"] = f"{item['open']} booking(s) clash with the published timetable ({series} series)"
        runs.append(item)
    return {"runs": sorted(runs, key=lambda x: x["run_id"])}


async def auto(session: AsyncSession, access: Access, run_id: int) -> dict[str, Any]:
    """Dry run only: the payload of ``apply`` with, for every conflict, the best option that clears the threshold
    and that no earlier suggestion of the batch took already (two clashes at 09:20 never get the same free room)."""
    p = await plan(session, access, run_id)
    items: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    claimed: set[tuple[int, str, int]] = set()
    for g in p["groups"]:
        moves = [
            o
            for o in g["options"]
            if o["kind"] in ("move_room", "move_period", "move_day")
            and (o["kind"] != "move_room" or o["score"] <= AUTO_SCORE)
        ]
        for c in g["conflicts"]:
            pick = None
            for o in moves:
                day = o["dates"][0] if o["kind"] == "move_day" else c["date"]
                slots = {(o["room_id"], day, q) for q in range(o["start_period"], o["end_period"] + 1)}
                if not slots & claimed:
                    pick, claimed = o, claimed | slots
                    break
            if pick is not None:
                items.append(
                    {"conflict_id": c["conflict_id"], "action": pick["kind"], "option_id": pick["id"], "scope": "one"}
                )
            else:
                left.append(
                    {
                        "conflict_id": c["conflict_id"],
                        "group": g["key"],
                        "reason": g["no_room_reason"]
                        or {"tr": "Eşiği geçen boş seçenek kalmadı", "en": "No free option above the threshold left"},
                    }
                )
    return {"run_id": p["run_id"], "dry_run": True, "items": items, "unresolved": left}


# --------------------------------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------------------------------


def _problem(conflict_id: int | None, code: str, tr: str, en: str) -> dict[str, Any]:
    return {"conflict_id": conflict_id, "code": code, "message_tr": tr, "message_en": en}


async def _targets(session: AsyncSession, c: BookingConflict, b: Booking, scope: str) -> list[Booking]:
    if scope == "one" or not b.series_id:
        return [b]
    today = await bsvc.today(session)
    q = select(Booking).where(
        Booking.series_id == b.series_id, Booking.status.in_((BOOKED, PENDING)), Booking.date >= today
    )
    if scope == "future":
        q = q.where(Booking.date >= b.date)
    return list((await session.execute(q.order_by(Booking.date))).scalars())


def _same(res: dict[str, Any] | None, item: dict[str, Any]) -> bool:
    return bool(res) and all(res.get(k) == item.get(k) for k in ("action", "option_id", "scope"))  # type: ignore[union-attr]


async def apply(
    session: AsyncSession, access: Access, run_id: int, items: list[dict[str, Any]], *, dry_run: bool = False
) -> dict[str, Any]:
    run = await active_run(session, run_id)
    if not items:
        raise ConflictError(422, "no_items", "nothing to apply", "uygulanacak karar yok")
    problems: list[dict[str, Any]] = []
    already: list[int] = []
    planned: list[dict[str, Any]] = []
    claimed: set[tuple[int, date, int]] = set()
    touched: set[int] = set()
    for item in items:
        cid = item.get("conflict_id")
        action = item.get("action")
        scope = item.get("scope") or "one"
        reason = (item.get("reason") or "").strip() or None
        c = await session.get(BookingConflict, int(cid)) if cid is not None else None
        if c is None or c.run_id != run.id:
            problems.append(_problem(cid, "not_found", "çakışma bulunamadı", "conflict not found"))
            continue
        if c.status != OPEN:
            if _same(c.resolution, {"action": action, "option_id": item.get("option_id"), "scope": scope}):
                already.append(c.id)  # idempotent repeat of the same decision
            else:
                problems.append(
                    _problem(c.id, "not_open", f"çakışma zaten kapandı ({c.status})", f"conflict is {c.status}")
                )
            continue
        if action not in ACTIONS:
            problems.append(_problem(c.id, "action", "geçersiz işlem", f"action: one of {', '.join(ACTIONS)}"))
            continue
        if scope not in SCOPES:
            problems.append(_problem(c.id, "scope", "kapsam: one, future, all", "scope: one, future or all"))
            continue
        b = await session.get(Booking, c.booking_id)
        if b is None or b.status not in (BOOKED, PENDING):
            problems.append(_problem(c.id, "booking_gone", "rezervasyon artık etkin değil", "the booking is gone"))
            continue
        if action == "override" and not access.can("planning.admin"):
            problems.append(
                _problem(
                    c.id,
                    "override_forbidden",
                    "koruma kararını yalnızca yönetici verir",
                    "only an administrator may keep a clashing booking",
                )
            )
            continue
        if action == "override" and not reason:
            problems.append(_problem(c.id, "reason", "koruma için gerekçe yazın", "an override needs a reason"))
            continue
        if action == "move_day" and (b.series_id and scope != "one"):
            problems.append(
                _problem(c.id, "scope", "gün değişikliği tek rezervasyon içindir", "a day move applies to one booking")
            )
            continue
        targets = await _targets(session, c, b, scope)
        targets = [t for t in targets if t.id not in touched]
        touched |= {t.id for t in targets}
        moves: list[tuple[Booking, int, date, int, int, int]] = []
        if action.startswith("move_"):
            opt = str(item.get("option_id") or "")
            kind, _, val = opt.partition(":")
            if f"move_{kind}" != action or not val:
                problems.append(_problem(c.id, "option", "seçenek işlemle uyuşmuyor", "option does not fit action"))
                continue
            bterm = await session.get(Term, b.term_id)
            info = await term_info(session, bterm) if bterm else None
            bad = False
            for t in targets:
                new_room_id, new_date, s, e = t.room_id, t.date, t.start_period, t.end_period
                try:
                    if kind == "room":
                        new_room_id = int(val)
                    elif kind == "period":
                        a_, _, z_ = val.partition("-")
                        s, e = int(a_), int(z_)
                    else:
                        new_date = date.fromisoformat(val)
                except ValueError:
                    bad = True
                    problems.append(_problem(c.id, "option", "geçersiz seçenek", "invalid option"))
                    break
                room = await session.get(Room, new_room_id)
                if room is None or not room.is_bookable:
                    bad = True
                    problems.append(_problem(c.id, "room", "oda rezerve edilemez", "room cannot be booked"))
                    break
                pid = await _span_period(session, info, room, new_date, s, e) if info else None
                if pid is None:
                    bad = True
                    problems.append(
                        _problem(
                            c.id,
                            "period",
                            f"{room.display_name} için bu ders saati yok",
                            f"no such period for {room.display_name}",
                        )
                    )
                    break
                held = await bsvc.find_conflict(session, room.id, new_date, s, e, exclude={x.id for x in targets})
                taken = any((room.id, new_date, p) in claimed for p in range(s, e + 1))
                if held is not None or taken:
                    bad = True
                    problems.append(
                        _problem(
                            c.id,
                            "slot_taken",
                            f"{room.display_name} {new_date:%d.%m.%Y} {_period_text(s, e)} dolu",
                            f"{room.display_name} on {new_date:%d.%m.%Y} {_period_text(s, e)} is taken",
                        )
                    )
                    break
                claimed |= {(room.id, new_date, p) for p in range(s, e + 1)}
                moves.append((t, room.id, new_date, pid, s, e))
            if bad:
                continue
        planned.append(
            {
                "conflict": c,
                "booking": b,
                "action": action,
                "scope": scope,
                "reason": reason,
                "option_id": item.get("option_id"),
                "targets": targets,
                "moves": moves,
            }
        )
    if problems:
        await session.rollback()
        raise ConflictError(
            409,
            "invalid_items",
            f"{len(problems)} decision(s) cannot be applied; nothing was changed",
            f"{len(problems)} karar uygulanamadı; hiçbir değişiklik yapılmadı",
            problems=problems,
        )
    result = await _execute(session, access, run, planned)
    result["already"] = already
    if dry_run:
        await session.rollback()
        result["dry_run"] = True
        result["notified"] = 0
        return result
    await session.commit()
    result["dry_run"] = False
    return result


async def _execute(
    session: AsyncSession, access: Access, run: ScheduleRun, planned: list[dict[str, Any]]
) -> dict[str, Any]:
    from app.services import approvals

    now = utcnow()
    moved_items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = []
    cancelled_items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = []
    resolved_items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = []
    per_owner: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unnotified = 0
    rooms: dict[int, Room] = {}

    async def room_name(rid: int) -> str:
        if rid not in rooms:
            r = await session.get(Room, rid)
            if r is not None:
                rooms[rid] = r
        return rooms[rid].display_name if rid in rooms else str(rid)

    target_ids: set[int] = set()
    for p in planned:
        c: BookingConflict = p["conflict"]
        action, reason = p["action"], p["reason"]
        changes: list[dict[str, Any]] = []
        if action.startswith("move_"):
            for t, rid, d, pid, s, e in p["moves"]:
                before = bsvc.snap(t)
                old = {
                    "room": await room_name(t.room_id),
                    "date": t.date.isoformat(),
                    "time": _period_text(t.start_period, t.end_period),
                }
                await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == t.id))
                t.room_id, t.date, t.period_id, t.start_period, t.end_period = rid, d, pid, s, e
                t.updated_at, t.updated_by = now, access.user_id
                await session.flush()
                if t.status == BOOKED or t.held_until is not None:
                    for slot in bsvc.slot_rows(t):
                        session.add(slot)
                moved_items.append((t.id, before, bsvc.snap(t)))
                changes.append(
                    {
                        "booking": t,
                        "from": old,
                        "to": {"room": await room_name(rid), "date": d.isoformat(), "time": _period_text(s, e)},
                    }
                )
        elif action == "cancel":
            text = reason or NO_ROOM_TR
            for t in p["targets"]:
                before = bsvc.snap(t)
                old = {
                    "room": await room_name(t.room_id),
                    "date": t.date.isoformat(),
                    "time": _period_text(t.start_period, t.end_period),
                }
                if t.status == PENDING:
                    req = await approvals.request_for_booking(session, t)
                    if req is not None and req.status == PENDING:
                        await approvals._close(
                            session, req, await approvals.bookings_of(session, req), REJECTED, text, access.user
                        )
                        req.reason_code, req.note = "slot_taken", text
                        await publish_event(
                            session,
                            "approval.reject",
                            "approval_request",
                            req.id,
                            after={"status": REJECTED, "reason_code": "slot_taken", "note": text},
                            actor=access.user,
                            reason=text,
                            term_id=t.term_id,
                        )
                    elif t.status == PENDING:
                        t.status, t.cancel_reason, t.cancelled_at = REJECTED, text, now
                else:
                    await session.execute(delete(BookingSlot).where(BookingSlot.booking_id == t.id))
                    t.status, t.cancelled_at, t.cancelled_by, t.cancel_reason = CANCELLED, now, access.user_id, text
                    cancelled_items.append((t.id, before, bsvc.snap(t)))
                changes.append({"booking": t, "from": old, "to": None, "reason": text})
        target_ids |= {t.id for t in p["targets"]}
        res = {
            "action": action,
            "option_id": p["option_id"],
            "scope": p["scope"],
            "reason": reason or (NO_ROOM_TR if action == "cancel" else None),
            "booking_ids": [t.id for t in p["targets"]],
            "by": access.user_id,
            "at": now.isoformat(),
        }
        before_c = {"status": c.status}
        c.status = IGNORED if action == "override" else RESOLVED
        c.resolution, c.resolved_at, c.resolved_by = res, now, access.user_id
        resolved_items.append((c.id, before_c, {"status": c.status, **res}))
        for ch in changes:
            owner = await _owner(session, ch["booking"])
            if owner is None:
                unnotified += 1
                continue
            per_owner[owner.id].append({**ch, "conflict_id": c.id})
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            409,
            "slot_taken",
            "a slot was booked by someone else meanwhile; nothing was changed",
            "bir saat bu sırada başkası tarafından alındı; hiçbir değişiklik yapılmadı",
        ) from exc
    # other open conflicts of the same run whose bookings this batch moved or cancelled are resolved with them
    if target_ids:
        for other in (
            await session.execute(
                select(BookingConflict).where(
                    BookingConflict.run_id == run.id,
                    BookingConflict.status == OPEN,
                    BookingConflict.booking_id.in_(sorted(target_ids)),
                )
            )
        ).scalars():
            other.status, other.resolved_at, other.resolved_by = RESOLVED, now, access.user_id
            other.resolution = {"action": "with_series", "at": now.isoformat(), "by": access.user_id}
            resolved_items.append((other.id, {"status": OPEN}, {"status": RESOLVED, "action": "with_series"}))
    why = f"P2: yayınlanan programla çakışma (program #{run.id})"
    if moved_items:
        await publish_event(
            session,
            "booking.move",
            "booking",
            moved_items[0][0],
            items=moved_items,
            actor=access.user,
            reason=why,
            term_id=run.term_id,
            payload={"booking_ids": [i[0] for i in moved_items], "actor_id": access.user_id},
        )
    if cancelled_items:
        await publish_event(
            session,
            "booking.cancel",
            "booking",
            cancelled_items[0][0],
            items=cancelled_items,
            actor=access.user,
            reason=why,
            term_id=run.term_id,
            payload={"booking_ids": [i[0] for i in cancelled_items], "actor_id": access.user_id},
        )
    await audit.record_many(
        session,
        "booking_conflict.resolve",
        "booking_conflict",
        resolved_items,
        parent_entity_id=run.id,
        parent_entity_type="run",
        actor=access.user,
        term_id=run.term_id,
    )
    notified = 0
    for uid, changes in sorted(per_owner.items()):
        user = await session.get(User, uid)
        if user is None:
            continue
        if await _digest(session, user, run, changes):
            notified += 1
    return {
        "run_id": run.id,
        "resolved": [p["conflict"].id for p in planned],
        "moved": [i[0] for i in moved_items],
        "cancelled": [i[0] for i in cancelled_items],
        "kept": [p["conflict"].id for p in planned if p["action"] == "override"],
        "notified": notified,
        "unnotified": unnotified,
    }


async def _digest(session: AsyncSession, user: User, run: ScheduleRun, changes: list[dict[str, Any]]) -> bool:
    """One notice for the owner, whatever the number of changed bookings (one series = 14 lines, one message)."""
    from app.services.bookings_notify import _language

    lang = "tr" if (await _language(session, user)) == "tr" else "en"
    n_ch = len(changes)
    if lang == "tr":
        title = f"Rezervasyonlarınız yeni programa göre güncellendi: {n_ch} değişiklik"
    else:
        title = f"Your bookings were updated to fit the new timetable: {n_ch} change(s)"
    lines = []
    for ch in sorted(changes, key=lambda x: (x["from"]["date"], x["from"]["time"])):
        f = ch["from"]
        d = date.fromisoformat(f["date"])
        head = f"{d:%d.%m.%Y} {f['time']} {f['room']}"
        if ch["to"] is None:
            tail = ("iptal edildi: " if lang == "tr" else "cancelled: ") + str(ch.get("reason") or "")
        else:
            t = ch["to"]
            td = date.fromisoformat(t["date"])
            tail = f"→ {td:%d.%m.%Y} {t['time']} {t['room']}"
        lines.append(f"{head} {tail}")
    ids = sorted(int(ch["conflict_id"]) for ch in changes)
    digest = hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest()[:16]
    key = f"conflicts:{run.id}:{user.id}:{digest}"
    res = await nd.dispatch(
        session,
        user,
        nd.Notice(
            event=EVENT,
            key=key,
            title=title,
            body="\n".join(lines),
            link="/my-bookings",
            data={
                "run_id": run.id,
                "changes": [
                    {"booking_id": ch["booking"].id, "from": ch["from"], "to": ch["to"], "reason": ch.get("reason")}
                    for ch in changes
                ],
            },
        ),
    )
    return any(d.status in ("sent", "skipped") for d in res)
