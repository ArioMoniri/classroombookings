"""Intake memory management: list what the intake remembers and forget it (owner request 2026-10-16).

``GET /council/memory`` lists the visible (not reset) rows of :mod:`app.council.memory` with a TR / EN
description, grouped by their signature (the row's ``subject_key``: a grid signature for column mappings and sheet
kinds, the signature set of a term group's files, one folded header spelling, a merge pair, a rule text).
``effective`` marks the row recall would use (the latest per kind, signature and attribute).

The rows hold hashes only; the description is rebuilt from the source job (its file names, sheet names and
headers). Headers, merge names and rule texts are file content: they are given to ``planning.edit`` only (like
``GET /council/jobs/{id}/review``); viewers see file names, kinds, fields and dates.

Forgetting (``DELETE /council/memory/{id}``, ``DELETE /council/memory?signature=``) is a learning reset of scope
``intake`` (:mod:`app.services.learning`): the rows are hidden at once, ``POST /learning/resets/{id}/undo`` restores
them for 30 days, the daily purge deletes them afterwards. One ``council.memory.forget`` audit event per forget.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.council import memory, storage
from app.council import text as tx
from app.models import CouncilJob, LearnedObservation, LearningReset, User
from app.models.base import utcnow
from app.services.events import publish_event

SCOPE = "intake"
MAX_ROWS = 2000
#: the group a kind belongs to in the management view
GROUP_OF = {
    "intake_mapping": "layout",
    "intake_kind": "layout",
    "intake_term": "term",
    "intake_lexicon": "lexicon",
    "intake_merge": "merge",
    "intake_rule": "rule",
}
ACTIONS = {
    "accept": ("kabul edildi", "accepted"),
    "reject": ("reddedildi", "rejected"),
    "edit": ("düzenlendi", "edited"),
}


class IntakeMemoryError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


async def _job_info(session: AsyncSession, job: CouncilJob) -> dict[str, Any]:
    """Grid signature -> {file, sheet, headers}, header hash -> header, file-set signature -> file names."""
    names = {int(f["index"]): str(f.get("filename") or "") for f in job.files or []}
    grids: dict[str, dict[str, Any]] = {}
    headers: dict[str, str] = {}
    for fi, art in (await storage.latest_by_file(session, job.id, "structure")).items():
        analyses = [a for a in art.payload.get("analyses", []) if a.get("grid", -1) >= 0]
        sheets = [str(a.get("name") or "") for a in analyses]
        for a in analyses:
            hs = [str(c.get("header") or "") for c in a.get("columns", [])]
            grids[memory.grid_signature(sheets, hs)] = {
                "file": names.get(fi, str(fi)),
                "file_index": fi,
                "sheet": str(a.get("name") or ""),
                "headers": hs,
            }
            for h in hs:
                if tx.fold(h):
                    headers.setdefault(memory._h("header", tx.fold(h)), h)
    sigs = await memory.signatures(session, job)
    files: dict[str, list[str]] = {}
    for g in (job.plan or {}).get("groups", []):
        fs = [int(x) for x in g.get("files") or []]
        files[memory._file_sig(sigs, fs)] = [names.get(x, str(x)) for x in fs]
    return {"grids": grids, "headers": headers, "files": files, "names": names}


def _col(attribute: str) -> int | None:
    return int(attribute[4:]) if attribute.startswith("col:") and attribute[4:].isdigit() else None


def describe(r: LearnedObservation, info: dict[str, Any] | None, content: bool) -> dict[str, Any]:
    """``{tr, en}`` sentence and the context (file, sheet, header, ...) of one memory row."""
    detail = r.detail or {}
    item = str(detail.get("item") or "")
    value = None if r.value == "-" else r.value
    ctx: dict[str, Any] = {}
    tr = en = ""
    if r.kind in ("intake_mapping", "intake_kind"):
        g = (info or {}).get("grids", {}).get(r.subject_key)
        where_tr = where_en = ""
        if g is not None:
            ctx.update(file=g["file"], sheet=g["sheet"])
            where_tr = where_en = f"{g['file']} › {g['sheet']}: "
        if r.kind == "intake_mapping":
            col = _col(r.attribute)
            header = g["headers"][col] if g is not None and col is not None and col < len(g["headers"]) else None
            ctx["column"] = col
            if content and header:
                ctx["header"] = header
            n = (col or 0) + 1
            head = f" '{header}'" if content and header else ""
            tr = f"{where_tr}{n}. sütun{head} → " + (value or "kullanılmıyor")
            en = f"{where_en}column {n}{head} → " + (value or "not used")
        else:
            ctx["sheet_kind"] = value
            tr = f"{where_tr}sayfa türü {value}"
            en = f"{where_en}sheet kind {value}"
    elif r.kind == "intake_lexicon":
        header = (info or {}).get("headers", {}).get(r.subject_key)
        if content and header:
            ctx["header"] = header
            tr, en = f"'{header}' başlığı → {value}", f"Header '{header}' → {value}"
        else:
            tr, en = f"Bir başlık yazımı → {value}", f"A header spelling → {value}"
    elif r.kind == "intake_term":
        files = (info or {}).get("files", {}).get(r.subject_key) or []
        ctx["files"] = files
        ctx["term"] = r.value
        on = f"{', '.join(files)} → " if files else ""
        tr, en = f"{on}dönem {r.value}", f"{on}term {r.value}"
    elif r.kind == "intake_merge":
        a_tr, a_en = ACTIONS.get(r.value, (r.value, r.value))
        parts = item.split(":", 2)  # merge:<kind>:<a>|<b>
        mkind = parts[1] if len(parts) == 3 else ""
        ctx["merge_kind"] = mkind or None
        pair = parts[2].split("|", 1) if len(parts) == 3 else []
        if content and len(pair) == 2:
            ctx.update(a=pair[0], b=pair[1])
            tr = f"Birleştirme ({mkind}) '{pair[0]}' = '{pair[1]}': {a_tr}"
            en = f"Merge ({mkind}) '{pair[0]}' = '{pair[1]}': {a_en}"
        else:
            tr, en = f"Birleştirme ({mkind}): {a_tr}", f"Merge ({mkind}): {a_en}"
    elif r.kind == "intake_rule":
        a_tr, a_en = ACTIONS.get(r.value, (r.value, r.value))
        parts = item.split(":")  # rule:<file>:<n>
        fi = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else None
        fname = (info or {}).get("names", {}).get(fi) if fi is not None else None
        ctx["file"] = fname
        on_tr = f"{fname} dosyasındaki kural" if fname else "Bir kural"
        on_en = f"Rule in {fname}" if fname else "A rule"
        tr, en = f"{on_tr}: {a_tr}", f"{on_en}: {a_en}"
    return {"tr": tr, "en": en, "context": ctx}


def _group_label(kind_group: str, rows: list[dict[str, Any]]) -> dict[str, str]:
    ctx = rows[0]["context"]
    if kind_group == "layout":
        if ctx.get("file"):
            return {
                "tr": f"{ctx['file']} › {ctx.get('sheet') or ''}",
                "en": f"{ctx['file']} › {ctx.get('sheet') or ''}",
            }
        return {"tr": "Dosya düzeni (kaynak iş silinmiş)", "en": "File layout (source job deleted)"}
    if kind_group == "term":
        files = ", ".join(ctx.get("files") or [])
        return {"tr": f"Dönem eşlemesi {files}".strip(), "en": f"Term mapping {files}".strip()}
    if kind_group == "lexicon":
        h = ctx.get("header")
        return {"tr": f"Başlık '{h}'" if h else "Başlık yazımı", "en": f"Header '{h}'" if h else "Header spelling"}
    if kind_group == "merge":
        if ctx.get("a") and ctx.get("b"):  # file content: planners only (describe(content=True))
            pair = f"'{ctx['a']}' = '{ctx['b']}'"
            return {"tr": f"Birleştirme {pair}", "en": f"Merge {pair}"}
        return {"tr": "Birleştirme kararı", "en": "Merge decision"}
    if ctx.get("file"):
        return {"tr": f"Kural kararı · {ctx['file']}", "en": f"Rule decision · {ctx['file']}"}
    return {"tr": "Kural kararı", "en": "Rule decision"}


async def listing(
    session: AsyncSession,
    *,
    signature: str | None = None,
    kind: str | None = None,
    job_id: int | None = None,
    content: bool = False,
) -> dict[str, Any]:
    """The visible intake memory, newest first, with the groups (one per signature)."""
    if kind is not None and kind not in memory.KINDS:
        raise IntakeMemoryError(422, f"kind must be one of {list(memory.KINDS)}")
    q = select(LearnedObservation).where(
        LearnedObservation.subject_type == memory.SUBJECT, LearnedObservation.reset_id.is_(None)
    )
    if signature:
        q = q.where(LearnedObservation.subject_key == signature.strip().lower())
    if kind:
        q = q.where(LearnedObservation.kind == kind)
    if job_id is not None:
        q = q.where(LearnedObservation.source_id == job_id)
    rows = list(
        (await session.execute(q.order_by(LearnedObservation.ts.desc(), LearnedObservation.id.desc()).limit(MAX_ROWS)))
        .scalars()
        .all()
    )
    # the row recall uses: the latest per (kind, signature, attribute) over all visible rows
    latest: dict[tuple[str, str, str], int] = {}
    keys = {r.subject_key for r in rows}
    if keys:
        for r in (
            await session.execute(
                select(LearnedObservation)
                .where(
                    LearnedObservation.subject_type == memory.SUBJECT,
                    LearnedObservation.reset_id.is_(None),
                    LearnedObservation.subject_key.in_(sorted(keys)),
                )
                .order_by(LearnedObservation.ts, LearnedObservation.id)
            )
        ).scalars():
            latest[(r.kind, r.subject_key, r.attribute)] = r.id
    jobs: dict[int, dict[str, Any] | None] = {}
    users: dict[int, str | None] = {}
    items: list[dict[str, Any]] = []
    for r in rows:
        if r.source_id not in jobs:
            job = await session.get(CouncilJob, r.source_id)
            jobs[r.source_id] = await _job_info(session, job) if job is not None else None
        if r.actor_id is not None and r.actor_id not in users:
            u = await session.get(User, r.actor_id)
            users[r.actor_id] = (u.full_name or u.email or u.username) if u is not None else None
        d = describe(r, jobs[r.source_id], content)
        items.append(
            {
                "id": r.id,
                "signature": r.subject_key,
                "kind": r.kind,
                "group": GROUP_OF.get(r.kind, "other"),
                "attribute": r.attribute,
                "value": None if r.value == "-" else r.value,
                "action": (r.detail or {}).get("action"),
                "created_at": r.created_at,
                "created_by": {"id": r.actor_id, "name": users.get(r.actor_id)} if r.actor_id is not None else None,
                "job_id": r.source_id,
                "job_exists": jobs[r.source_id] is not None,
                "term_id": r.term_id,
                "effective": latest.get((r.kind, r.subject_key, r.attribute)) == r.id,
                "description": {"tr": d["tr"], "en": d["en"]},
                "context": d["context"],
            }
        )
    groups: dict[str, dict[str, Any]] = {}
    for it in items:
        g = groups.get(it["signature"])
        if g is None:
            g = groups[it["signature"]] = {
                "signature": it["signature"],
                "group": it["group"],
                "kinds": [],
                "jobs": [],
                "count": 0,
                "last_at": it["created_at"],
                "rows": [],
            }
        g["count"] += 1
        g["rows"].append(it)
        if it["kind"] not in g["kinds"]:
            g["kinds"].append(it["kind"])
        if it["job_id"] not in g["jobs"]:
            g["jobs"].append(it["job_id"])
    out_groups = []
    for g in groups.values():
        label = _group_label(g["group"], g["rows"])
        out_groups.append(
            {**{k: v for k, v in g.items() if k != "rows"}, "label": label, "ids": [x["id"] for x in g["rows"]]}
        )
    return {
        "items": items,
        "groups": out_groups,
        "total": len(items),
        "content": content,
        "truncated": len(rows) >= MAX_ROWS,
    }


async def _forget(
    session: AsyncSession, actor: User, where: Any, scope_value: str, reason: str | None, subject: dict[str, Any]
) -> dict[str, Any]:
    from app.services import learning

    ids = list(
        (
            await session.execute(
                select(LearnedObservation.id).where(
                    LearnedObservation.subject_type == memory.SUBJECT, LearnedObservation.reset_id.is_(None), where
                )
            )
        ).scalars()
    )
    if not ids:
        raise IntakeMemoryError(404, "no remembered decision matches")
    now = utcnow()
    rs = LearningReset(
        kind="RESET",
        scope_type=SCOPE,
        scope_value=scope_value[:64],
        reason=(reason or "").strip() or "intake memory: forgotten in Hatırlanan kararlar",
        actor_id=actor.id,
        created_at=now,
        watermark=now,
        expires_at=now + timedelta(days=learning.UNDO_DAYS),
        counts={"observations": len(ids), "feedback": 0, "suggestions": 0},
    )
    session.add(rs)
    await session.flush()
    await session.execute(
        update(LearnedObservation)
        .where(LearnedObservation.id.in_(ids))
        .values(reset_id=rs.id)
        .execution_options(synchronize_session=False)
    )
    await publish_event(
        session,
        "council.memory.forget",
        "learning_reset",
        rs.id,
        after={**subject, "rows": len(ids), "undo_until": rs.expires_at.isoformat()},
        actor=actor,
        reason=rs.reason,
    )
    return {**learning.reset_out(rs), "forgotten": len(ids), "ids": ids}


async def forget_one(session: AsyncSession, actor: User, row_id: int, reason: str | None = None) -> dict[str, Any]:
    return await _forget(
        session, actor, LearnedObservation.id == row_id, f"#{row_id}", reason, {"scope": SCOPE, "row": row_id}
    )


async def forget_signature(
    session: AsyncSession, actor: User, signature: str, reason: str | None = None
) -> dict[str, Any]:
    sig = (signature or "").strip().lower()
    if not sig:
        raise IntakeMemoryError(422, "signature is required")
    return await _forget(
        session, actor, LearnedObservation.subject_key == sig, sig, reason, {"scope": SCOPE, "signature": sig}
    )


__all__ = ["SCOPE", "IntakeMemoryError", "describe", "forget_one", "forget_signature", "listing"]
