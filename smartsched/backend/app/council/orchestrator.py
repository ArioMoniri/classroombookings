"""Orchestrator of the Ingestion Council: one file at a time through the specialists, then cross-file steps.

    for each file:   intake -> (fast_path | structure -> extract)
    across files:    reconcile -> planner -> rules (per file) -> critic (+ judge)

Every step is a ``council_steps`` row: status, duration, model tokens and cost, and a message. Every
output is an append-only ``council_artifacts`` row. The job keeps running when a step fails: the file is
marked failed (intake) or the step falls back to the deterministic path, and the message says why.

Budgets: each step has a timeout (``COUNCIL_STEP_TIMEOUT_S``) and the job has a token budget
(``COUNCIL_JOB_TOKEN_BUDGET``). When the budget is spent, the remaining model calls are skipped and
the heuristic results stand ("budget exhausted" in the step message).

The model is used only when an API key is configured and ``COUNCIL_AI`` is on. Otherwise every role
runs its deterministic part, and the steps that need the model say so. No placeholder data is produced.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy import func, select

from app.ai.client import AIClient, AIConfigError, AIError, get_client
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.council import critic, fastpath, llm, planner, reconcile, rules, storage
from app.council.extract import extract, rule_texts
from app.council.render import Rendered, RenderError, render_file
from app.council.review import build_items
from app.council.structure import SheetAnalysis, analyze
from app.models import CouncilJob, CouncilStep
from app.models.base import utcnow
from app.workers.queue import public_error

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class Ctx:
    job_id: int
    mode: str
    lang: str
    year_hint: int | None
    client: AIClient | None
    ai_note: str
    threshold: float
    timeout_s: float
    budget: int
    samples: int
    judge_n: int
    model: str | None
    fast_model: str | None
    rendered: dict[int, Rendered] = field(default_factory=dict)

    def tokens_used(self) -> int:
        if self.client is None:
            return 0
        return self.client.usage.input_tokens + self.client.usage.output_tokens

    def llm_ok(self) -> tuple[bool, str]:
        if self.client is None:
            return False, self.ai_note
        if self.tokens_used() >= self.budget:
            return False, f"token budget exhausted ({self.tokens_used()} >= {self.budget}); heuristic result kept"
        return True, ""


class StepRec:
    def __init__(self, ctx: Ctx, step_id: int) -> None:
        self.ctx = ctx
        self.step_id = step_id
        self.status = "DONE"
        self.messages: list[str] = []
        self.detail: dict[str, Any] = {}
        self.model: str | None = None

    def say(self, msg: str) -> None:
        if msg and msg not in self.messages:
            self.messages.append(msg)

    async def run(self, aw: Awaitable[T]) -> T:
        return await asyncio.wait_for(aw, self.ctx.timeout_s)


def _usage(client: AIClient | None) -> tuple[int, int, float]:
    if client is None:
        return 0, 0, 0.0
    return client.usage.input_tokens, client.usage.output_tokens, client.usage.estimated_cost_usd


@asynccontextmanager
async def step(ctx: Ctx, agent: str, file_index: int | None) -> AsyncIterator[StepRec]:
    factory = get_session_factory()
    async with factory() as s:
        q = (
            select(func.count())
            .select_from(CouncilStep)
            .where(CouncilStep.job_id == ctx.job_id, CouncilStep.agent == agent)
        )
        q = q.where(CouncilStep.file_index.is_(None) if file_index is None else CouncilStep.file_index == file_index)
        attempt = int((await s.execute(q)).scalar_one()) + 1
        row = CouncilStep(job_id=ctx.job_id, file_index=file_index, agent=agent, status="RUNNING", attempt=attempt)
        s.add(row)
        await s.commit()
        step_id = row.id
    rec = StepRec(ctx, step_id)
    before = _usage(ctx.client)
    t0 = time.perf_counter()
    try:
        yield rec
    except TimeoutError:
        rec.status = "FAILED"
        rec.say(f"{agent} timed out after {ctx.timeout_s:.0f}s")
    except Exception as exc:  # noqa: BLE001 - recorded on the step; the job continues
        log.exception("council job %s step %s file %s failed", ctx.job_id, agent, file_index)
        rec.status = "FAILED"
        rec.say(public_error(exc))
    finally:
        after = _usage(ctx.client)
        async with factory() as s:
            row2 = await s.get(CouncilStep, step_id)
            if row2 is not None:
                row2.status = rec.status
                row2.finished_at = utcnow()
                row2.duration_ms = int((time.perf_counter() - t0) * 1000)
                row2.input_tokens = after[0] - before[0]
                row2.output_tokens = after[1] - before[1]
                row2.cost_usd = round(after[2] - before[2], 6)
                row2.model = rec.model if row2.input_tokens else None
                row2.message = "\n".join(rec.messages)[:4000] or None
                row2.detail = rec.detail
                await s.commit()


async def _update_file(job_id: int, index: int, **fields: Any) -> None:
    async with get_session_factory()() as s:
        job = await s.get(CouncilJob, job_id)
        if job is None:
            return
        files = [dict(f) for f in job.files]
        files[index].update(fields)
        job.files = files
        await s.commit()


async def _artifact(
    ctx: Ctx,
    kind: str,
    payload: dict[str, Any],
    *,
    file_index: int | None = None,
    step_id: int | None = None,
    confidence: float | None = None,
) -> None:
    async with get_session_factory()() as s:
        await storage.add_artifact(
            s, ctx.job_id, kind, payload, file_index=file_index, step_id=step_id, confidence=confidence
        )
        await s.commit()


async def make_ctx(job: CouncilJob) -> Ctx:
    st = get_settings()
    client: AIClient | None = None
    note = ""
    model = (job.settings or {}).get("model") or st.council_model or None
    if not st.council_ai or (job.settings or {}).get("ai") is False:
        note = "AI disabled for the council (COUNCIL_AI=false or ai=false); deterministic path only"
    else:
        async with get_session_factory()() as s:
            try:
                client = await get_client(s, model=model)
            except AIConfigError:
                note = "no Anthropic API key configured: deterministic path only (heuristic mapping + importers)"
    return Ctx(
        job_id=job.id,
        mode=job.mode,
        lang=job.lang,
        year_hint=job.year_hint,
        client=client,
        ai_note=note,
        threshold=float((job.settings or {}).get("review_threshold") or st.council_review_threshold),
        timeout_s=float(st.council_step_timeout_s),
        budget=int(st.council_job_token_budget),
        samples=max(1, int(st.council_self_consistency)),
        judge_n=max(0, int(st.council_judge_sample)),
        model=model,
        fast_model=st.council_fast_model or model,
    )


# ---------------------------------------------------------------------------
# Per-file pipeline
# ---------------------------------------------------------------------------


def _year(ctx: Ctx, filename: str) -> int:
    from app.council import text as tx

    years = tx.years_in(filename)
    return years[0] if years else (ctx.year_hint or utcnow().year)


async def process_file(ctx: Ctx, entry: dict[str, Any]) -> None:
    i = entry["index"]
    name = entry["filename"]
    path = storage.file_path(ctx.job_id, entry)
    await _update_file(ctx.job_id, i, status="RUNNING")
    rendered: Rendered | None = None
    async with step(ctx, "intake", i) as st:
        data = path.read_bytes()
        try:
            rendered = await st.run(asyncio.to_thread(render_file, data, name))
        except RenderError as exc:
            st.status = "FAILED"
            st.say(str(exc))
        if rendered is not None and rendered.needs_vision:
            ok, why = ctx.llm_ok()
            if ok and ctx.client is not None:
                st.model = ctx.fast_model or ctx.client.model
                try:
                    res = await st.run(llm.transcribe(ctx.client, data, rendered, model=ctx.fast_model))
                    if not res.ok:
                        st.say(f"vision transcription failed: {res.message}")
                except AIError as exc:
                    st.say(f"vision transcription failed: {exc}")
            else:
                st.say(f"this file has no machine-readable text (image or scan); reading it needs the AI model ({why})")
        if rendered is not None:
            st.detail = rendered.summary()
            await _artifact(ctx, "rendered", rendered.summary(), file_index=i, step_id=st.step_id)
            for w in rendered.warnings:
                st.say(w)
    if rendered is None:
        await _update_file(ctx.job_id, i, status="FAILED", route="error", message="could not be read")
        return
    ctx.rendered[i] = rendered
    await _update_file(ctx.job_id, i, format=rendered.format, language=rendered.language, sha256=rendered.sha256)
    if rendered.needs_vision:
        await _update_file(
            ctx.job_id, i, status="DONE", route="vision", message="needs the AI model to read (image/scan)", counts={}
        )
        await _artifact(ctx, "records", {"records": [], "counts": {}, "route": "vision"}, file_index=i)
        return

    shape = None if ctx.mode == "general" else fastpath.detect_shape(rendered)
    records: list[dict[str, Any]] = []
    analyses: list[SheetAnalysis] = []
    warnings: list[str] = []
    route = f"fast:{shape}" if shape else "general"
    if shape:
        async with step(ctx, "structure", i) as st:
            st.status = "SKIPPED"
            st.say(f"known shape '{shape}': the existing importer reads this file (deterministic fast path)")
            await _artifact(
                ctx,
                "structure",
                {"route": route, "shape": shape, "analyses": []},
                file_index=i,
                step_id=st.step_id,
                confidence=1.0,
            )
        async with step(ctx, "extract", i) as st:
            records, warnings = await st.run(
                asyncio.to_thread(fastpath.records_for, shape, path, name, _year(ctx, name))
            )
            st.say(f"read by the {shape} importer's parser: {len(records)} records")
    else:
        async with step(ctx, "structure", i) as st:
            analyses = await st.run(asyncio.to_thread(analyze, rendered))
            ok, why = ctx.llm_ok()
            if not ok:
                st.say(why)
            elif ctx.client is not None:
                st.model = ctx.model or ctx.client.model
                merged: list[SheetAnalysis] = []
                for a in analyses:
                    if a.grid < 0 or (a.kind == "timetable_grid" and a.confidence >= ctx.threshold):
                        merged.append(a)
                        continue
                    ok, why = ctx.llm_ok()
                    if not ok:
                        st.say(why)
                        merged.append(a)
                        continue
                    try:
                        votes, msgs = await st.run(
                            llm.vote_structure(
                                ctx.client, rendered.grids[a.grid], name, samples=ctx.samples, model=ctx.model
                            )
                        )
                    except AIError as exc:
                        votes, msgs = [], [f"model vote failed: {exc}"]
                    for m in msgs:
                        st.say(m)
                    merged.append(llm.merge_votes(a, votes, ctx.threshold))
                analyses = merged
            conf = min((a.confidence for a in analyses if a.grid >= 0), default=None)
            st.detail = {"kinds": [a.kind for a in analyses]}
            await _artifact(
                ctx,
                "structure",
                {"route": route, "analyses": [a.to_dict() for a in analyses]},
                file_index=i,
                step_id=st.step_id,
                confidence=conf,
            )
        async with step(ctx, "extract", i) as st:
            records = await st.run(asyncio.to_thread(extract, rendered, analyses, year_hint=_year(ctx, name)))
            text_kind = next((a.kind for a in analyses if a.grid < 0), None)
            if not records and rendered.units and text_kind == "other":
                ok, why = ctx.llm_ok()
                if ok and ctx.client is not None:
                    st.model = ctx.model or ctx.client.model
                    try:
                        extra, msg = await st.run(
                            llm.extract_free_text(
                                ctx.client, rendered, rendered.units, model=ctx.model, year_hint=_year(ctx, name)
                            )
                        )
                        records += extra
                        st.say(msg)
                    except AIError as exc:
                        st.say(f"free-text extraction failed: {exc}")
                else:
                    st.say(f"free text without tables; record extraction from prose needs the AI model ({why})")
            st.say(f"{len(records)} records")
    texts = rule_texts(rendered, analyses, records)
    counts = dict(Counter(r["type"] for r in records))
    await _artifact(
        ctx, "records", {"records": records, "counts": counts, "warnings": warnings, "route": route}, file_index=i
    )
    await _artifact(ctx, "rule_texts", {"texts": texts}, file_index=i)
    kinds = sorted({a.kind for a in analyses}) if analyses else ([shape] if shape else [])
    await _update_file(
        ctx.job_id, i, status="DONE", route=route, counts=counts, kinds=kinds, rule_texts=len(texts), message=None
    )


# ---------------------------------------------------------------------------
# Cross-file steps
# ---------------------------------------------------------------------------


def _axis_slots(
    structures: dict[int, dict[str, Any]], records: dict[int, list[dict[str, Any]]]
) -> list[list[list[str]]]:
    out: list[list[list[str]]] = []
    for payload in structures.values():
        for a in payload.get("analyses", []):
            for ax in a.get("axes", []):
                out.append(ax.get("slots", []))
        if payload.get("shape") == "weekly-grid":
            out.append([[p["start"], p["end"]] for p in planner.DEFAULT_GRID])
    return out


def _source_row(rendered: Rendered, analyses: list[SheetAnalysis], src: dict[str, Any]) -> str:
    for a in analyses:
        if a.grid < 0:
            continue
        g = rendered.grids[a.grid]
        if "sheet" in src and g.origin.get("sheet") != src["sheet"]:
            continue
        if g.row_meta:
            rows = [
                k
                for k, meta in enumerate(g.row_meta)
                if all(meta[key] == src.get(key) for key in ("page", "line", "table", "row") if key in meta)
            ]
        else:
            rows = [g.row_numbers.index(src["row"])] if src.get("row") in g.row_numbers else []
        if not rows:
            continue
        r = rows[0]
        heads = [g.cell(a.header_rows[0], c) if a.header_rows else f"c{c}" for c in range(g.n_cols)]
        return " | ".join(f"{heads[c][:30]}={g.cell(r, c)}" for c in range(g.n_cols) if g.cell(r, c))
    return ""


async def cross_steps(ctx: Ctx) -> None:
    factory = get_session_factory()
    async with factory() as s:
        job = await s.get(CouncilJob, ctx.job_id)
        assert job is not None
        files = [dict(f) for f in job.files]
        records = await storage.records_by_file(s, job)
        structures = {fi: a.payload for fi, a in (await storage.latest_by_file(s, ctx.job_id, "structure")).items()}
        texts = {
            fi: a.payload.get("texts", [])
            for fi, a in (await storage.latest_by_file(s, ctx.job_id, "rule_texts")).items()
        }

    dataset: dict[str, Any] = {}
    async with step(ctx, "reconcile", None) as st:
        inputs = [(f["index"], f["filename"], records.get(f["index"], [])) for f in files]
        dataset = await st.run(asyncio.to_thread(reconcile.reconcile, inputs))
        st.say(
            f"{len(dataset['rooms'])} rooms, {len(dataset['courses'])} courses, "
            f"{len(dataset['duplicates'])} duplicate records, {len(dataset['merges'])} merge suggestions"
        )
        await _artifact(ctx, "dataset", dataset, step_id=st.step_id)

    plan_out: dict[str, Any] = {}
    async with step(ctx, "planner", None) as st:
        meta = []
        for f in files:
            rend = ctx.rendered.get(f["index"])
            meta.append(
                {"index": f["index"], "filename": f["filename"], "sheets": [g.name for g in rend.grids] if rend else []}
            )
        plan_out = planner.plan(meta, records, _axis_slots(structures, records))
        st.say(f"{len(plan_out['groups'])} term group(s); period grid: {plan_out['period_grid']['source']}")
        await _artifact(ctx, "plan", plan_out, step_id=st.step_id)
        async with factory() as s:
            job = await s.get(CouncilJob, ctx.job_id)
            if job is not None:
                job.plan = plan_out
                await s.commit()

    for f in files:
        fi = f["index"]
        if not texts.get(fi):
            continue
        async with step(ctx, "rules", fi) as st:
            ok, why = ctx.llm_ok()
            client = ctx.client if ok else None
            if client is not None:
                st.model = ctx.model or client.model
            try:
                mined = await st.run(rules.mine(client, texts[fi], dataset, lang=ctx.lang, model=ctx.model))
            except AIError as exc:
                mined = await rules.mine(None, texts[fi], dataset, lang=ctx.lang)
                st.say(f"rule miner model call failed ({exc}); texts kept for review")
            if client is None and why:
                st.say(why)
            for m in mined.get("messages", [])[:5]:
                st.say(m)
            await _artifact(ctx, "rules", mined, file_index=fi, step_id=st.step_id)

    async with step(ctx, "critic", None) as st:
        issues = await st.run(asyncio.to_thread(critic.check, dataset, records, plan_out))
        ok, why = ctx.llm_ok()
        if ctx.judge_n and ok and ctx.client is not None:
            st.model = ctx.fast_model or ctx.client.model
            for f in files:
                fi = f["index"]
                payload = structures.get(fi, {})
                if not payload.get("analyses") or fi not in ctx.rendered:
                    continue
                analyses = [SheetAnalysis.from_dict(a) for a in payload["analyses"]]
                recs = [(k, r) for k, r in enumerate(records.get(fi, [])) if r["type"] in ("meeting", "exam", "room")]
                stride = max(1, len(recs) // max(1, ctx.judge_n))
                samples = []
                for k, r in recs[::stride][: ctx.judge_n]:
                    row = _source_row(ctx.rendered[fi], analyses, r["source"])
                    if row:
                        samples.append((reconcile.rid(fi, k), r, row))
                try:
                    verdicts, msg = await st.run(llm.judge(ctx.client, samples, model=ctx.fast_model))
                except AIError as exc:
                    verdicts, msg = [], f"judge failed: {exc}"
                st.say(msg)
                bad = [v for v in verdicts if v["verdict"] == "mismatch"]
                st.detail.setdefault("judge", {})[str(fi)] = {"checked": len(verdicts), "mismatch": len(bad)}
                if bad:
                    issues.append(
                        {
                            "code": "judge_mismatch",
                            "severity": "warning",
                            "message": f"{f['filename']}: the model judge found {len(bad)} of {len(verdicts)} "
                            f"sampled records disagreeing with their source row "
                            f"(e.g. {bad[0]['field']}: {bad[0]['reason']})",
                            "records": [v["record"] for v in bad],
                            "sources": [],
                            "verdicts": bad,
                        }
                    )
        elif ctx.judge_n:
            st.say(f"model judge skipped: {why}")
        st.say(f"{len(issues)} finding(s)")
        await _artifact(ctx, "issues", {"issues": issues}, step_id=st.step_id)


async def finalize(job_id: int, client: AIClient | None, ai_note: str) -> dict[str, Any]:
    async with get_session_factory()() as s:
        job = await s.get(CouncilJob, job_id)
        assert job is not None
        items = await build_items(s, job)
        blocking = [it for it in items if it["blocking"] and it["decision"] is None]
        job.status = "REVIEW" if blocking else "READY"
        job.finished_at = utcnow()
        counts: Counter[str] = Counter()
        for f in job.files:
            counts.update(f.get("counts") or {})
        job.summary = {
            "files": len(job.files),
            "files_failed": sum(1 for f in job.files if f.get("status") == "FAILED"),
            "records": dict(counts),
            "review_items": len(items),
            "blocking_items": len(blocking),
            "ai": ai_note or "model used",
        }
        if client is not None:
            job.usage = client.usage.to_out()
        await s.commit()
        return {"status": job.status, **job.summary}


async def run_job(job_id: int, progress: Any = None) -> dict[str, Any]:
    """Queue body: every file, then the cross-file steps, then the review status."""
    factory = get_session_factory()
    async with factory() as s:
        job = await s.get(CouncilJob, job_id)
        if job is None:
            raise ValueError(f"council job {job_id} not found")
        job.status = "RUNNING"
        job.error = None
        await s.commit()
        ctx = await make_ctx(job)
        files = [dict(f) for f in job.files]
        job.ai_mode = "llm" if ctx.client is not None else "heuristic"
        await s.commit()
    total = len(files) + 1
    for n, f in enumerate(files):
        if progress:
            progress(f"file {n + 1}/{len(files)}: {f['filename']}", int(100 * n / total))
        await process_file(ctx, f)
    if progress:
        progress("cross-file: reconcile, plan, rules, critic", int(100 * len(files) / total))
    await cross_steps(ctx)
    return await finalize(job_id, ctx.client, ctx.ai_note)


async def on_status(job_id: int, status: str, error: str | None) -> None:
    if status != "FAILED":
        return
    async with get_session_factory()() as s:
        job = await s.get(CouncilJob, job_id)
        if job is not None:
            job.status = "FAILED"
            job.error = (error or "failed")[:2000]
            job.finished_at = utcnow()
            await s.commit()


def enqueue(job_id: int) -> None:
    from app.workers.queue import JobState, get_queue

    async def body(progress: Any) -> dict[str, Any]:
        return await run_job(job_id, progress)

    async def status_cb(st: JobState) -> None:
        await on_status(job_id, st.status, st.error)

    get_queue().enqueue(f"council:{job_id}", body, on_status=status_cb)


__all__ = ["Ctx", "cross_steps", "enqueue", "finalize", "make_ctx", "process_file", "run_job"]
