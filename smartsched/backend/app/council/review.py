"""Human review: low-confidence items from the blackboard, decisions, and deterministic re-runs.

Item kinds (``blocking`` items must be decided before commit):

| kind | from | blocking | decisions |
|---|---|---|---|
| ``classification`` | structure: sheet kind below the threshold | yes | accept, edit {kind} |
| ``mapping`` | structure: a column below the threshold / unmapped candidate | yes | accept, reject, edit {field} |
| ``merge`` | reconciler: near-duplicate rooms or instructors | yes | accept (same entity), reject (different) |
| ``issue`` | critic: errors and warnings | no | accept (acknowledged) |
| ``rule`` | rule miner: a constraint proposal | no | accept (commit it), reject, edit {hardness, weight} |
| ``rule_text`` | rule-like text with no model available | no | accept (acknowledged) |
| ``plan`` | planner: one term group | no | accept, edit {code, name, kind, week_count, start_date, year} |
| ``file`` | a file that could not be read | no | accept (acknowledged) |
| ``ai_rows`` | rows read by the AI model (:mod:`app.council.airows`) | yes | per row via ``/rows/decisions`` |

Decisions are stored as ``review`` artifacts (append-only; the latest decision per item wins) and each post is
one ``council.review`` audit event. A mapping or classification edit re-runs extract -> reconcile -> planner ->
critic for the job deterministically (no model calls) on the job queue (the job is ``RUNNING`` meanwhile).
Decisions are also remembered for the next upload with the same file signature (:mod:`app.council.memory`).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import safe_files
from app.council import critic, planner, reconcile, storage
from app.council.lexicon import FIELDS
from app.council.structure import KIND_LABELS, KINDS, SheetAnalysis
from app.models import CouncilJob, User
from app.models.base import utcnow
from app.services.events import publish_event

BLOCKING = {"classification", "mapping", "merge"}
#: every item kind :func:`build_items` emits (the frontend's REVIEW_KINDS must list each: a contract test)
ITEM_KINDS = ("classification", "mapping", "merge", "issue", "rule", "rule_text", "plan", "file", "ai_rows")
ACTIONS = {"accept", "reject", "edit"}


async def decisions(session: AsyncSession, job_id: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for art in await storage.all_of(session, job_id, "review"):
        out.update(art.payload.get("decisions", {}))
    return out


def _threshold(job: CouncilJob) -> float:
    from app.core.config import get_settings

    return float((job.settings or {}).get("review_threshold") or get_settings().council_review_threshold)


async def build_items(session: AsyncSession, job: CouncilJob) -> list[dict[str, Any]]:
    thr = _threshold(job)
    decided = await decisions(session, job.id)
    items: list[dict[str, Any]] = []

    def add(item_id: str, kind: str, title: str, *, legacy_id: str | None = None, **extra: Any) -> None:
        items.append(
            {
                "id": item_id,
                "kind": kind,
                "title": title,
                "blocking": kind in BLOCKING,
                "decision": decided.get(item_id) or (decided.get(legacy_id) if legacy_id else None),
                **extra,
            }
        )

    names = {f["index"]: f["filename"] for f in job.files}
    for f in job.files:
        if f.get("status") == "FAILED" or f.get("route") in ("error", "vision", "ai-off"):
            add(
                f"file:{f['index']}",
                "file",
                f"{f['filename']}: {f.get('message') or 'could not be read'}",
                file_index=f["index"],
                confidence=0.0,
            )
    for fi, art in (await storage.latest_by_file(session, job.id, "structure")).items():
        for a_dict in art.payload.get("analyses", []):
            a = SheetAnalysis.from_dict(a_dict)
            if a.grid < 0:
                continue
            where = f"{names.get(fi, fi)} / {a.name}"
            if a.confidence < thr:
                add(
                    f"cls:{fi}:{a.grid}",
                    "classification",
                    f"{where}: is this a {KIND_LABELS[a.kind]}?",
                    file_index=fi,
                    grid=a.grid,
                    confidence=a.confidence,
                    current={"kind": a.kind},
                    options=list(KINDS),
                    notes=a.notes,
                )
            if a.kind == "timetable_grid":
                continue
            for c in a.columns:
                low = c.field is not None and c.confidence < thr
                missed = c.field is None and any(float(s) >= 0.5 for _, s in c.alternatives)
                if low or missed:
                    add(
                        f"map:{fi}:{a.grid}:{c.index}",
                        "mapping",
                        f"{where}: column '{c.header or c.index}' -> {c.field or '(not used)'}?",
                        file_index=fi,
                        grid=a.grid,
                        column=c.index,
                        confidence=c.confidence,
                        current={"field": c.field},
                        alternatives=c.alternatives,
                        samples=c.samples,
                        options=["", *FIELDS],
                        source=c.source,
                    )
    dataset = await storage.latest(session, job.id, "dataset")
    if dataset is not None:
        from app.council.memory import legacy_merge_item_id, merge_item_id

        for m in dataset.payload.get("merges", []):
            add(
                merge_item_id(m),  # opaque: the names stay inside `current` (planners only, T-R1-22)
                "merge",
                f"Same {m['kind']}? '{m['a']}' and '{m['b']}'",
                confidence=m["score"],
                current=m,
                legacy_id=legacy_merge_item_id(m),
            )
    issues = await storage.latest(session, job.id, "issues")
    if issues is not None:
        for n, iss in enumerate(issues.payload.get("issues", [])):
            if iss["severity"] in ("error", "warning"):
                add(
                    f"issue:{n}:{iss['code']}",
                    "issue",
                    iss["message"],
                    severity=iss["severity"],
                    code=iss["code"],
                    sources=iss.get("sources", [])[:5],
                    count=len(iss.get("records", [])),
                )
    for fi, art in (await storage.latest_by_file(session, job.id, "rules")).items():
        for n, p in enumerate(art.payload.get("proposals", [])):
            add(
                f"rule:{fi}:{n}",
                "rule",
                p.get("title") or p.get("nl_text") or p.get("kind", "rule"),
                file_index=fi,
                current={
                    "kind": p.get("kind"),
                    "hardness": p.get("hardness"),
                    "weight": p.get("weight"),
                    "nl_text": p.get("nl_text"),
                },
                source=p.get("_source"),
                text=p.get("_text"),
                confidence=p.get("confidence"),
            )
        pending = art.payload.get("pending", [])
        if pending:
            add(
                f"rule_text:{fi}",
                "rule_text",
                f"{names.get(fi, fi)}: {len(pending)} rule-like text(s) need the AI model to become constraints",
                file_index=fi,
                texts=pending[:30],
            )
    plan = await storage.latest(session, job.id, "plan")
    if plan is not None:
        for g_i, g in enumerate(plan.payload.get("groups", [])):
            files = ", ".join(str(names.get(i, i)) for i in g["files"])
            add(
                f"plan:{g_i}",
                "plan",
                f"Term {g['code']} ({g['kind']}, {g['week_count']} weeks) from {files}",
                current={k: g[k] for k in ("code", "name", "kind", "week_count", "start_date", "year")},
                confidence=g["confidence"],
                files=g["files"],
                evidence=g.get("evidence", []),
            )
    # rows read by the AI model: one blocking item per file until a person decided each row (P19-A2)
    from app.council import airows

    items.extend(await airows.review_items(session, job, decided))
    # intake memory: remembered decisions of earlier jobs as visible suggestions (never applied by themselves)
    from app.council import memory

    for extra in await memory.recall(session, job, items):
        extra["decision"] = decided.get(extra["id"])
        extra["options"] = ["", *FIELDS]
        items.append(extra)
    return items


def effective_plan(plan: dict[str, Any], decided: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = {**plan, "groups": [dict(g) for g in plan.get("groups", [])]}
    for g_i, g in enumerate(out["groups"]):
        d = decided.get(f"plan:{g_i}")
        if d and d.get("action") == "edit" and isinstance(d.get("value"), dict):
            for k in ("code", "name", "kind", "week_count", "start_date", "year"):
                if k in d["value"] and d["value"][k] not in (None, ""):
                    g[k] = d["value"][k]
    return out


async def rerun_deterministic(session: AsyncSession, job: CouncilJob, file_indexes: set[int]) -> None:
    """Re-extract ``file_indexes`` with the reviewed structure, then reconcile, plan and critic again."""
    from app.council.extract import extract, rule_texts
    from app.council.render import render_file

    decided = await decisions(session, job.id)
    structures = await storage.latest_by_file(session, job.id, "structure")
    for fi in sorted(file_indexes):
        art = structures.get(fi)
        entry = next((f for f in job.files if f["index"] == fi), None)
        if art is None or entry is None or not art.payload.get("analyses"):
            continue
        analyses = [SheetAnalysis.from_dict(a) for a in art.payload["analyses"]]
        for a in analyses:
            d = decided.get(f"cls:{fi}:{a.grid}")
            if d and d.get("action") == "edit" and (d.get("value") or {}).get("kind") in KINDS:
                a.kind, a.confidence, a.source = d["value"]["kind"], 1.0, "review"
            elif d and d.get("action") == "accept":
                a.confidence = max(a.confidence, 1.0)
            for c in a.columns:
                cd = decided.get(f"map:{fi}:{a.grid}:{c.index}")
                if not cd:
                    continue
                if cd.get("action") == "reject":
                    c.field, c.source = None, "review"
                elif cd.get("action") == "edit":
                    field = (cd.get("value") or {}).get("field") or None
                    c.field, c.source = (field if field in FIELDS else None), "review"
                c.confidence = 1.0
        await storage.add_artifact(
            session,
            job.id,
            "structure",
            {**art.payload, "analyses": [a.to_dict() for a in analyses]},
            file_index=fi,
            confidence=min((a.confidence for a in analyses if a.grid >= 0), default=None),
        )
        path = storage.file_path(job.id, entry)
        rendered = await safe_files.run_isolated(render_file, path.read_bytes(), entry["filename"])
        records = await asyncio.to_thread(extract, rendered, analyses, year_hint=job.year_hint)
        texts = rule_texts(rendered, analyses, records)
        counts = dict(Counter(r["type"] for r in records))
        await storage.add_artifact(
            session,
            job.id,
            "records",
            {"records": records, "counts": counts, "warnings": [], "route": "general (reviewed)"},
            file_index=fi,
        )
        await storage.add_artifact(session, job.id, "rule_texts", {"texts": texts}, file_index=fi)
        files = [dict(f) for f in job.files]
        for f in files:
            if f["index"] == fi:
                f["counts"] = counts
        job.files = files
    records_all = await storage.records_by_file(session, job)
    dataset = reconcile.reconcile([(f["index"], f["filename"], records_all.get(f["index"], [])) for f in job.files])
    await storage.add_artifact(session, job.id, "dataset", dataset)
    old_plan = await storage.latest(session, job.id, "plan")
    meta = [{"index": f["index"], "filename": f["filename"], "sheets": []} for f in job.files]
    axes: list[list[list[str]]] = []
    for art in structures.values():
        for a in art.payload.get("analyses", []):
            axes.extend(ax.get("slots", []) for ax in a.get("axes", []))
        if art.payload.get("shape") == "weekly-grid":
            axes.append([[p["start"], p["end"]] for p in planner.DEFAULT_GRID])
    new_plan = planner.plan(meta, records_all, axes, lang=job.lang)
    if old_plan is not None:  # sheet names are not re-read here; keep the earlier week lists per group code
        old = {g["code"]: g for g in old_plan.payload.get("groups", [])}
        for g in new_plan["groups"]:
            if g["code"] in old and not g["weeks"]:
                g["weeks"] = old[g["code"]]["weeks"]
    await storage.add_artifact(session, job.id, "plan", new_plan)
    job.plan = new_plan
    prev = await storage.latest(session, job.id, "issues")
    keep = [i for i in (prev.payload.get("issues", []) if prev else []) if i["code"] == "judge_mismatch"]
    issues = critic.check(dataset, records_all, new_plan) + keep
    await storage.add_artifact(session, job.id, "issues", {"issues": issues})


async def _status_after_review(session: AsyncSession, job: CouncilJob, before: str) -> list[dict[str, Any]]:
    items = await build_items(session, job)
    blocking = [it for it in items if it["blocking"] and it["decision"] is None]
    if before in ("REVIEW", "READY"):
        job.status = "REVIEW" if blocking else "READY"
    else:
        job.status = before
    job.summary = {**(job.summary or {}), "review_items": len(items), "blocking_items": len(blocking)}
    return blocking


async def apply_decisions(
    session: AsyncSession, job: CouncilJob, items_in: list[dict[str, Any]], actor: User | None
) -> dict[str, Any]:
    """Store the decisions (one ``council.review`` audit event) and, when a mapping or classification changed,
    queue the deterministic re-run of the affected files (:func:`enqueue_rerun`): the job is ``RUNNING`` until
    it has finished (commit is refused meanwhile), then ``REVIEW`` / ``READY`` again."""
    user_id = actor.id if actor is not None else None
    known = {it["id"]: it for it in await build_items(session, job)}
    stored: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for d in items_in:
        item = known.get(d["id"])
        if item is None:
            errors.append(f"unknown review item {d['id']}")
            continue
        if d["action"] not in ACTIONS:
            errors.append(f"{d['id']}: unknown action {d['action']}")
            continue
        value = d.get("value") if isinstance(d.get("value"), dict) else None
        if item["kind"] == "ai_rows":
            errors.append(f"{d['id']}: decide the rows themselves (POST /council/jobs/{{id}}/rows/decisions)")
            continue
        if d["action"] == "edit":
            if item["kind"] == "mapping" and (value is None or (value.get("field") or "") not in ("", *FIELDS)):
                errors.append(f"{d['id']}: edit needs value.field from the field list")
                continue
            if item["kind"] == "classification" and (value is None or value.get("kind") not in KINDS):
                errors.append(f"{d['id']}: edit needs value.kind from the kind list")
                continue
            if item["kind"] == "rule" and value is not None:
                if value.get("hardness") not in (None, "hard", "soft"):
                    errors.append(f"{d['id']}: hardness must be hard or soft")
                    continue
                if value.get("weight") is not None and not 1 <= int(value["weight"]) <= 10:
                    errors.append(f"{d['id']}: weight must be 1..10")
                    continue
            if item["kind"] in ("merge", "issue", "rule_text", "file", "ai_rows"):
                errors.append(f"{d['id']}: {item['kind']} items can only be accepted or rejected")
                continue
        stored[d["id"]] = {"action": d["action"], "value": value, "by": user_id, "at": utcnow().isoformat()}
    if stored:
        await storage.add_artifact(session, job.id, "review", {"decisions": stored})
        await session.flush()
        # one audit event per review post: which items, which action (values are field / kind names, no content)
        await publish_event(
            session,
            "council.review",
            "council_job",
            job.id,
            after={
                "decisions": {
                    i: {
                        "kind": known[i]["kind"],
                        "action": d["action"],
                        **(
                            {"value": d["value"]}
                            if d["value"] and known[i]["kind"] in ("mapping", "classification", "rule", "plan")
                            else {}
                        ),
                    }
                    for i, d in stored.items()
                },
                "count": len(stored),
            },
            actor=actor,
        )
        from app.council import memory

        await memory.remember(session, job, {i: (known[i], d) for i, d in stored.items()}, actor)
    rerun = {
        known[i]["file_index"]
        for i, d in stored.items()
        if known[i]["kind"] in ("mapping", "classification") and d["action"] in ("edit", "reject")
    }
    before = job.status
    if rerun:
        job.settings = {**(job.settings or {}), "status_before_rerun": before}
        job.status = "RUNNING"
        items = await build_items(session, job)
        blocking = [it for it in items if it["blocking"] and it["decision"] is None]
    else:
        blocking = await _status_after_review(session, job, before)
    await session.commit()
    if rerun:
        enqueue_rerun(job.id, sorted(rerun))
    return {
        "saved": len(stored),
        "errors": errors,
        "rerun_files": sorted(rerun),
        "rerun_queued": bool(rerun),
        "blocking": len(blocking),
    }


async def run_rerun(job_id: int, files: list[int]) -> dict[str, Any]:
    """Queue body of a review re-run (deterministic, no model calls)."""
    from app.core.db import get_session_factory

    async with get_session_factory()() as s:
        job = await s.get(CouncilJob, job_id)
        if job is None:
            raise ValueError(f"council job {job_id} not found")
        await rerun_deterministic(s, job, set(files))
        before = str((job.settings or {}).get("status_before_rerun") or "REVIEW")
        blocking = await _status_after_review(s, job, before)
        await s.commit()
        return {"status": job.status, "blocking": len(blocking), "files": files}


def enqueue_rerun(job_id: int, files: list[int]) -> None:
    from app.core.db import get_session_factory
    from app.workers.queue import JobState, get_queue

    async def body(progress: Any) -> dict[str, Any]:
        if progress:
            progress(f"re-reading {len(files)} file(s) with the reviewed mapping", 10)
        return await run_rerun(job_id, files)

    async def on_status(st: JobState) -> None:
        if st.status != "FAILED":
            return
        async with get_session_factory()() as s:
            job = await s.get(CouncilJob, job_id)
            if job is not None and job.status == "RUNNING":
                job.status = str((job.settings or {}).get("status_before_rerun") or "REVIEW")
                job.error = f"review re-run failed: {(st.error or 'failed')[:1900]}"
                await s.commit()

    get_queue().enqueue(f"council-review:{job_id}:{utcnow().timestamp():.0f}", body, on_status=on_status)


__all__ = [
    "BLOCKING",
    "ITEM_KINDS",
    "apply_decisions",
    "build_items",
    "decisions",
    "effective_plan",
    "enqueue_rerun",
    "rerun_deterministic",
    "run_rerun",
]
