"""Learning versions, the nightly refresh, calibration drafts and per-habit controls (adaptive scheduling AS-13;
audit RF-07; docs/research/2026-10-17-adaptive-scheduling.md §3.3).

* **Versions.** Every refresh (manual, nightly, a revert) writes a ``learning_versions`` row for the term: counts,
  a SHA-256 checksum of the term's active prior set and the diff against the previous version (new / dropped /
  changed suggestions, by scope, no names). The prior set itself is kept in ``learned_prior_snapshots`` (compact
  JSON). "Bu sürüme dön" (:func:`revert`) restores a snapshot byte for byte (same checksum) and **pins** the term
  so lazy recomputes keep it until the next manual refresh; accepted rules are never touched (they have their own
  restore).
* **Nightly refresh.** 03:15 Europe/Istanbul, the active term only, beside the purge jobs; setting
  ``learning.nightly_refresh`` (default on). It only changes suggestions, never rules; a pinned term is skipped.
* **Calibration.** Per suggestion class (attribute x confidence band) a Beta(1 + accepted, 1 + rejected) posterior;
  classes with >= 5 decisions whose posterior mean is under 0.5 get a draft "öğrenme ayarı": raise the class's
  minimum confidence to the next band. Nothing applies until an admin applies it (``learning.min_confidence``).
* **Per-habit controls (RF-07).** One learned habit (subject x attribute x value) can be *disabled* (never
  suggested again, in any term), *corrected* (the planner names the right value: the wrong one is not suggested
  and the right one gets correction evidence), or *tuned* (the weight a later accept uses, 1..5). Stored in the
  setting ``learning.habit_overrides`` (scopes only, no names); audited; undone with ``clear``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearnedPrior, LearnedPriorSnapshot, LearningVersion, Setting, Term
from app.models.base import utcnow

log = logging.getLogger("smartsched.learning.versions")

OVERRIDES_KEY = "learning.habit_overrides"
MIN_CONF_KEY = "learning.min_confidence"
NIGHTLY_KEY = "learning.nightly_refresh"
PIN_PREFIX = "learning.pin."
HABIT_STATES = ("disabled", "corrected", "tuned")
#: the prior columns a snapshot keeps (``computed_at`` is a clock, not content)
SNAP_FIELDS = (
    "id",
    "subject_type",
    "subject_key",
    "attribute",
    "value",
    "score",
    "support",
    "total",
    "terms_count",
    "confidence",
    "suggestible",
    "active",
    "proposal",
    "explanation",
    "evidence",
)
BANDS = ((0.8, "high"), (0.6, "medium"), (0.0, "low"))
MIN_DECISIONS = 5
NIGHTLY_AT = (3, 15)
TZ = "Europe/Istanbul"


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


class VersionError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _err(status: int, code: str, en: str, tr: str) -> VersionError:
    return VersionError(status, {"code": code, "message": en, "message_en": en, "message_tr": tr})


# ------------------------------------------------------------------------------------------------ settings


async def _json_setting(session: AsyncSession, key: str, default: Any) -> Any:
    row = await session.get(Setting, key)
    if row is None or not row.value:
        return default
    try:
        return json.loads(row.value)
    except ValueError:
        return default


async def _put_setting(session: AsyncSession, key: str, value: Any) -> None:
    row = await session.get(Setting, key)
    text = None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)
    if row is None:
        session.add(Setting(key=key, value=text, is_secret=False))
    else:
        row.value = text
    await session.flush()


def scope_key(st: str, sk: str, attr: str, val: str) -> str:
    return f"{st}|{sk}|{attr}|{val}"


async def habit_overrides(session: AsyncSession) -> dict[str, dict[str, Any]]:
    data = await _json_setting(session, OVERRIDES_KEY, {})
    return data if isinstance(data, dict) else {}


async def min_confidence(session: AsyncSession) -> dict[str, float]:
    data = await _json_setting(session, MIN_CONF_KEY, {})
    return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}


async def pinned(session: AsyncSession, term_id: int) -> int | None:
    row = await session.get(Setting, f"{PIN_PREFIX}{term_id}")
    try:
        return int(row.value) if row is not None and row.value else None
    except ValueError:
        return None


async def unpin(session: AsyncSession, term_id: int) -> None:
    row = await session.get(Setting, f"{PIN_PREFIX}{term_id}")
    if row is not None:
        row.value = None
        await session.flush()


async def nightly_enabled(session: AsyncSession) -> bool:
    row = await session.get(Setting, NIGHTLY_KEY)
    return row is None or row.value is None or str(row.value).strip().lower() not in ("0", "false", "off", "no")


# ------------------------------------------------------------------------------------------------ snapshots


def _jsonable(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    return v


async def prior_rows(session: AsyncSession, term_id: int) -> list[dict[str, Any]]:
    """The term's active prior rows (``active``), as canonical dicts sorted by id."""
    cols = [getattr(LearnedPrior, f) for f in SNAP_FIELDS]
    q = select(*cols).where(LearnedPrior.term_id == term_id, LearnedPrior.active.is_(True)).order_by(LearnedPrior.id)
    return [{f: _jsonable(v) for f, v in zip(SNAP_FIELDS, row, strict=True)} for row in (await session.execute(q)).all()]


def checksum(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _scope(r: Mapping[str, Any]) -> str:
    return scope_key(r["subject_type"], r["subject_key"], r["attribute"], r["value"])


def diff(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    """New / dropped / changed suggestible priors between two prior sets (scopes and numbers only)."""
    o = {_scope(r): r for r in old if r.get("suggestible")}
    n = {_scope(r): r for r in new if r.get("suggestible")}

    def brief(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "scope": _scope(r),
            "subject_type": r["subject_type"],
            "attribute": r["attribute"],
            "value": r["value"],
            "confidence": r["confidence"],
            "support": r["support"],
            "value_label": (r.get("evidence") or {}).get("value_label"),
        }

    changed = [
        {**brief(n[k]), "confidence_before": o[k]["confidence"], "support_before": o[k]["support"]}
        for k in sorted(set(o) & set(n))
        if (o[k]["confidence"], o[k]["support"], o[k]["score"]) != (n[k]["confidence"], n[k]["support"], n[k]["score"])
    ]
    return {
        "new": [brief(n[k]) for k in sorted(set(n) - set(o))][:500],
        "dropped": [brief(o[k]) for k in sorted(set(o) - set(n))][:500],
        "changed": changed[:500],
        "counts": {"new": len(set(n) - set(o)), "dropped": len(set(o) - set(n)), "changed": len(changed)},
    }


async def _last(session: AsyncSession, term_id: int) -> LearningVersion | None:
    return (
        await session.execute(
            select(LearningVersion)
            .where(LearningVersion.term_id == term_id)
            .order_by(LearningVersion.number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _snapshot(session: AsyncSession, version_id: int) -> list[dict[str, Any]]:
    snap = await session.get(LearnedPriorSnapshot, version_id)
    return list(snap.rows or []) if snap is not None else []


async def record_version(
    session: AsyncSession, term_id: int, *, trigger: str, actor: Any = None, restored_from: int | None = None
) -> LearningVersion:
    """Write the version row + snapshot of the term's current prior set."""
    from app.models import LearnedObservation

    rows = await prior_rows(session, term_id)
    prev = await _last(session, term_id)
    old = await _snapshot(session, prev.id) if prev is not None else []
    n_obs = (
        await session.execute(
            select(func.count()).where(LearnedObservation.reset_id.is_(None), LearnedObservation.term_id == term_id)
        )
    ).scalar_one()
    v = LearningVersion(
        term_id=term_id,
        number=(prev.number + 1) if prev is not None else 1,
        trigger=trigger,
        created_by=getattr(actor, "id", None),
        observations=int(n_obs or 0),
        priors=len(rows),
        suggestible=sum(1 for r in rows if r.get("suggestible")),
        checksum=checksum(rows),
        diff=diff(old, rows),
        restored_from=restored_from,
        created_at=utcnow(),
    )
    session.add(v)
    await session.flush()
    session.add(LearnedPriorSnapshot(version_id=v.id, term_id=term_id, rows=rows))
    await session.flush()
    return v


def version_out(v: LearningVersion) -> dict[str, Any]:
    trig = {"manual": ("Elle", "Manual"), "nightly": ("Gece", "Nightly"), "revert": ("Geri dönüş", "Revert")}
    tr, en = trig.get(v.trigger, (v.trigger, v.trigger))
    return {
        "id": v.id,
        "term_id": v.term_id,
        "number": v.number,
        "trigger": v.trigger,
        "trigger_label": _t(tr, en),
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "created_by": v.created_by,
        "observations": v.observations,
        "priors": v.priors,
        "suggestible": v.suggestible,
        "checksum": v.checksum,
        "diff": v.diff,
        "restored_from": v.restored_from,
    }


async def list_versions(session: AsyncSession, term_id: int) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(LearningVersion)
                .where(LearningVersion.term_id == term_id)
                .order_by(LearningVersion.number.desc())
            )
        ).scalars()
    )
    pin = await pinned(session, term_id)
    return {
        "term_id": term_id,
        "versions": [version_out(v) for v in rows],
        "pinned_version_id": pin,
        "nightly_refresh": await nightly_enabled(session),
        "needs": None
        if rows
        else _t(
            "Henüz öğrenme sürümü yok: Öğrenmeyi yenile ya da gece yenilemesini bekleyin",
            "No learning version yet: refresh learning or wait for the nightly refresh",
        ),
    }


async def refresh_term(session: AsyncSession, term_id: int, *, trigger: str = "manual", actor: Any = None) -> dict[str, Any]:
    """Extract + recompute the term's priors and record a version (a manual refresh lifts a revert's pin)."""
    from app.services import learning

    if trigger == "manual":
        await unpin(session, term_id)
    out = await learning.refresh(session, term_id)
    v = await record_version(session, term_id, trigger=trigger, actor=actor)
    out["version"] = version_out(v)
    return out


async def revert(session: AsyncSession, version_id: int, actor: Any) -> dict[str, Any]:
    """"Bu sürüme dön": the term's prior set becomes the snapshot of ``version_id`` (same checksum); priors that
    were not in it are deactivated (ids kept for the decisions that point at them). Accepted rules stay."""
    from app.services import learning
    from app.services.events import publish_event

    v = await session.get(LearningVersion, version_id)
    if v is None:
        raise _err(404, "version_not_found", "learning version not found", "öğrenme sürümü bulunamadı")
    rows = await _snapshot(session, v.id)
    want = {int(r["id"]): r for r in rows}
    existing = {
        int(pid): (bool(active), bool(sugg))
        for pid, active, sugg in (
            await session.execute(
                select(LearnedPrior.id, LearnedPrior.active, LearnedPrior.suggestible).where(
                    LearnedPrior.term_id == v.term_id
                )
            )
        ).all()
    }
    now = utcnow()
    updates = [{**r, "computed_at": now} for pid, r in want.items() if pid in existing]
    fresh = [{**r, "term_id": v.term_id, "computed_at": now} for pid, r in want.items() if pid not in existing]
    off = [
        {"id": pid, "active": False, "suggestible": False, "computed_at": now}
        for pid, (active, sugg) in existing.items()
        if pid not in want and (active or sugg)
    ]
    for chunk in range(0, len(updates), 2000):
        await session.execute(update(LearnedPrior), updates[chunk : chunk + 2000])
    for chunk in range(0, len(off), 2000):
        await session.execute(update(LearnedPrior), off[chunk : chunk + 2000])
    for chunk in range(0, len(fresh), 2000):
        await session.execute(insert(LearnedPrior), fresh[chunk : chunk + 2000])
    await session.flush()
    await _put_setting(session, f"{PIN_PREFIX}{v.term_id}", v.id)
    learning._forget(v.term_id)
    nv = await record_version(session, v.term_id, trigger="revert", actor=actor, restored_from=v.number)
    await publish_event(
        session,
        "learning.version_revert",
        "learning_version",
        nv.id,
        after={"term_id": v.term_id, "restored_from": v.number, "checksum": nv.checksum},
        actor=actor,
        term_id=v.term_id,
    )
    return {"restored": version_out(v), "version": version_out(nv), "identical": nv.checksum == v.checksum}


async def scrub_person(session: AsyncSession, keys: list[tuple[str, str]]) -> int:
    """KVKK erasure: remove a person's priors from every snapshot (a revert must never bring them back)."""
    want = {(st, sk) for st, sk in keys}
    n = 0
    for snap in (await session.execute(select(LearnedPriorSnapshot))).scalars():
        rows = [r for r in snap.rows or [] if (r.get("subject_type"), r.get("subject_key")) not in want]
        if len(rows) != len(snap.rows or []):
            n += len(snap.rows or []) - len(rows)
            snap.rows = rows
    await session.flush()
    return n


# ------------------------------------------------------------------------------------------------ calibration


def band_of(conf: float) -> str:
    return next(name for lo, name in BANDS if conf >= lo)


def beta_summary(acc: int, rej: int) -> dict[str, float]:
    a, b = 1 + acc, 1 + rej
    mean = a / (a + b)
    sd = (a * b / ((a + b) ** 2 * (a + b + 1))) ** 0.5
    return {"mean": round(mean, 3), "lower": round(max(0.0, mean - 1.2816 * sd), 3), "n": acc + rej}


async def calibration(session: AsyncSession) -> dict[str, Any]:
    """Accept / reject per class (attribute x confidence band) with its Beta posterior, and draft proposals."""
    from app.models.learning import SuggestionFeedback

    rows = (
        await session.execute(
            select(SuggestionFeedback.action, LearnedPrior.attribute, LearnedPrior.confidence)
            .join(LearnedPrior, LearnedPrior.id == SuggestionFeedback.prior_id)
            .where(SuggestionFeedback.action.in_(("ACCEPT", "REJECT")), SuggestionFeedback.reset_id.is_(None))
        )
    ).all()
    counts: dict[tuple[str, str], list[int]] = {}
    for action, attr, conf in rows:
        c = counts.setdefault((str(attr), band_of(float(conf or 0.0))), [0, 0])
        c[0 if action == "ACCEPT" else 1] += 1
    current = await min_confidence(session)
    classes = []
    proposals = []
    for (attr, band), (acc, rej) in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        post = beta_summary(acc, rej)
        classes.append({"attribute": attr, "band": band, "accepted": acc, "rejected": rej, "posterior": post})
        if post["n"] >= MIN_DECISIONS and post["mean"] < 0.5 and band != "high":
            target = 0.8 if band == "medium" else 0.6
            if current.get(attr, 0.6) < target:
                proposals.append(
                    {
                        "attribute": attr,
                        "band": band,
                        "min_confidence": target,
                        "current": current.get(attr, 0.6),
                        "status": "draft",
                        "explanation": _t(
                            f"{attr} önerilerinde {band} güven bandında {post['n']} kararın {rej}'i ret; "
                            f"kabul olasılığı {post['mean']:.2f}. Öneri: en düşük güveni {target:.1f} yap.",
                            f"{attr} suggestions in the {band} band: {rej} of {post['n']} decisions rejected; "
                            f"acceptance {post['mean']:.2f}. Proposal: raise the minimum confidence to {target:.1f}.",
                        ),
                    }
                )
    order = sorted(classes, key=lambda c: (-c["posterior"]["mean"], c["attribute"], c["band"]))
    return {
        "classes": classes,
        "display_order": [f"{c['attribute']}:{c['band']}" for c in order],
        "proposals": proposals,
        "applied": current,
        "confidence": "none" if not classes else ("low" if sum(c["posterior"]["n"] for c in classes) < 20 else "medium"),
        "needs": None
        if classes
        else _t("Henüz kabul ya da ret kararı yok", "No accept or reject decision yet"),
    }


async def apply_calibration(session: AsyncSession, attribute: str, value: float | None, actor: Any) -> dict[str, Any]:
    """An admin applies (or with ``None`` clears) a minimum confidence for one attribute; the next recompute
    uses it."""
    from app.models.learning import ATTRIBUTES
    from app.services.events import publish_event

    if attribute not in ATTRIBUTES:
        raise _err(422, "attribute", f"attribute: one of {', '.join(ATTRIBUTES)}", f"öznitelik: {', '.join(ATTRIBUTES)}")
    if value is not None and not 0.5 <= float(value) <= 0.99:
        raise _err(422, "min_confidence", "min_confidence must be 0.5..0.99", "en düşük güven 0,5 ile 0,99 arasında olmalı")
    cur = await min_confidence(session)
    before = dict(cur)
    if value is None:
        cur.pop(attribute, None)
    else:
        cur[attribute] = round(float(value), 2)
    await _put_setting(session, MIN_CONF_KEY, cur)
    await publish_event(session, "learning.calibration_apply", "setting", MIN_CONF_KEY, before=before, after=cur, actor=actor)
    from app.services import learning

    learning._forget()
    return {"applied": cur}


# ------------------------------------------------------------------------------------------------ habits (RF-07)


async def set_habit(
    session: AsyncSession, prior_id: int, *, state: str | None, actor: Any, reason: str | None = None,
    value: str | None = None, weight: int | None = None,
) -> dict[str, Any]:
    """Disable / correct / tune one learned habit (or ``state=None`` to clear). ``corrected`` adds correction
    evidence for ``value`` (+2, like a planner correction) so the right habit is learned, not just the wrong one
    hidden."""
    from app.models import LearnedObservation
    from app.services import learning
    from app.services.events import publish_event

    p = await session.get(LearnedPrior, prior_id)
    if p is None:
        raise _err(404, "prior_not_found", "learned habit not found", "öğrenilmiş alışkanlık bulunamadı")
    key = scope_key(p.subject_type, p.subject_key, p.attribute, p.value)
    data = await habit_overrides(session)
    before = data.get(key)
    if state is None:
        data.pop(key, None)
    else:
        if state not in HABIT_STATES:
            raise _err(422, "state", "state: disabled, corrected or tuned", "durum: disabled, corrected ya da tuned")
        entry: dict[str, Any] = {
            "state": state,
            "reason": (reason or "").strip()[:500] or None,
            "by": getattr(actor, "id", None),
            "at": utcnow().isoformat(),
        }
        if state == "tuned":
            if weight is None or not 1 <= int(weight) <= learning.MAX_WEIGHT:
                raise _err(422, "weight", f"weight must be 1..{learning.MAX_WEIGHT}", f"ağırlık 1 ile {learning.MAX_WEIGHT} arasında olmalı")
            entry["weight"] = int(weight)
        if state == "corrected":
            val = (value or "").strip()
            if not val or val == p.value:
                raise _err(422, "value", "a correction names a different value", "düzeltme farklı bir değer vermeli")
            entry["to"] = val[:64]
            next_id = int(
                (
                    await session.execute(
                        select(func.coalesce(func.max(LearnedObservation.source_id), 0)).where(
                            LearnedObservation.source_table == "habit_corrections"
                        )
                    )
                ).scalar_one()
            ) + 1
            session.add(
                LearnedObservation(
                    ts=utcnow(),
                    term_id=p.term_id,
                    kind="correction_to",
                    subject_type=p.subject_type,
                    subject_key=p.subject_key,
                    attribute=p.attribute,
                    value=val[:64],
                    sign=1,
                    weight=2,
                    source_table="habit_corrections",
                    source_id=next_id,
                    actor_id=getattr(actor, "id", None),
                    detail={"corrects": p.value, "prior_id": p.id},
                )
            )
        data[key] = entry
    await _put_setting(session, OVERRIDES_KEY, data)
    await publish_event(
        session,
        "learning.habit",
        "learned_prior",
        p.id,
        before={"override": before} if before else None,
        after={"scope": key, "override": data.get(key)},
        actor=actor,
        term_id=p.term_id,
        reason=reason,
    )
    await learning.recompute_priors(session, p.term_id, subjects=[(p.subject_type, p.subject_key)])
    learning._forget(p.term_id)
    return {"prior_id": p.id, "scope": key, "override": data.get(key)}


async def list_habits(session: AsyncSession) -> list[dict[str, Any]]:
    data = await habit_overrides(session)
    return [{"scope": k, **v} for k, v in sorted(data.items())]


# ------------------------------------------------------------------------------------------------ nightly job

_task: asyncio.Task[None] | None = None


def seconds_until(now: datetime, hour: int = NIGHTLY_AT[0], minute: int = NIGHTLY_AT[1]) -> float:
    """Seconds from ``now`` (local wall clock) to the next ``hour:minute``."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def nightly_once() -> dict[str, Any]:
    """Refresh the active term (unless switched off or pinned by a revert)."""
    from app.core.db import get_session_factory

    async with get_session_factory()() as session:
        if not await nightly_enabled(session):
            return {"skipped": "off"}
        term = (await session.execute(select(Term).where(Term.is_active.is_(True)).limit(1))).scalar_one_or_none()
        if term is None:
            return {"skipped": "no_active_term"}
        if await pinned(session, term.id):
            return {"skipped": "pinned", "term_id": term.id}
        out = await refresh_term(session, term.id, trigger="nightly")
        await session.commit()
        return {"term_id": term.id, "version": out["version"]["number"]}


async def _loop() -> None:
    from zoneinfo import ZoneInfo

    while True:
        now = datetime.now(ZoneInfo(TZ)).replace(tzinfo=None)
        await asyncio.sleep(seconds_until(now))
        try:
            log.info("learning nightly refresh: %s", await nightly_once())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing refresh never stops the loop or the app
            log.exception("learning nightly refresh failed")


def start_nightly_job() -> None:
    """Started from ``app.main`` lifespan next to the purge jobs (not in the test environment)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="learning-nightly")


async def stop_nightly_job() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None


__all__ = [
    "apply_calibration",
    "calibration",
    "checksum",
    "diff",
    "habit_overrides",
    "list_habits",
    "list_versions",
    "min_confidence",
    "nightly_once",
    "pinned",
    "prior_rows",
    "record_version",
    "refresh_term",
    "revert",
    "scrub_person",
    "seconds_until",
    "set_habit",
    "start_nightly_job",
    "stop_nightly_job",
]
