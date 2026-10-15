"""Phase 19 moderation tab API (P19-M1..M3; docs/design/v2/phase19-moderation.md §14, review §3d).

Permissions:

* reads (people, history, matchings, diff): ``planning.view`` sees every request; a user without it sees only
  the requests of the instructor record linked to their account (``Instructor.user_id``; academician needs Q11)
  and gets 403 when no record is linked;
* priorities, re-solves and draft edits: ``planning.edit``; a pin over the rooms' capacity also needs
  ``planning.admin`` and a reason (Q8). Publishing stays ``POST /runs/{id}/activate`` with its guard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentAccess, CurrentUser, Planner, Viewer
from app.core.db import get_session_factory
from app.models import ScheduleRun, Term
from app.schemas.moderation import MatchingActionIn, PriorityIn, ResolveIn, SubjectPriorityIn
from app.services import moderation as mod
from app.services.bookings_perms import load_access

router = APIRouter(tags=["moderation"])


def _raise(exc: mod.ModerationError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


async def _term(db: AsyncSession, term_id: int) -> Term:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    return term


async def _scope(db: AsyncSession, access: Any) -> mod.Scope:
    try:
        return await mod.visibility(db, access)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.get("/terms/{term_id}/moderation/people")
async def moderation_people(term_id: int, db: DB, access: CurrentAccess, q: str | None = None) -> dict[str, Any]:
    """Kişiler tab: per academician sections, requests, match rate, preferences, learned priors, the
    "N dönemdir karşılanmadı" badge; accessibility as yes / no only."""
    term = await _term(db, term_id)
    scope = await _scope(db, access)
    return await mod.people(db, term, scope, q)


@router.get("/moderation/people/{instructor_id}/history")
async def moderation_history(
    instructor_id: int, db: DB, access: CurrentAccess, terms: str | None = Query(default=None)
) -> dict[str, Any]:
    """The person's requests across terms (``terms``: codes or ids, comma separated; default every term)."""
    scope = await _scope(db, access)
    try:
        return await mod.history(db, instructor_id, scope, terms)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


async def _issues(db: AsyncSession, term: Term, run: ScheduleRun | None) -> dict[int, dict[str, Any]]:
    """Per request: the ``/classes`` placement status and its issues (calendar_views, the same as the class table)."""
    from app.services.calendar_views import classes

    data = await classes(db, term, kind="meetings", run=run)
    return {
        r.id: {"placement_status": r.placement_status, "issues": [i.model_dump(mode="json") for i in r.issues]}
        for r in data.items
    }


async def _findings(db: AsyncSession, run: ScheduleRun) -> tuple[dict[int, list[dict[str, Any]]], dict[str, Any]]:
    """Per request: the planner-level findings of the stored run (``planner_check``), violations and exceptions."""
    from app.services.planner_check import check_run

    res = await check_run(db, run)
    out: dict[int, list[dict[str, Any]]] = {}
    for f in res.findings:
        item = {**f.as_dict(), "violation": f.violation}
        item.pop("request_ids", None)
        for rid in f.request_ids:
            out.setdefault(int(rid), []).append(item)
    return out, res.summary()


@router.get("/terms/{term_id}/moderation/matchings")
async def moderation_matchings(
    term_id: int,
    db: DB,
    access: CurrentAccess,
    run_id: int | None = None,
    verdict: str | None = None,
    q: str | None = None,
    check: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=2000, ge=1, le=5000),
) -> dict[str, Any]:
    """Eşleşmeler tab: request -> assignment with satisfied flags (room, building, tags, day, period) and a reason.
    ``run_id`` defaults to the published run; without one the planner's definitive rooms are compared. ``check``
    adds the planner-level findings of the run (``planner_check``)."""
    from app.services.calendar_views import tr_fold

    term = await _term(db, term_id)
    scope = await _scope(db, access)
    try:
        run = await mod.run_for(db, term, run_id)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc
    _td, items = await mod.term_matchings(db, term, run, scope)
    counts = mod.counts_of(items)
    if verdict:
        wanted = {v.strip() for v in verdict.split(",") if v.strip()}
        items = [it for it in items if it["verdict"] in wanted]
    if q and q.strip():
        needle = tr_fold(q)
        items = [
            it
            for it in items
            if needle in tr_fold(it["label"])
            or needle in tr_fold(it.get("course_name") or "")
            or (scope.all and any(needle in tr_fold(i["name"]) for i in it["instructors"]))
        ]
    total = len(items)
    page = items[offset : offset + limit]
    issues = await _issues(db, term, run)
    findings: dict[int, list[dict[str, Any]]] = {}
    summary = None
    if check and run is not None:
        findings, summary = await _findings(db, run)
    for it in page:
        extra = issues.get(int(it["request_id"])) or {}
        it["placement_status"] = extra.get("placement_status")
        it["issues"] = extra.get("issues", [])
        it["findings"] = findings.get(int(it["request_id"]), []) if check and run is not None else None
    return {
        "term_id": term.id,
        "run_id": run.id if run else None,
        "source": "run" if run else "planner",
        "visibility": "all" if scope.all else "own",
        "counts": counts,
        "match_rate": mod.match_rate(counts),
        "planner_check": summary,
        "total": total,
        "offset": offset,
        "items": page,
    }


@router.get("/terms/{term_id}/moderation/matchings/{request_id}")
async def moderation_matching_detail(
    term_id: int, request_id: int, db: DB, access: CurrentAccess, run_id: int | None = None
) -> dict[str, Any]:
    """One matching with the class detail of ``calendar_views.class_detail`` (raw row, checks, run history)."""
    from app.services.calendar_views import CalendarError, class_detail

    term = await _term(db, term_id)
    scope = await _scope(db, access)
    try:
        run = await mod.run_for(db, term, run_id)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc
    td = await mod.load_term(db, term, run, request_ids=[request_id])
    if not td.meetings:
        raise HTTPException(404, "meeting request not found in this term")
    mr = td.meetings[0]
    if not scope.allows(si.instructor_id for si in mr.section.instructors):
        raise HTTPException(403, "you can see only your own requests")
    item = mod.match_one(td, mr)
    try:
        detail = await class_detail(db, term, request_id, kind="meetings", run=run)
    except CalendarError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return {**item, "detail": detail.model_dump(mode="json")}


@router.put("/moderation/sections/{section_id}/priority")
async def put_section_priority(section_id: int, body: PriorityIn, db: DB, user: Planner) -> dict[str, Any]:
    """The coordinator priority of a section's requests (higher wins a best-effort placement; audited)."""
    try:
        return await mod.set_section_priority(db, section_id, body.priority, user, body.note)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.put("/moderation/requests/{request_id}/priority")
async def put_request_priority(request_id: int, body: PriorityIn, db: DB, user: Planner) -> dict[str, Any]:
    """A request's priority override (``null``: the section's priority applies; audited)."""
    try:
        return await mod.set_request_priority(db, request_id, body.priority, user, body.note)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.put("/moderation/people/{instructor_id}/priority")
async def put_person_priority(instructor_id: int, body: SubjectPriorityIn, db: DB, user: Planner) -> dict[str, Any]:
    """A person's default priority for one term (inherited by their requests: request > section > person >
    programme; audited ``person.priority``). Coordinators and admins only (``planning.edit``)."""
    try:
        return await mod.set_subject_priority(db, "person", instructor_id, body.term_id, body.priority, user, body.note)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.put("/moderation/programs/{program_id}/priority")
async def put_program_priority(program_id: int, body: SubjectPriorityIn, db: DB, user: Planner) -> dict[str, Any]:
    """A programme's default priority for one term (audited ``program.priority``)."""
    try:
        return await mod.set_subject_priority(db, "program", program_id, body.term_id, body.priority, user, body.note)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.get("/terms/{term_id}/moderation/priorities")
async def list_subject_priorities(
    term_id: int, db: DB, _: Viewer, subject: str | None = Query(default=None, pattern="^(person|program)$")
) -> dict[str, Any]:
    """The person / programme priorities set for the term (the overview's Kişiler / Programlar lists)."""
    await _term(db, term_id)
    return {"term_id": term_id, "items": await mod.list_overrides(db, term_id, subject)}


@router.get("/moderation/me")
async def moderation_me(db: DB, user: CurrentUser) -> dict[str, Any]:
    """Who the caller is for moderation (any signed-in user): the instructor record linked to the account
    (``instructor_id``, null when none; several links are listed in ``instructor_ids``), whether they see every
    request (``planning.view``) or only their own, and the current term (readable without ``planning.view``).
    Replaces the UI's 403 probe on ``/moderation/people/0/history``."""
    return await mod.me(db, await load_access(db, user))


@router.get("/moderation/current-term")
async def moderation_current_term(db: DB, _user: CurrentUser) -> dict[str, Any]:
    """The current term for any signed-in user (``GET /terms/current`` needs ``planning.view``): id, code,
    name, kind, dates and the published course run, or 404 when there are no terms."""
    term = await mod.current_term_brief(db)
    if term is None:
        raise HTTPException(404, "no terms yet")
    return term


@router.post("/terms/{term_id}/moderation/resolve", status_code=202)
async def moderation_resolve(
    term_id: int, body: ResolveIn, db: DB, user: Planner, response: Response
) -> dict[str, Any]:
    """Re-solve after edits: a child run of ``base_run_id`` (stability, carried locks, one worker), ``repair`` on
    the neighbourhood of ``changed_request_ids`` or ``full``. Never activated. 202 with the run id (poll
    ``GET /moderation/runs/{id}/diff``), or with ``wait`` 200 and the diff."""
    from app.workers.run_jobs import check_user_limit

    term = await _term(db, term_id)
    base = await db.get(ScheduleRun, body.base_run_id)
    if base is None:
        raise HTTPException(404, "base run not found")
    await check_user_limit(db, user.id)
    try:
        child = await mod.create_resolve(
            db,
            term,
            base,
            body.changed_request_ids,
            body.mode,
            user,
            radius=body.radius,
            time_limit_s=body.time_limit_s,
            compare_to=body.compare_to,
        )
    except mod.ModerationError as exc:
        raise _raise(exc) from exc
    child_id, base_id = child.id, base.id
    if not body.wait:
        mod.enqueue_resolve(child_id)
        return {"run_id": child_id, "status": "QUEUED", "base_run_id": base_id}
    await mod.run_resolve(get_session_factory(), child_id)
    db.expire_all()
    fresh = await db.get(ScheduleRun, child_id)
    assert fresh is not None
    response.status_code = 200
    return await mod.resolve_diff(db, fresh)


@router.get("/moderation/runs/{run_id}/diff")
async def moderation_diff(run_id: int, db: DB, _: Viewer, compare_to: int | None = None) -> dict[str, Any]:
    """The re-solve preview: moved / unchanged / newly placed / unplaceable against the published run that started
    the chain (``compared_to``: published / was_published / root), or against ``compare_to``."""
    run = await db.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    try:
        return await mod.resolve_diff(db, run, compare_to)
    except mod.ModerationError as exc:
        raise _raise(exc) from exc


@router.put("/moderation/matchings/{request_id}")
async def put_matching(request_id: int, body: MatchingActionIn, db: DB, user: Planner) -> dict[str, Any]:
    """pin / prefer / unlock one class on a draft child run (never the published run); next re-solve applies it."""
    access = await load_access(db, user)
    try:
        return await mod.matching_action(
            db,
            request_id,
            run_id=body.run_id,
            action=body.action,
            actor=user,
            may_override="planning.admin" in access.perms,
            room_ids=body.room_ids,
            day=body.day,
            start_period=body.start_period,
            reason=body.reason,
        )
    except mod.ModerationError as exc:
        raise _raise(exc) from exc
