"""Commit dry-run (P19-I4): the real commit, inside one transaction that is rolled back.

``POST /council/jobs/{id}/commit {"dry_run": true}`` runs :func:`app.council.commit.commit` (the same
importers and the same writer) in a session whose ``commit()`` only flushes, records every row the writer
creates or changes (SQLAlchemy flush events), and rolls the transaction back. Nothing is written: no term,
no rooms, no requests, no audit event, the job keeps its status.

The answer has, per entity (``meeting_requests``, ``sections``, ``rooms``, ``blocks``, ...):

* ``create`` / ``update``: rows inserted / rows whose content changed (bookkeeping columns alone do not count);
* ``unchanged``: rows the file matched that are identical (the importers' and the writer's own counts);
* ``conflict``: rows where a planner edit (studio, kept in ``imported_snapshots``) and the file disagree. With
  ``on_conflict="keep"`` (default) the planner's value stays; ``"take"`` writes the file's value. Either way
  the conflict is listed with both values.

``rows`` holds the row diffs (``from`` -> ``to`` per field, the planner's imported value when there is a
snapshot), capped at :data:`MAX_ROWS`; ``rows_total`` says how many there were. The real commit records the
same counts (``result.changes``), so a dry-run and the commit that follows can be compared one to one.

``result`` keeps the commit's term, files and counts, and ``baseline_run`` (app/council/baseline.py): the run the
schedule maps would go to (``run_id``; ``null`` with ``run_created`` when a new baseline run would be made), its
create / update / unchanged / linked counts, or ``skipped`` with ``baseline.mode = skip``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

MAX_ROWS = 500
#: bookkeeping tables: never part of the diff
IGNORED = frozenset(
    {
        "council_jobs",
        "council_artifacts",
        "council_steps",
        "audit_events",
        "imported_snapshots",
        "notification_outbox",
        "settings",
        "term_locks",
        "webhook_deliveries",
        "calendar_sync_jobs",
    }
)
#: columns that change on every import without changing the content
META = frozenset({"source_row_index", "parse_warnings", "source_row", "updated_at", "created_at"})
_KEYS = ("source_key", "code", "canonical_name", "label", "full_name", "name", "key")


def plain(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat(timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    return v


def _table(obj: Any) -> str | None:
    t = getattr(obj, "__tablename__", None)
    return str(t) if t else None


def _row_key(obj: Any) -> str | None:
    for k in _KEYS:
        v = getattr(obj, k, None)
        if v not in (None, ""):
            return str(v)[:120]
    return None


class ChangeRecorder:
    """Rows created / updated through one session (flush events); net changes per row across flushes."""

    def __init__(self) -> None:
        self.created: dict[tuple[str, Any], dict[str, Any]] = {}
        self.updated: dict[tuple[str, Any], dict[str, Any]] = {}
        self._pending: list[Any] = []

    def attach(self, session: AsyncSession) -> ChangeRecorder:
        sync: Session = session.sync_session
        event.listen(sync, "before_flush", self._before)
        event.listen(sync, "after_flush", self._after)
        return self

    def detach(self, session: AsyncSession) -> None:
        sync: Session = session.sync_session
        if event.contains(sync, "before_flush", self._before):
            event.remove(sync, "before_flush", self._before)
            event.remove(sync, "after_flush", self._after)

    def _ident(self, obj: Any) -> tuple[str, Any] | None:
        table = _table(obj)
        if table is None or table in IGNORED:
            return None
        # the primary key from the instance: new rows get their identity key only after the flush finishes
        pk = tuple(inspect(obj).mapper.primary_key_from_instance(obj))
        if any(v is None for v in pk):
            return None
        return (table, pk[0] if len(pk) == 1 else pk)

    def _before(self, session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ARG002
        for obj in session.new:
            table = _table(obj)
            if table is not None and table not in IGNORED:
                self._pending.append(obj)
        for obj in session.dirty:
            key = self._ident(obj)
            if key is None or key in self.created or not session.is_modified(obj, include_collections=False):
                continue
            st = inspect(obj)
            entry = self.updated.setdefault(key, {"entity": key[0], "id": key[1], "key": _row_key(obj), "fields": {}})
            for attr in st.mapper.column_attrs:
                hist = st.attrs[attr.key].history
                if not hist.has_changes():
                    continue
                old = plain(hist.deleted[0]) if hist.deleted else None
                new = plain(hist.added[0]) if hist.added else None
                if attr.key in entry["fields"]:
                    entry["fields"][attr.key][1] = new
                else:
                    entry["fields"][attr.key] = [old, new]

    def _after(self, session: Session, flush_context: Any) -> None:  # noqa: ARG002
        for obj in self._pending:
            key = self._ident(obj)
            if key is not None and key not in self.created:
                self.created[key] = {"entity": key[0], "id": key[1], "key": _row_key(obj)}
        self._pending.clear()

    def net_updates(self) -> list[dict[str, Any]]:
        out = []
        for entry in self.updated.values():
            fields = [
                {"field": f, "from": a, "to": b} for f, (a, b) in entry["fields"].items() if a != b and f not in META
            ]
            if fields:
                out.append({**entry, "fields": fields})
        return out


def _entity_of_conflict(c: dict[str, Any]) -> str:
    return {"meeting": "meeting_requests", "section": "sections", "exam": "exam_requests"}.get(
        str(c.get("entity")), str(c.get("entity"))
    )


def summarize(rec: ChangeRecorder, result: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    """Counts per entity and the row diffs of one (dry-run or real) commit."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for key in rec.created:
        counts[key[0]]["create"] += 1
    updates = rec.net_updates()
    for u in updates:
        counts[u["entity"]]["update"] += 1
    for rep in result.get("fast_path", []):
        for entity, n in (rep.get("unchanged") or {}).items():
            counts[entity]["unchanged"] += int(n)
    for entity, n in (result.get("unchanged") or {}).items():
        counts[entity]["unchanged"] += int(n)
    conflicts = [c for rep in result.get("fast_path", []) for c in rep.get("conflicts") or []]
    conflicts += list(result.get("conflicts") or [])
    rows_in_conflict: dict[str, set[Any]] = defaultdict(set)
    for c in conflicts:
        rows_in_conflict[_entity_of_conflict(c)].add(c.get("id"))
    for entity, ids in rows_in_conflict.items():
        counts[entity]["conflict"] += len(ids)
    rows: list[dict[str, Any]] = [
        {"change": "create", "entity": c["entity"], "id": c["id"], "key": c["key"]} for c in rec.created.values()
    ]
    by_row = {(_entity_of_conflict(c), c.get("id")): c for c in conflicts}
    for u in updates:
        row = {"change": "update", **u}
        if (u["entity"], u["id"]) in by_row:
            row["change"] = "conflict"
        rows.append(row)
    seen = {(r["entity"], r["id"]) for r in rows}
    for c in conflicts:  # kept planner edits change nothing, so they are not among the updates
        k = (_entity_of_conflict(c), c.get("id"))
        if k not in seen:
            seen.add(k)
            rows.append({"change": "conflict", "entity": k[0], "id": k[1], "key": c.get("course"), "fields": []})
    for r in rows:
        if r["change"] == "conflict":
            r["conflicts"] = [
                {kk: c.get(kk) for kk in ("field", "planner", "file", "previous_import", "resolution")}
                for c in conflicts
                if (_entity_of_conflict(c), c.get("id")) == (r["entity"], r["id"])
            ]
    order = {"conflict": 0, "update": 1, "create": 2}
    rows.sort(key=lambda r: (order[r["change"]], r["entity"], str(r["id"])))
    return {
        "on_conflict": on_conflict,
        "counts": {
            e: {k: int(c.get(k, 0)) for k in ("create", "update", "unchanged", "conflict")}
            for e, c in sorted(counts.items())
        },
        "rows": rows[:MAX_ROWS],
        "rows_total": len(rows),
        "conflicts_total": len(conflicts),
    }


async def dry_run(session_factory: Any, job_id: int, **kwargs: Any) -> dict[str, Any]:
    """Run the commit of ``job_id`` with ``kwargs`` (see :func:`app.council.commit.commit`) and roll it back."""
    from app.council.commit import commit
    from app.models import CouncilJob

    async with session_factory() as s:
        rec = ChangeRecorder().attach(s)
        # every commit() of the writer and the importers becomes a flush: one transaction, rolled back below
        s.commit = s.flush
        try:
            job = await s.get(CouncilJob, job_id)
            if job is None:
                raise LookupError(f"council job {job_id} not found")
            result = await commit(s, job, recorder=rec, **kwargs)
            report = summarize(rec, result, str(kwargs.get("on_conflict") or "keep"))
            rec.detach(s)
        finally:
            await s.rollback()
    keep = (
        "term_code",
        "term_created",
        "files",
        "fast_path",
        "general",
        "notes",
        "constraints_created",
        "baseline_run",
    )
    out = {k: result.get(k) for k in keep}
    base = out.get("baseline_run")
    if isinstance(base, dict) and base.get("run_created"):
        out["baseline_run"] = {**base, "run_id": None}  # the new run's id was rolled back with the transaction
    return {"dry_run": True, **report, "result": out}


__all__ = ["MAX_ROWS", "ChangeRecorder", "dry_run", "plain", "summarize"]
