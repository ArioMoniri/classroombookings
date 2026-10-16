"""Intake memory: what coordinators confirmed in review, offered again on the next matching upload.

Remembered per institution (one database), as rows of the learning lane's ``learned_observations`` with
``subject_type = "intake"`` (:mod:`app.services.learning`), so the existing memory controls cover it: a reset
(``all`` / ``term``; planning.admin, audited) hides the rows, undo restores them for 30 days, the daily purge
deletes them afterwards. Rows hold hashes, field / kind names and term codes only, never cell content or names.

| kind | subject key (sha256) | attribute | value |
|---|---|---|---|
| ``intake_mapping`` | grid signature (file's sheet names + grid's folded headers) | ``col:<n>`` | field or ``-`` |
| ``intake_lexicon`` | one folded header spelling | ``header`` | field it was mapped to |
| ``intake_kind`` | grid signature | ``kind`` | sheet kind |
| ``intake_term`` | the signature set of the group's files | ``term`` | term code (the edit in ``detail``) |
| ``intake_merge`` | the pair (kind, a, b), folded | ``merge`` | accept / reject |
| ``intake_rule`` | the rule text, folded | ``rule`` | accept / reject / edit |

Recall (:func:`recall`, used by :func:`app.council.review.build_items`) never decides anything: a matching review
item gets ``remembered`` (value, job, date and the label "remembered from <date> / job <id>") and ``suggestion``
(the decision to post). A column the analysis is sure about but a coordinator mapped differently before becomes a
blocking ``mapping`` item with that suggestion, so the job stays review-gated; nothing is committed without a
person. The job's own decisions are not recalled into it, and a file with another signature matches nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.council import storage
from app.council import text as tx
from app.models import CouncilJob, LearnedObservation, User
from app.models.base import utcnow

SUBJECT = "intake"
SOURCE_TABLE = "council_jobs"
KINDS = ("intake_mapping", "intake_lexicon", "intake_kind", "intake_term", "intake_merge", "intake_rule")


def _h(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def grid_signature(sheets: Iterable[str], headers: Iterable[str]) -> str:
    """Header fingerprint + the file's sheet names (Turkish-folded, so ``İ``/``ı``/NBSP do not matter)."""
    return _h("grid", [tx.fold(s) for s in sheets], [tx.fold(h) for h in headers])


async def signatures(session: AsyncSession, job: CouncilJob) -> dict[tuple[int, int], dict[str, Any]]:
    """(file, grid) -> {"sig", "headers"} from the job's structure analyses (general-path files)."""
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for fi, art in (await storage.latest_by_file(session, job.id, "structure")).items():
        analyses = [a for a in art.payload.get("analyses", []) if a.get("grid", -1) >= 0]
        sheets = [str(a.get("name") or "") for a in analyses]
        for a in analyses:
            headers = [str(c.get("header") or "") for c in a.get("columns", [])]
            out[(fi, int(a["grid"]))] = {"sig": grid_signature(sheets, headers), "headers": headers}
    return out


def _file_sig(sigs: dict[tuple[int, int], dict[str, Any]], files: Iterable[int]) -> str:
    return _h("files", sorted(v["sig"] for (fi, _), v in sigs.items() if fi in set(files)))


def _merge_key(m: dict[str, Any]) -> str:
    return _h("merge", m.get("kind"), tx.fold(m.get("a") or ""), tx.fold(m.get("b") or ""))


def merge_item_id(m: dict[str, Any]) -> str:
    """Opaque review item id of a merge proposal: ``merge:<kind>:<16 hex of the folded pair's hash>`` (T-R1-22).

    The two spellings are names of people (or room codes): they travel only inside the item's ``current`` and only
    to planners (``content=true``), never in an id that viewers, the audit log or the intake memory keep."""
    return f"merge:{m.get('kind')}:{_merge_key(m)[:16]}"


def legacy_merge_item_id(m: dict[str, Any]) -> str:
    """The id of a merge before T-R1-22 (``merge:<kind>:<a>|<b>``): read only, for decisions stored back then."""
    return f"merge:{m.get('kind')}:{m.get('a')}|{m.get('b')}"


def _rule_key(item: dict[str, Any]) -> str:
    return _h(
        "rule", tx.fold(item.get("text") or (item.get("current") or {}).get("nl_text") or item.get("title") or "")
    )


def facts(
    item: dict[str, Any], decision: dict[str, Any], sigs: dict[tuple[int, int], dict[str, Any]]
) -> list[tuple[str, str, str, str, dict[str, Any]]]:
    """(kind, subject key, attribute, value, detail) to remember for one decided review item."""
    action, value = decision["action"], decision.get("value") or {}
    kind = item["kind"]
    out: list[tuple[str, str, str, str, dict[str, Any]]] = []
    if kind == "mapping":
        g = sigs.get((item["file_index"], item["grid"]))
        if g is None:
            return out
        field = (
            str(value.get("field") or "")
            if action == "edit"
            else ("" if action == "reject" else str((item.get("current") or {}).get("field") or ""))
        )
        col = int(item["column"])
        out.append(("intake_mapping", g["sig"], f"col:{col}", field or "-", {}))
        header = g["headers"][col] if col < len(g["headers"]) else ""
        if action == "edit" and field and tx.fold(header):
            out.append(("intake_lexicon", _h("header", tx.fold(header)), "header", field, {}))
    elif kind == "classification":
        g = sigs.get((item["file_index"], item["grid"]))
        if g is not None:
            k = str(value.get("kind") if action == "edit" else (item.get("current") or {}).get("kind") or "")
            if k:
                out.append(("intake_kind", g["sig"], "kind", k, {}))
    elif kind == "plan" and item.get("files"):
        cur = {**(item.get("current") or {}), **(value if action == "edit" else {})}
        if cur.get("code"):
            edit = {k: cur.get(k) for k in ("code", "name", "kind", "week_count", "start_date", "year")}
            out.append(("intake_term", _file_sig(sigs, item["files"]), "term", str(cur["code"])[:64], {"term": edit}))
    elif kind == "merge":
        out.append(("intake_merge", _merge_key(item.get("current") or {}), "merge", action, {}))
    elif kind == "rule":
        out.append(("intake_rule", _rule_key(item), "rule", action, {"value": value} if action == "edit" else {}))
    return out


async def remember(
    session: AsyncSession,
    job: CouncilJob,
    decided: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    actor: User | None,
) -> int:
    """Store the facts of the decided items (one row per job and fact; a later decision of the same job replaces
    its earlier one). Flushes; the caller commits."""
    sigs = await signatures(session, job)
    now = utcnow()
    n = 0
    for item_id, (item, decision) in decided.items():
        for kind, key, attr, value, detail in facts(item, decision, sigs):
            await session.execute(
                delete(LearnedObservation).where(
                    LearnedObservation.subject_type == SUBJECT,
                    LearnedObservation.source_table == SOURCE_TABLE,
                    LearnedObservation.source_id == job.id,
                    LearnedObservation.kind == kind,
                    LearnedObservation.subject_key == key,
                    LearnedObservation.attribute == attr,
                    LearnedObservation.reset_id.is_(None),
                )
            )
            session.add(
                LearnedObservation(
                    ts=now,
                    created_at=now,
                    term_id=None,
                    kind=kind,
                    subject_type=SUBJECT,
                    subject_key=key[:64],
                    attribute=attr[:16],
                    value=value[:64],
                    sign=1,
                    weight=0,  # never a learned scheduling prior (app/services/learning.py weighs evidence)
                    source_table=SOURCE_TABLE,
                    source_id=job.id,
                    actor_id=actor.id if actor is not None else None,
                    detail={
                        # a merge row keeps the pair's hash (subject_key) and its kind, never the item id or names
                        **(
                            {"merge_kind": item.get("current", {}).get("kind")}
                            if kind == "intake_merge"
                            else {"item": item_id}
                        ),
                        "action": decision["action"],
                        "at": now.isoformat(timespec="minutes"),
                        **detail,
                    },  # fmt: skip
                )
            )
            n += 1
    await scrub_legacy(session)
    await session.flush()
    return n


async def scrub_legacy(session: AsyncSession) -> int:
    """Drop the item id from merge rows written before T-R1-22 (it held the two names): keep only the kind.

    Idempotent; flushes, the caller commits. Run by :func:`remember` and by the memory listing."""
    rows = (
        (
            await session.execute(
                select(LearnedObservation).where(
                    LearnedObservation.subject_type == SUBJECT, LearnedObservation.kind == "intake_merge"
                )
            )
        )
        .scalars()
        .all()
    )
    n = 0
    for r in rows:
        detail = dict(r.detail or {})
        if "item" not in detail:
            continue
        parts = str(detail.pop("item") or "").split(":", 2)
        detail.setdefault("merge_kind", parts[1] if len(parts) == 3 else None)
        r.detail = detail
        n += 1
    if n:
        await session.flush()
    return n


async def attach_term(session: AsyncSession, job_id: int, term_id: int) -> None:
    """After a commit: the job's memory belongs to that term, so a term reset covers it."""
    await session.execute(
        update(LearnedObservation)
        .where(
            LearnedObservation.subject_type == SUBJECT,
            LearnedObservation.source_table == SOURCE_TABLE,
            LearnedObservation.source_id == job_id,
            LearnedObservation.term_id.is_(None),
        )
        .values(term_id=term_id)
        .execution_options(synchronize_session=False)
    )


async def _visible(session: AsyncSession, job_id: int, keys: set[str]) -> dict[tuple[str, str, str], Any]:
    """Latest visible (not reset) fact per (kind, subject key, attribute) from other jobs."""
    if not keys:
        return {}
    rows = (
        await session.execute(
            select(LearnedObservation)
            .where(
                LearnedObservation.subject_type == SUBJECT,
                LearnedObservation.reset_id.is_(None),
                LearnedObservation.source_id != job_id,
                LearnedObservation.subject_key.in_(sorted(keys)),
            )
            .order_by(LearnedObservation.ts, LearnedObservation.id)
        )
    ).scalars()
    out: dict[tuple[str, str, str], Any] = {}
    for r in rows:
        out[(r.kind, r.subject_key, r.attribute)] = r
    return out


def _note(r: Any) -> dict[str, Any]:
    at = (r.detail or {}).get("at") or r.ts.isoformat(timespec="minutes")
    return {
        "value": None if r.value == "-" else r.value,
        "action": (r.detail or {}).get("action"),
        "job": r.source_id,
        "at": at,
        "kind": r.kind,
        "label": f"remembered from {str(at)[:10]} / job {r.source_id}",
        "label_tr": f"{str(at)[:10]} tarihli {r.source_id} numaralı işten hatırlandı",
    }


async def recall(session: AsyncSession, job: CouncilJob, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark ``items`` with remembered suggestions and return extra items for confident columns that a coordinator
    mapped differently before (blocking, so the job stays review-gated)."""
    sigs = await signatures(session, job)
    keys = {v["sig"] for v in sigs.values()}
    lex = {}
    for (fi, grid), v in sigs.items():
        for col, header in enumerate(v["headers"]):
            if tx.fold(header):
                lex[(fi, grid, col)] = _h("header", tx.fold(header))
    keys |= set(lex.values())
    for it in items:
        if it["kind"] == "plan" and it.get("files"):
            keys.add(_file_sig(sigs, it["files"]))
        elif it["kind"] == "merge":
            keys.add(_merge_key(it.get("current") or {}))
        elif it["kind"] == "rule":
            keys.add(_rule_key(it))
    mem = await _visible(session, job.id, keys)
    if not mem:
        return []
    for it in items:
        r = None
        suggestion: dict[str, Any] | None = None
        if it["kind"] == "mapping":
            g = sigs.get((it["file_index"], it["grid"]))
            r = mem.get(("intake_mapping", g["sig"], f"col:{it['column']}")) if g else None
            if r is None and (it["file_index"], it["grid"], it["column"]) in lex:
                r = mem.get(("intake_lexicon", lex[(it["file_index"], it["grid"], it["column"])], "header"))
            if r is not None:
                field = None if r.value == "-" else r.value
                current = (it.get("current") or {}).get("field")
                suggestion = (
                    {"action": "accept"}
                    if field == current
                    else ({"action": "reject"} if field is None else {"action": "edit", "value": {"field": field}})
                )
        elif it["kind"] == "classification":
            g = sigs.get((it["file_index"], it["grid"]))
            r = mem.get(("intake_kind", g["sig"], "kind")) if g else None
            if r is not None:
                same = r.value == (it.get("current") or {}).get("kind")
                suggestion = {"action": "accept"} if same else {"action": "edit", "value": {"kind": r.value}}
        elif it["kind"] == "plan" and it.get("files"):
            r = mem.get(("intake_term", _file_sig(sigs, it["files"]), "term"))
            if r is not None:
                suggestion = {"action": "edit", "value": dict((r.detail or {}).get("term") or {"code": r.value})}
        elif it["kind"] == "merge":
            r = mem.get(("intake_merge", _merge_key(it.get("current") or {}), "merge"))
            if r is not None:
                suggestion = {"action": r.value}
        elif it["kind"] == "rule":
            r = mem.get(("intake_rule", _rule_key(it), "rule"))
            if r is not None:
                suggestion = {
                    "action": r.value,
                    **({"value": (r.detail or {}).get("value")} if r.value == "edit" else {}),
                }
        if r is not None and suggestion is not None:
            it["remembered"] = _note(r)
            it["suggestion"] = suggestion
    # confident columns (no review item) that a coordinator mapped otherwise for the same signature
    have = {(it["file_index"], it["grid"], it["column"]) for it in items if it["kind"] == "mapping"}
    extra: list[dict[str, Any]] = []
    names = {f["index"]: f["filename"] for f in job.files}
    for fi, art in (await storage.latest_by_file(session, job.id, "structure")).items():
        for a in art.payload.get("analyses", []):
            g = sigs.get((fi, int(a.get("grid", -1))))
            if g is None or a.get("kind") == "timetable_grid":
                continue
            for c in a.get("columns", []):
                r = mem.get(("intake_mapping", g["sig"], f"col:{c['index']}"))
                if r is None or (fi, a["grid"], c["index"]) in have:
                    continue
                field = None if r.value == "-" else r.value
                if field == c.get("field"):
                    continue
                extra.append(
                    {
                        "id": f"map:{fi}:{a['grid']}:{c['index']}",
                        "kind": "mapping",
                        "title": f"{names.get(fi, fi)} / {a.get('name')}: column '{c.get('header') or c['index']}' "
                        f"-> {c.get('field') or '(not used)'}? (remembered: {field or '(not used)'})",
                        "blocking": True,
                        "decision": None,
                        "file_index": fi,
                        "grid": a["grid"],
                        "column": c["index"],
                        "confidence": c.get("confidence"),
                        "current": {"field": c.get("field")},
                        "alternatives": c.get("alternatives", []),
                        "samples": c.get("samples", []),
                        "source": c.get("source"),
                        "remembered": _note(r),
                        "suggestion": {"action": "reject"}
                        if field is None
                        else {"action": "edit", "value": {"field": field}},
                    }
                )
    return extra


__all__ = [
    "KINDS",
    "SUBJECT",
    "attach_term",
    "facts",
    "grid_signature",
    "legacy_merge_item_id",
    "merge_item_id",
    "recall",
    "remember",
    "scrub_legacy",
    "signatures",
]
