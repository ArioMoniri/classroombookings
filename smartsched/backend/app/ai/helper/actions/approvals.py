"""Read actions 6-7: ``my_requests_status`` (GET /approvals/mine) and ``approvals_inbox`` (GET /approvals/inbox).

Both call :mod:`app.services.approvals` like their routes; that service runs its lazy expiry sweep first (the same
housekeeping every approvals call does), which writes only when a request ran past its deadline. Booking notes are
never put in a card. The rejection reason in ``my_requests_status`` is text an approver wrote, so the action is marked
``taints``: a model turn that read it loses its write tools (architecture doc §2.4)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.common import day_label
from app.ai.helper.actions.registry import Args, Ctx, action
from app.services import approvals as asvc

REQUESTERS = ("book_single.create", "book_single.request", "book_recur.create", "book_recur.request")


def _when(req: dict[str, Any]) -> tuple[s.Txt, str]:
    rows = req.get("bookings") or []
    if not rows:
        return cards.txt("—"), ""
    b = rows[0]
    tr, en = day_label(date.fromisoformat(b["date"]))
    more = f" (+{len(rows) - 1})" if len(rows) > 1 else ""
    return cards.txt(tr + more, en + more), cards.clean(f"{b['time_start'] or ''}–{b['time_end'] or ''}".strip("–"))


def _status(code: str) -> s.Txt:
    return cards.txt(
        asvc.STATUS_TR.get(code, code.lower()).capitalize(), asvc.STATUS_EN.get(code, code.lower()).capitalize()
    )


class NoArgs(Args):
    pass


@action(
    name="my_requests_status",
    kind="read",
    permission=REQUESTERS,
    args=NoArgs,
    summary_tr="Taleplerim",
    summary_en="My requests",
    description="List the user's own booking requests and what the approvers decided.",
    route="GET /approvals/mine",
    card="list",
    taints=True,
)
async def my_requests_status(ctx: Ctx, _args: NoArgs) -> s.CardBase:
    items = await asvc.mine(ctx.session, ctx.access)
    rows = []
    for r in items[:20]:
        day, time_text = _when(r)
        cells: dict[str, Any] = {
            "room": cards.clean(r.get("room_name") or "", 64),
            "date": day,
            "time": time_text,
            "status": _status(r["status"]),
        }
        if r.get("reason"):
            cells["reason"] = cards.clean(r["reason"], 200)
        rows.append(
            s.Row(
                id=f"request:{r['id']}",
                cells=cells,
                actions=[
                    s.RowAction(
                        action="withdraw_my_request",
                        label=cards.txt("Geri çek", "Withdraw"),
                        args={"request_id": int(r["id"])},
                    )
                ]
                if r["status"] == asvc.PENDING
                else [],
            )
        )
    pending = sum(1 for r in items if r["status"] == asvc.PENDING)
    return s.ListCard(
        id=cards.new_id(),
        action="my_requests_status",
        title=cards.txt(f"Taleplerim · {pending} onay bekliyor", f"My requests · {pending} waiting for approval"),
        columns=[
            s.Column(key="room", label=cards.txt("Salon", "Room"), kind="room"),
            s.Column(key="date", label=cards.txt("Gün", "Day"), kind="date"),
            s.Column(key="time", label=cards.txt("Saat", "Time"), kind="time"),
            s.Column(key="status", label=cards.txt("Durum", "Status"), kind="status"),
            s.Column(key="reason", label=cards.txt("Gerekçe", "Reason"), kind="text"),
        ],
        rows=rows[: cards.LIST_ROWS],
        total=len(items),
        more="my_requests",
        empty=cards.txt("Talebiniz yok.", "You have no requests."),
    )


@action(
    name="approvals_inbox",
    kind="read",
    permission=(asvc.DECIDE,),
    args=NoArgs,
    summary_tr="Bekleyen talepler",
    summary_en="Pending requests",
    description="List the booking requests waiting for this approver, with approve / reject buttons.",
    route="GET /approvals/inbox",
    card="list",
)
async def approvals_inbox(ctx: Ctx, _args: NoArgs) -> s.CardBase:
    items = await asvc.inbox(ctx.session, ctx.access, "open")
    rows = []
    for r in items[:20]:
        day, time_text = _when(r)
        rows.append(
            s.Row(
                id=f"request:{r['id']}",
                cells={
                    "room": cards.clean(r.get("room_name") or "", 64),
                    "date": day,
                    "time": time_text,
                    "who": cards.clean(r.get("requester_name") or "", 80),
                },
                actions=[
                    s.RowAction(
                        action="decide_approval",
                        label=cards.txt("Onayla", "Approve"),
                        args={"request_id": int(r["id"]), "decision": "approve"},
                    ),
                    s.RowAction(
                        action="decide_approval",
                        label=cards.txt("Reddet…", "Reject…"),
                        args={"request_id": int(r["id"]), "decision": "reject"},
                        danger=True,
                    ),
                ],
            )
        )
    return s.ListCard(
        id=cards.new_id(),
        action="approvals_inbox",
        title=cards.txt(f"Bekleyen talepler · {len(items)}", f"Pending requests · {len(items)}"),
        columns=[
            s.Column(key="room", label=cards.txt("Salon", "Room"), kind="room"),
            s.Column(key="date", label=cards.txt("Gün", "Day"), kind="date"),
            s.Column(key="time", label=cards.txt("Saat", "Time"), kind="time"),
            s.Column(key="who", label=cards.txt("Talep eden", "Requested by"), kind="person"),
        ],
        rows=rows[: cards.LIST_ROWS],
        total=len(items),
        more="approvals",
        empty=cards.txt("Bekleyen talep yok.", "No requests are waiting."),
    )
