"""Outbox dispatcher of the integrations (calendar push connectors, outgoing webhooks).

Request handlers never call a provider or a webhook URL. The services write durable outbox rows
(``calendar_sync_jobs``, ``webhook_deliveries``, ``notification_outbox`` e-mails) inside the transaction of the
change; after the commit
:func:`kick_after_commit` schedules :func:`drain` on a dedicated :class:`app.workers.queue.JobQueue` (one slot, so
a long CP-SAT solve never delays a calendar update). Rows are claimed with a conditional UPDATE (``PENDING`` ->
``RUNNING`` with a lease), so several processes can drain the same tables. Failed attempts back off 1 min, 5 min,
30 min, 2 h, 6 h, then the row is ``FAILED``; the drain re-arms a timer for the next due row and the app start
(:func:`on_startup`) picks up whatever a previous process left.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, event, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.integrations import PENDING, RUNNING
from app.workers.queue import JobQueue

log = logging.getLogger(__name__)

KEY = "integrations:drain"
#: seconds before attempt 2, 3, ... (attempt 1 is immediate); after the last one the row is FAILED
BACKOFF_S: tuple[int, ...] = (60, 300, 1800, 7200, 21600)
MAX_ATTEMPTS = len(BACKOFF_S) + 1
LEASE = timedelta(minutes=5)
#: the timer re-checks at least this often while rows wait (a lost wake-up costs at most this much)
MAX_TIMER_S = 300.0

Drainer = Callable[[datetime, int], Awaitable[int]]

_queue: JobQueue | None = None
_again = False
_timer: asyncio.TimerHandle | None = None


def _get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue(max_concurrency=1)
    return _queue


def next_attempt(attempts: int, now: datetime) -> datetime | None:
    """When to try again after ``attempts`` failed attempts; ``None`` = give up."""
    if attempts >= MAX_ATTEMPTS:
        return None
    return now + timedelta(seconds=BACKOFF_S[attempts - 1])


def due(model: Any, now: datetime) -> Select[Any]:
    """Rows ready to run: PENDING and due, or RUNNING with an expired lease (a crashed worker)."""
    return select(model.id).where(
        or_(
            and_(model.status == PENDING, model.next_attempt_at <= now),
            and_(model.status == RUNNING, model.locked_until < now),
        )
    )


async def claim(session: AsyncSession, model: Any, row_id: int, now: datetime) -> bool:
    res: Any = await session.execute(
        update(model)
        .where(
            model.id == row_id,
            or_(model.status == PENDING, and_(model.status == RUNNING, model.locked_until < now)),
        )
        .values(status=RUNNING, locked_until=now + LEASE)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return bool(res.rowcount == 1)


def _drainers() -> list[Drainer]:
    from app.services import bookings_notify, calendar_connectors, webhooks
    from app.services.channels import outbox as channels_outbox

    return [calendar_connectors.drain_due, webhooks.drain_due, bookings_notify.drain_due, channels_outbox.drain_due]


def _next_due_fns() -> list[Callable[[], Awaitable[datetime | None]]]:
    from app.services import bookings_notify, calendar_connectors, webhooks
    from app.services.channels import outbox as channels_outbox

    return [calendar_connectors.next_due, webhooks.next_due, bookings_notify.next_due, channels_outbox.next_due]


async def drain(now: datetime | None = None, limit: int = 200) -> int:
    """Process every due row once (tests pass a future ``now`` to run retries)."""
    total = 0
    for fn in _drainers():
        try:
            total += await fn(now or utcnow(), limit)
        except Exception:  # noqa: BLE001 - one broken integration must not stop the other
            log.exception("integration drain %s failed", fn)
    return total


async def _job(_progress: Any) -> dict[str, Any]:
    global _again
    processed = 0
    for _ in range(50):  # bounded: new rows committed meanwhile set _again
        _again = False
        processed += await drain()
        if not _again:
            break
    await _arm_timer()
    return {"processed": processed}


async def _arm_timer() -> None:
    soonest: datetime | None = None
    for fn in _next_due_fns():
        try:
            at = await fn()
        except Exception:  # noqa: BLE001
            log.debug("next_due failed", exc_info=True)
            continue
        if at is not None and (soonest is None or at < soonest):
            soonest = at
    if soonest is not None:
        delay = max(1.0, min(MAX_TIMER_S, (soonest - utcnow()).total_seconds()))
        schedule_drain(delay)


def schedule_drain(delay: float = 0.0) -> None:
    """Run :func:`drain` on the integrations queue now (or after ``delay`` seconds). No-op without a loop."""
    global _again, _timer
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if delay > 0:
        if _timer is not None and not _timer.cancelled() and _timer.when() <= loop.time() + delay:
            return
        if _timer is not None:
            _timer.cancel()
        _timer = loop.call_later(delay, schedule_drain)
        return
    q = _get_queue()
    st = q.state(KEY)
    if st is not None and st.status in ("QUEUED", "RUNNING"):
        _again = True
        return
    q.enqueue(KEY, _job)


def kick_after_commit(session: AsyncSession) -> None:
    """Schedule a drain once the caller's transaction commits (the rows are invisible to other sessions before)."""
    sync = session.sync_session
    if sync.info.get(KEY):
        return
    sync.info[KEY] = True

    def _after_commit(s: Any) -> None:
        s.info.pop(KEY, None)
        schedule_drain()

    def _after_rollback(s: Any, _previous_transaction: Any = None) -> None:  # after_soft_rollback passes both
        s.info.pop(KEY, None)

    event.listen(sync, "after_commit", _after_commit, once=True)
    event.listen(sync, "after_soft_rollback", _after_rollback, once=True)


def run_detached(fn: Callable[[], Awaitable[None]], key: str) -> None:
    """Fire-and-forget work on the integrations queue (e.g. revoking a token at the provider after disconnect)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    async def job(_progress: Any) -> None:
        await fn()

    _get_queue().enqueue(key, job)


async def wait_idle(timeout: float = 60.0) -> None:
    """Until no drain is queued or running (a drain may queue the next one)."""
    q = _get_queue()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while q._tasks and loop.time() < deadline:
        await q.wait_idle(max(0.1, deadline - loop.time()))


async def on_startup() -> None:
    """Pick up rows a previous process left (pending retries, expired leases); start the nightly calendar repair
    (not in tests: they call :func:`nightly_once`)."""
    schedule_drain()
    from app.core.config import get_settings

    if get_settings().environment != "test":
        start_nightly()


#: CAL-06: the nightly repair of the pushed calendars runs at this Istanbul time
NIGHTLY_AT = (3, 30)
_nightly_task: asyncio.Task[None] | None = None


def seconds_until_nightly(now_utc: datetime) -> float:
    """Seconds from ``now_utc`` (naive UTC) to the next 03:30 Europe/Istanbul."""
    from datetime import UTC
    from zoneinfo import ZoneInfo

    local = now_utc.replace(tzinfo=UTC).astimezone(ZoneInfo("Europe/Istanbul"))
    target = local.replace(hour=NIGHTLY_AT[0], minute=NIGHTLY_AT[1], second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return (target - local).total_seconds()


async def nightly_once() -> int:
    """Queue one ``nightly`` job per pushed calendar and record when it ran (admin status)."""
    from app.core.db import get_session_factory
    from app.services import calendar_connectors
    from app.services.bookings_settings import set_group

    async with get_session_factory()() as session:
        queued = await calendar_connectors.queue_nightly(session)
        await set_group(
            session,
            "integrations",
            {
                "nightly_reconcile_at": {"at": utcnow().isoformat(timespec="seconds") + "Z", "queued": queued}
            },  # fmt: skip
        )
        await session.commit()
    schedule_drain()
    return queued


async def _nightly_loop() -> None:
    while True:
        await asyncio.sleep(seconds_until_nightly(utcnow()))
        try:
            await nightly_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing night must not stop the next one
            log.exception("nightly calendar repair failed")


def start_nightly() -> None:
    global _nightly_task
    if _nightly_task is None or _nightly_task.done():
        _nightly_task = asyncio.create_task(_nightly_loop(), name="calendar-nightly")


async def shutdown() -> None:
    global _queue, _timer, _nightly_task
    if _nightly_task is not None:
        _nightly_task.cancel()
        _nightly_task = None
    if _timer is not None:
        _timer.cancel()
        _timer = None
    if _queue is not None:
        await _queue.shutdown()
        _queue = None


# --------------------------------------------------------------------------------------------------
# The one subscriber on app.services.events.publish_event (booking / series / approval mutations)
# --------------------------------------------------------------------------------------------------


async def affected_booking_ids(session: AsyncSession, ev: Any) -> list[int]:
    """Bookings touched by a domain event: its booking items, ``payload.booking_ids``, a series' bookings and an
    approval request's booking(s)."""
    from app.models import ApprovalRequest, Booking

    ids: set[int] = set(ev.booking_ids)
    for raw in (ev.payload or {}).get("booking_ids") or []:
        if str(raw).isdigit():
            ids.add(int(raw))
    series_ids: set[int] = set()
    entity = str(ev.entity_id) if ev.entity_id is not None else ""
    if ev.entity_type in ("booking_series", "series") and entity.isdigit():
        series_ids.add(int(entity))
    if ev.entity_type == "approval_request" and entity.isdigit():
        req = await session.get(ApprovalRequest, int(entity))
        if req is not None:
            if req.booking_id:
                ids.add(req.booking_id)
            if req.series_id:
                series_ids.add(req.series_id)
    if series_ids:
        q = select(Booking.id).where(Booking.series_id.in_(sorted(series_ids)))
        ids |= set((await session.execute(q)).scalars())
    return sorted(ids)


#: CAL-06: published-plan changes that reach the pushed class calendars
CLASS_ACTIONS = ("run.activate", "run.delete", "assignment.move", "assignment.bulk_move", "assignment.restore")


async def affected_class_targets(session: AsyncSession, ev: Any) -> tuple[set[int], set[int]] | None:
    """Who a move touches: the users linked to the teachers of the moved rows' sections and the rows' departments.
    ``None`` = everybody with a class scope (a publish, a deletion, or rows that cannot be traced); ``(set(), set())``
    = nobody (the rows belong to a draft run, which never reaches a calendar)."""
    from app.importers import normalize as n
    from app.models import Assignment, Course, Instructor, MeetingRequest, ScheduleRun, Section, SectionInstructor

    if not str(ev.action).startswith("assignment."):
        return None
    ids = {int(i[0]) for i in ev.items if str(i[0]).isdigit()}
    for _id, _before, after in ev.items:
        if isinstance(after, dict) and str(after.get("split_into") or "").isdigit():
            ids.add(int(after["split_into"]))
    if not ids:
        return None
    rows = list((await session.execute(select(Assignment).where(Assignment.id.in_(sorted(ids))))).scalars())
    if not rows:
        return None
    runs = {
        r.id: r
        for r in (
            await session.execute(select(ScheduleRun).where(ScheduleRun.id.in_({a.run_id for a in rows})))
        ).scalars()
    }
    rows = [a for a in rows if (run := runs.get(a.run_id)) is not None and run.is_active and run.kind == "COURSE"]
    if not rows:
        return set(), set()
    term_ids = {runs[a.run_id].term_id for a in rows}
    sections: set[int] = set()
    mr_ids = {a.meeting_request_id for a in rows if a.meeting_request_id}
    if mr_ids:
        q = select(MeetingRequest.section_id).where(MeetingRequest.id.in_(sorted(mr_ids)))
        sections |= {int(x) for x in (await session.execute(q)).scalars()}
    keys = {n.course_key(c) for a in rows if not a.meeting_request_id for c in (a.course_codes or []) if c}
    if keys:
        q2 = (
            select(Section.id, Course.code)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id.in_(sorted(term_ids)))
        )
        sections |= {int(sid) for sid, code in (await session.execute(q2)).all() if n.course_key(code) in keys}
    if not sections:
        return None
    programs = {
        int(p)
        for p in (await session.execute(select(Section.program_id).where(Section.id.in_(sorted(sections))))).scalars()
        if p is not None
    }
    users = {
        int(u)
        for u in (
            await session.execute(
                select(Instructor.user_id)
                .join(SectionInstructor, SectionInstructor.instructor_id == Instructor.id)
                .where(SectionInstructor.section_id.in_(sorted(sections)), Instructor.user_id.is_not(None))
            )
        ).scalars()
        if u is not None
    }
    return users, programs


#: CAL-13: invigilation-plan changes that reach the pushed "Sınav görevlerim" calendars
DUTY_ACTIONS = ("invigilation.activate", "invigilation.reassign", "invigilation.add_duty")


async def moves_published_exams(session: AsyncSession, ev: Any) -> bool:
    """A move of rows of a published EXAM run (the own exams of ``my_duties``)."""
    from app.models import Assignment, ScheduleRun

    if not str(ev.action).startswith("assignment."):
        return False
    ids = {int(i[0]) for i in ev.items if str(i[0]).isdigit()}
    if not ids:
        return False
    q = (
        select(Assignment.id)
        .join(ScheduleRun, ScheduleRun.id == Assignment.run_id)
        .where(Assignment.id.in_(sorted(ids)), ScheduleRun.is_active.is_(True), ScheduleRun.kind == "EXAM")
        .limit(1)
    )
    return (await session.execute(q)).first() is not None


async def on_invigilation_event(session: AsyncSession, ev: Any) -> None:
    """CAL-13: a published or edited invigilation plan queues the class reconcile of every ``my_duties`` push."""
    from app.services import calendar_connectors

    if ev.action in DUTY_ACTIONS and (ev.payload or {}).get("active", True):
        await calendar_connectors.queue_classes(session, duties_only=True)


async def on_domain_event(session: AsyncSession, ev: Any) -> None:
    from app.services import calendar_connectors, webhooks

    if ev.action in CLASS_ACTIONS and await moves_published_exams(session, ev):
        await calendar_connectors.queue_classes(session, duties_only=True)
    if ev.action in CLASS_ACTIONS:
        targets = await affected_class_targets(session, ev)
        if targets is None:
            await calendar_connectors.queue_classes(session)
        elif targets[0] or targets[1]:
            await calendar_connectors.queue_classes(session, user_ids=targets[0], programs=targets[1])
        if not ev.action.startswith("run.activate"):
            return  # moves are not booking events (run.activate also re-checks bookings, as before)
    ids = await affected_booking_ids(session, ev)
    await calendar_connectors.queue_bookings(session, ids)
    await webhooks.on_event(session, ev, ids)


def register() -> None:
    from app.services import events

    for pattern in ("booking.*", "series.*", "approval.*", "run.activate", "run.delete", "assignment.*"):
        events.subscribe(pattern, on_domain_event)
    events.subscribe("invigilation.*", on_invigilation_event)
