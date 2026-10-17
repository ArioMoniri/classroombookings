"""Copy a run into an unpublished draft (owner decision 2026-10-17, R1-S-37; ledger ``decisions-2026-10-17``).

An administrator's forced move on the live (published) plan never edits the live run: the move endpoints
(``api/v1/calendar.py`` bulk-move, ``api/v1/runs.py`` single move) call :func:`clone_as_draft` first and apply the
forced edit to the copy. The live plan stays exactly as published until the draft is published through the normal
publish guard (``POST /runs/{draft}/activate`` with ``confirm_forced_breaks``).

The copy keeps every placement field for field (archived rows too, so an undo token of the copy behaves like one of
the source), the run's parameters, scores, diagnosis and stats; it is never active and points at the live run through
``parent_run_id``. ``source_key`` is unique across runs, so the copy's rows carry none (a run's assignments are keyed
by id; ``source_key`` only identifies imported rows of their original run).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, ScheduleRun, User

#: the copied assignment columns (everything but the identity, the run and the cross-run unique key)
_COLUMNS = (
    "meeting_request_id",
    "exam_request_id",
    "week",
    "weeks",
    "day",
    "date",
    "start_period",
    "end_period",
    "room_ids",
    "label",
    "course_codes",
    "tags",
    "notes",
    "is_locked",
    "origin",
    "archived",
)


def _copy(value: Any) -> Any:
    return list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value


def draft_label(run: ScheduleRun) -> str:
    return f"Taslak: yayındaki plan #{run.id} için zorunlu düzenleme"[:255]


async def clone_as_draft(
    session: AsyncSession, run: ScheduleRun, *, actor: User | None, reason: str | None
) -> tuple[ScheduleRun, dict[int, int]]:
    """A new unpublished run with the same placements as ``run``; returns it and ``{source id: copy id}``.

    Flushes, does not commit (the caller applies the forced edit in the same transaction)."""
    stats = dict(run.stats or {})
    stats["forced_draft"] = {
        "live_run_id": run.id,
        "reason": (reason or "").strip(),
        "by": actor.id if actor is not None else None,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    draft = ScheduleRun(
        term_id=run.term_id,
        kind=run.kind,
        horizon=run.horizon,
        horizon_params=dict(run.horizon_params or {}),
        status=run.status,
        params=dict(run.params or {}),
        objective_value=run.objective_value,
        soft_score=run.soft_score,
        hard_score=run.hard_score,
        stats=stats,
        diagnosis=list(run.diagnosis or []),
        parent_run_id=run.id,
        prompt_text=run.prompt_text,
        label=draft_label(run),
        is_active=False,
        created_by=actor.id if actor is not None else run.created_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
    session.add(draft)
    await session.flush()
    rows = list(
        (await session.execute(select(Assignment).where(Assignment.run_id == run.id).order_by(Assignment.id))).scalars()
    )
    copies = [Assignment(run_id=draft.id, **{c: _copy(getattr(a, c)) for c in _COLUMNS}) for a in rows]
    session.add_all(copies)
    await session.flush()
    id_map = {a.id: c.id for a, c in zip(rows, copies, strict=True)}
    if (run.stats or {}).get("forced_overrides"):
        # the live run's earlier overrides name its rows: on the copy they name the copied rows, so they keep counting
        draft.stats = {
            **draft.stats,
            "forced_overrides": [_remap(o, id_map) for o in (run.stats or {}).get("forced_overrides") or []],
        }
    from app.services import audit

    await audit.record(
        session,
        "run.forced_draft",
        "schedule_run",
        draft.id,
        after={"live_run_id": run.id, "draft_run_id": draft.id, "assignments": len(copies)},
        actor=actor,
        reason=(reason or "").strip() or None,
        term_id=run.term_id,
    )
    return draft, id_map


def _remap(override: dict[str, Any], id_map: dict[int, int]) -> dict[str, Any]:
    out = dict(override)
    out["assignment_ids"] = sorted(id_map.get(int(i), int(i)) for i in override.get("assignment_ids") or [])
    out["placements"] = [
        {**p, "id": id_map.get(int(p["id"]), int(p["id"]))} for p in override.get("placements") or [] if "id" in p
    ]
    return out
