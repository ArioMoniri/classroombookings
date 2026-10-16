"""Row review for AI-read records (Phase 19 P19-A2, owner decisions of 2026-10-15).

A record is an **AI row** when the model produced it: a vision transcription (``source.vision``) or a record the
model extracted (``source.via == "llm"``). A table the server read itself is a **direct** row whatever the file's
format route (T-R1-21: the deterministic DOCX / PDF table rows read with AI off are direct, not AI). AI rows start
``pending``; only a person makes them ``accepted``, ``edited`` or ``rejected``
(``POST /council/jobs/{id}/rows/decisions``). Direct rows are ``ready`` and may be rejected or edited too.

* Commit refuses (409) while an AI row of the chosen files is pending; ``allow_pending`` does not apply to them.
  Rejected rows are not written; an edit replaces the named record fields.
* Bulk: one call may decide at most :data:`BULK_MAX` AI rows, and only with ``confirm=true``; an AI row below the
  job's review threshold (low confidence) is decided on its own (a call holding only that row).
* One blocking review item per file (``rows:<file>``, kind ``ai_rows``) says how many AI rows wait, so the job is
  ``REVIEW`` until they are decided (it decides itself when none is pending).

Decisions are ``review`` artifacts like every other decision (``row:<file>:<record>``) and one
``council.review`` audit event per call.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.council import storage
from app.models import CouncilJob, User
from app.models.base import utcnow
from app.services.events import publish_event

BULK_MAX = 50
ACTIONS = ("accept", "reject", "edit")
STATE = {"accept": "accepted", "reject": "rejected", "edit": "edited"}
#: record keys a reviewer may not edit (identity and provenance)
FROZEN = frozenset({"type", "source", "warnings", "confidence", "review_required"})


class RowDecisionError(ValueError):
    """A refused row decision call (HTTP 422)."""


def row_id(fi: int, k: int) -> str:
    return f"row:{fi}:{k}"


def is_ai(entry: dict[str, Any], rec: dict[str, Any]) -> bool:
    """True only for a record the model produced (``entry`` is kept for the callers' signature)."""
    src = rec.get("source") or {}
    return bool(src.get("vision") or src.get("via") == "llm")


def _threshold(job: CouncilJob) -> float:
    from app.council.review import _threshold as thr

    return thr(job)


async def rows(
    session: AsyncSession, job: CouncilJob, decided: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Every record of the job as a review row (state, method, confidence, provenance, values)."""
    from app.council.review import decisions

    decided = decided if decided is not None else await decisions(session, job.id)
    entries = {f["index"]: f for f in job.files}
    thr = _threshold(job)
    out: list[dict[str, Any]] = []
    for fi, recs in sorted((await storage.records_by_file(session, job)).items()):
        entry = entries.get(fi, {"index": fi})
        for k, rec in enumerate(recs):
            ai = is_ai(entry, rec)
            d = decided.get(row_id(fi, k))
            state = STATE[d["action"]] if d else ("pending" if ai else "ready")
            raw_conf = rec.get("confidence")
            conf = float(raw_conf) if isinstance(raw_conf, (int, float)) else 1.0
            out.append(
                {
                    "id": row_id(fi, k),
                    "file_index": fi,
                    "record_index": k,
                    "entity": rec.get("type"),
                    "method": "ai" if ai else "direct",
                    "review_required": ai,
                    "state": state,
                    "confidence": conf,
                    "low_confidence": ai and conf < thr,
                    "values": {kk: v for kk, v in rec.items() if kk not in ("source", "warnings")},
                    "edited": (d or {}).get("value") if d and d["action"] == "edit" else None,
                    "issues": list(rec.get("warnings") or []),
                    "provenance": {"file": entry.get("filename"), **(rec.get("source") or {})},
                    "decision": d,
                }
            )
    return out


def counts(all_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_state: dict[str, int] = {}
    by_method: dict[str, int] = {}
    for r in all_rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        by_method[r["method"]] = by_method.get(r["method"], 0) + 1
    return {"state": by_state, "method": by_method, "total": len(all_rows)}


async def pending_ai(session: AsyncSession, job: CouncilJob, files: list[int] | None = None) -> list[str]:
    wanted = set(files) if files is not None else None
    return [
        r["id"]
        for r in await rows(session, job)
        if r["state"] == "pending" and (wanted is None or r["file_index"] in wanted)
    ]


async def review_items(
    session: AsyncSession, job: CouncilJob, decided: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One blocking ``ai_rows`` item per file with AI rows (decided by itself when none is pending)."""
    per_file: dict[int, dict[str, int]] = {}
    for r in await rows(session, job, decided):
        if r["method"] != "ai":
            continue
        c = per_file.setdefault(r["file_index"], {"pending": 0, "total": 0})
        c["total"] += 1
        c["pending"] += r["state"] == "pending"
    names = {f["index"]: f["filename"] for f in job.files}
    out = []
    for fi, c in sorted(per_file.items()):
        out.append(
            {
                "id": f"rows:{fi}",
                "kind": "ai_rows",
                "title": f"{names.get(fi, fi)}: {c['pending']} of {c['total']} rows read by the AI model wait for "
                "a person (accept, edit or reject each row)",
                "blocking": True,
                "decision": None if c["pending"] else {"action": "accept", "auto": True},
                "file_index": fi,
                "pending": c["pending"],
                "total": c["total"],
            }
        )
    return out


async def decide(
    session: AsyncSession, job: CouncilJob, items_in: list[dict[str, Any]], actor: User | None, *, confirm: bool
) -> dict[str, Any]:
    """Store row decisions (see the module notes for the bulk rules). Raises :class:`RowDecisionError`."""
    known = {r["id"]: r for r in await rows(session, job)}
    errors: list[str] = []
    chosen: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for d in items_in:
        r = known.get(str(d.get("row_id")))
        if r is None:
            errors.append(f"unknown row {d.get('row_id')}")
            continue
        if d.get("action") not in ACTIONS:
            errors.append(f"{r['id']}: action must be accept, reject or edit")
            continue
        value = d.get("value") if isinstance(d.get("value"), dict) else None
        if d["action"] == "edit":
            bad = sorted(set(value or {}) - (set(r["values"]) - FROZEN))
            if not value or bad:
                errors.append(f"{r['id']}: edit needs value with record fields ({', '.join(bad) or 'empty'})")
                continue
        chosen.append((r, {"action": d["action"], "value": value}))
    ai = [r for r, _ in chosen if r["method"] == "ai"]
    if len(ai) > 1:
        if len(ai) > BULK_MAX:
            raise RowDecisionError(f"at most {BULK_MAX} AI rows per call (got {len(ai)})")
        if not confirm:
            raise RowDecisionError(f"deciding {len(ai)} AI rows at once needs confirm=true")
        low = [r["id"] for r in ai if r["low_confidence"]]
        if low:
            raise RowDecisionError(
                f"low-confidence AI rows are decided one at a time: {', '.join(low[:10])}"
                + (f" (+{len(low) - 10})" if len(low) > 10 else "")
            )
    now = utcnow().isoformat()
    stored = {
        r["id"]: {**d, "by": actor.id if actor is not None else None, "at": now, "method": r["method"]}
        for r, d in chosen
    }
    if stored:
        await storage.add_artifact(session, job.id, "review", {"decisions": stored})
        await publish_event(
            session,
            "council.review",
            "council_job",
            job.id,
            after={
                "rows": {i: {"action": d["action"], "method": d["method"]} for i, d in stored.items()},
                "count": len(stored),
                "confirmed_bulk": len(ai) > 1,
            },
            actor=actor,
        )
        from app.council.review import _status_after_review

        await _status_after_review(session, job, job.status)
    await session.commit()
    return {"saved": len(stored), "errors": errors}


__all__ = [
    "BULK_MAX",
    "RowDecisionError",
    "counts",
    "decide",
    "is_ai",
    "pending_ai",
    "review_items",
    "row_id",
    "rows",
]
