"""Read actions 3-5: ``find_free_rooms`` (POST /rooms/find), ``room_day_schedule`` (GET /bookings/grid) and
``my_bookings`` (GET /bookings/mine). Each calls the page's own service with the person's ``Access``; names of other
people and booking notes are shown only where the grid itself shows them (``booking_out`` applies the permissions),
and notes are never put in a card (context minimisation, architecture doc §2.4)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from pydantic import Field

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.common import ClockText, DayText, day_label, resolve_day, resolve_rooms
from app.ai.helper.actions.registry import ActionRefused, Args, Ctx, action
from app.services import bookings as bsvc
from app.services import find_room as fsvc
from app.services.bookings_calendar import CalendarError
from app.services.bookings_settings import get_group

BOOKERS = ("book_single.create", "book_single.request")


def _choice(arg: str, rooms: list[Any], args: dict[str, Any], action_name: str) -> s.ChoiceCard:
    return s.ChoiceCard(
        id=cards.new_id(),
        action=action_name,
        arg=arg,
        question=cards.txt("Hangi salon?", "Which room?"),
        options=[
            s.Option(
                value=r.id,
                label=cards.txt(r.display_name or r.code),
                hint=cards.txt(f"{r.capacity} kişilik", f"{r.capacity} seats"),
            )
            for r in rooms[:5]
        ],
        args={k: v for k, v in args.items() if k != arg},
    )


# ------------------------------------------------------------------------------------------- find free rooms


class FindFreeRoomsArgs(Args):
    date: DayText = ""
    start: ClockText = ""
    end: ClockText = ""
    headcount: Annotated[int, Field(ge=0, le=5000, description="seats needed; 0 = any")] = 0
    building: Annotated[str, Field(max_length=40, description="building name or code; '' = any")] = ""
    text: Annotated[str, Field(max_length=100, description="room features in words, e.g. 'projeksiyon'; '' = none")] = (
        ""
    )


@action(
    name="find_free_rooms",
    kind="read",
    args=FindFreeRoomsArgs,
    summary_tr="Boş derslik bul",
    summary_en="Find a free room",
    description="Find rooms the user may book that are free on a date and time (and fit a headcount).",
    route="POST /rooms/find",
    card="list",
    route_args={
        "date": "date",
        "start": "start",
        "end": "end",
        "headcount": "headcount",
        "building": "buildings",
        "text": "text",
    },
)
async def find_free_rooms(ctx: Ctx, args: FindFreeRoomsArgs) -> s.CardBase:
    d = await resolve_day(ctx, args.date) or await bsvc.today(ctx.session)
    if not args.start:
        return s.FormCard(
            id=cards.new_id(),
            action="find_free_rooms",
            title=cards.txt("Boş derslik bul", "Find a free room"),
            risk="R1",
            missing=["start"],
            fields=[
                s.FormField(
                    name="date", label=cards.txt("Tarih", "Date"), kind="date", required=True, value=d.isoformat()
                ),
                s.FormField(name="start", label=cards.txt("Başlangıç", "Start"), kind="time", required=True),
                s.FormField(
                    name="end", label=cards.txt("Bitiş", "End"), kind="time", required=False, value=args.end or None
                ),
                s.FormField(
                    name="headcount",
                    label=cards.txt("Kişi sayısı", "Headcount"),
                    kind="number",
                    required=False,
                    value=args.headcount or None,
                ),
            ],
        )
    q = fsvc.FindQuery(
        dates=[d],
        start=args.start,
        end=args.end or None,
        headcount=args.headcount,
        buildings=[args.building] if args.building else [],
        text=args.text or None,
        include_busy=False,
        limit=cards.LIST_ROWS * 4,
    )
    try:
        out = await fsvc.find_rooms(ctx.session, ctx.access, q)
    except fsvc.FindError as exc:
        raise ActionRefused(exc.status, exc.code, exc.message_tr, exc.message) from exc
    good = [r for r in out["results"] if r["status"] in ("free", "requestable") and r.get("action") != "none"]
    tr_day, en_day = day_label(d)
    time_text = f"{out['time'].get('start', args.start)}–{out['time'].get('end', args.end)}".strip("–")
    rows = []
    for r in good[: cards.LIST_ROWS]:
        request = r["action"] == "request"
        rows.append(
            s.Row(
                id=f"room:{r['room_id']}",
                cells={
                    "room": cards.clean(r["name"] or r["code"], 64),
                    "capacity": cards.txt(f"{r['capacity']} kişilik", f"{r['capacity']} seats"),
                    "status": cards.txt("Onayla ayrılır", "Needs approval") if request else cards.txt("Boş", "Free"),
                },
                actions=[
                    s.RowAction(
                        action="create_booking",
                        label=cards.txt("Talep et", "Request") if request else cards.txt("Ayır", "Book"),
                        args={"room": r["room_id"], "date": d.isoformat(), "period_id": r.get("period_id") or 0},
                    )
                ]
                if r.get("period_id")
                else [],
            )
        )
    return s.ListCard(
        id=cards.new_id(),
        action="find_free_rooms",
        title=cards.txt(f"Boş salonlar · {tr_day} {time_text}", f"Free rooms · {en_day} {time_text}"),
        columns=[
            s.Column(key="room", label=cards.txt("Salon", "Room"), kind="room"),
            s.Column(key="capacity", label=cards.txt("Kapasite", "Capacity"), kind="number"),
            s.Column(key="status", label=cards.txt("Durum", "Status"), kind="status"),
        ],
        rows=rows,
        total=len(good),
        more="find_room",
        empty=cards.txt("Bu saatte uygun salon yok.", "No room is free at this time."),
    )


# ------------------------------------------------------------------------------------------ room day schedule


class RoomDayArgs(Args):
    room: Annotated[str, Field(max_length=40, description="room code or name, e.g. 'A 204'")] = ""
    date: DayText = ""


SLOT_TEXT = {
    "available": ("Boş", "Free"),
    "booked": ("Rezerve", "Booked"),
    "timetable": ("Ders programında", "In the timetable"),
    "unavailable": ("Kapalı", "Closed"),
}


@action(
    name="room_day_schedule",
    kind="read",
    permission=("room.view",),
    args=RoomDayArgs,
    summary_tr="Salonun günlük durumu",
    summary_en="A room's day",
    description="Show one room's periods on one day: free, booked or in the timetable.",
    route="GET /bookings/grid",
    card="list",
    gate="maintenance",
    route_args={"date": "date"},
    resolved=("room",),
)
async def room_day_schedule(ctx: Ctx, args: RoomDayArgs) -> s.CardBase:
    rooms = await resolve_rooms(ctx, args.room)
    if not rooms:
        raise ActionRefused(
            404,
            "room_not_found",
            f"“{args.room}” adında bir salon bulunamadı.",
            f"No room called “{args.room}” was found.",
        )
    if len(rooms) > 1:
        return _choice("room", rooms, args.model_dump(), "room_day_schedule")
    room = rooms[0]
    d = await resolve_day(ctx, args.date) or await bsvc.today(ctx.session)
    try:
        org = await get_group(ctx.session, "org")
        grid = await bsvc.grid(
            ctx.session,
            ctx.access,
            display="room",
            d=d,
            term_id=None,
            room_group_id=None,
            room_id=room.id,
            use_room_groups=org["use_room_groups"],
        )
    except CalendarError as exc:
        raise ActionRefused(409, "calendar", str(exc), str(exc)) from exc
    periods = {p["id"]: p for p in grid["periods"]}
    rows = []
    for slot in grid["slots"]:
        if slot["room_id"] != room.id or slot["date"] != d.isoformat():
            continue
        p = periods.get(slot["period_id"])
        if p is None:
            continue
        st = slot["status"]
        tr, en = SLOT_TEXT.get(st, ("Kapalı", "Closed"))
        actions = []
        if st == "available" and slot.get("allow_single") and not slot.get("past"):
            actions.append(
                s.RowAction(
                    action="create_booking",
                    label=cards.txt("Talep et", "Request") if slot.get("request_only") else cards.txt("Ayır", "Book"),
                    args={"room": room.id, "date": d.isoformat(), "period_id": p["id"]},
                )
            )
        rows.append(
            s.Row(
                id=f"period:{p['id']}",
                cells={
                    "time": f"{p['time_start']}–{p['time_end']}",
                    "period": cards.clean(p["name"], 40),
                    "status": cards.txt(tr, en),
                },
                actions=actions,
            )
        )
    tr_day, en_day = day_label(d)
    free = sum(1 for r in rows if r.actions)
    return s.ListCard(
        id=cards.new_id(),
        action="room_day_schedule",
        title=cards.txt(
            f"{room.display_name} · {tr_day} · {free} boş saat",
            f"{room.display_name} · {en_day} · {free} free period(s)",
        ),
        columns=[
            s.Column(key="time", label=cards.txt("Saat", "Time"), kind="time"),
            s.Column(key="period", label=cards.txt("Ders saati", "Period"), kind="text"),
            s.Column(key="status", label=cards.txt("Durum", "Status"), kind="status"),
        ],
        # the free periods first, so the five visible rows are the bookable ones
        rows=sorted(rows, key=lambda r: not r.actions)[:20],
        total=len(rows),
        more="bookings",
        empty=cards.txt("Bu gün için ders saati yok.", "No periods on this day."),
    )


# ---------------------------------------------------------------------------------------------- my bookings


class MyBookingsArgs(Args):
    days: Annotated[int, Field(ge=0, le=120, description="how many days ahead; 0 = the next 14 days")] = 0


@action(
    name="my_bookings",
    kind="read",
    permission=BOOKERS,
    args=MyBookingsArgs,
    summary_tr="Rezervasyonlarım",
    summary_en="My bookings",
    description="List the user's own upcoming bookings (with a cancel button each).",
    route="GET /bookings/mine",
    card="list",
    gate="list",
    resolved=("days",),
)
async def my_bookings(ctx: Ctx, args: MyBookingsArgs) -> s.CardBase:
    today = await bsvc.today(ctx.session)
    until = today + timedelta(days=args.days or 14)
    items = await bsvc.list_bookings(
        ctx.session, ctx.access, user_id=ctx.access.user_id, d_from=today, d_to=until, status="BOOKED"
    )
    rows = []
    for b in items:
        tr_day, en_day = day_label(date.fromisoformat(b["date"]))
        rows.append(
            s.Row(
                id=f"booking:{b['id']}",
                cells={
                    "date": cards.txt(tr_day, en_day),
                    "time": cards.clean(f"{b['time_start'] or ''}–{b['time_end'] or ''}".strip("–"), 40),
                    "room": cards.clean(b["room_name"], 64),
                },
                actions=[
                    s.RowAction(
                        action="cancel_my_booking",
                        label=cards.txt("İptal et", "Cancel"),
                        args={"booking_id": int(b["id"])},
                        danger=True,
                    )
                ],
            )
        )
    return s.ListCard(
        id=cards.new_id(),
        action="my_bookings",
        title=cards.txt(f"Rezervasyonlarım · {len(rows)} yaklaşan", f"My bookings · {len(rows)} upcoming"),
        columns=[
            s.Column(key="date", label=cards.txt("Gün", "Day"), kind="date"),
            s.Column(key="time", label=cards.txt("Saat", "Time"), kind="time"),
            s.Column(key="room", label=cards.txt("Salon", "Room"), kind="room"),
        ],
        rows=rows[: cards.LIST_ROWS],
        total=len(rows),
        more="my_bookings",
        empty=cards.txt("Yaklaşan rezervasyonunuz yok.", "You have no upcoming bookings."),
    )
