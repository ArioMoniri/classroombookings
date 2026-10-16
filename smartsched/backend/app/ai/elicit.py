"""Pre-generation constraint elicitation: free text (TR/EN) -> validated ``ProposedConstraint`` list.

Flow: catalogue + compact term context in a cached system prompt -> one strict ``propose_constraints``
tool call -> every proposal is resolved (names -> ids, :mod:`app.ai.resolve`) and validated against the
catalogue schema. Nothing is written to the database here; :func:`accept_proposals` does that after
the planner reviewed the list, and it re-verifies every id against the database (the accepted list
comes back from the browser and is not trusted either).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import catalog
from app.ai.client import AIClient, text_of, tool_uses
from app.ai.resolve import TermContext, load_term_context, resolve_proposal, resolve_section_edit
from app.ai.sanitize import strip_controls
from app.models import AIProposalDecision, ConstraintRow, ExamRequest, MeetingRequest, Room, Section
from app.schemas.ai import ElicitOut, ProposedConstraint, ProposedSectionEdit, SourceRef, UsageOut

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).parent / "prompts"
MAX_TOKENS = 16000
EFFORT = "medium"

_RULES_EN = (PROMPTS / "elicit.md").read_text(encoding="utf-8")
_MAPPING = (PROMPTS / "mapping.md").read_text(encoding="utf-8")


def build_system(ctx: TermContext, lang: str, intro: str | None = None) -> list[dict[str, Any]]:
    """Two cached blocks: ``intro`` (elicitation rules by default) + shared mapping rules + catalogue,
    then the term context (stable per term)."""
    language = "Turkish" if lang == "tr" else "English"
    rules = (intro if intro is not None else _RULES_EN).format(lang=language) + "\n" + _MAPPING.format(lang=language)
    cat = (
        "Catalogue of constraint kinds (kind [allowed hardness, default; params]: description, examples):\n"
        + catalog.catalog_prompt(lang)
    )
    return [
        {"type": "text", "text": rules + "\n" + cat, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "Term context:\n" + ctx.prompt_block(), "cache_control": {"type": "ephemeral"}},
    ]


SourceLookup = Callable[[int], SourceRef | None]


def model_source(source: str | None) -> str:
    """Effective source of a rule that passed through the AI layer: AI, UPLOAD or LEARNED. Anything else the
    browser sends back (``ADMIN`` ...) is treated as ``AI``: a proposal cannot launder itself into a planner rule."""
    src = (source or "").upper()
    return src if src in catalog.MODEL_SOURCES else "AI"


def enforce_source_policy(p: ProposedConstraint, source: str | None = None) -> ProposedConstraint:
    """Mark ``p`` rejected (with the reasons) when its source may not produce it (review D1 / P19-00b)."""
    issues = catalog.source_policy_issues(
        p.kind, p.params, p.hardness, model_source(source or p.source), weight=p.weight
    )
    if any(e.resolved_id is None for e in p.entities):
        # the model named a target that did not resolve: the planner fixes the name in review (accept
        # re-checks), so "untargeted" is not final yet
        issues = [i for i in issues if not i.startswith("untargeted")]
    if issues:
        p.status = "rejected"
        p.issues = [*p.issues, *[i for i in issues if i not in p.issues]]
    return p


def _validated_call_input(call: Any) -> tuple[dict[str, Any] | None, list[str]]:
    data = call.input if isinstance(call.input, dict) else None
    if data is None:
        return None, ["tool input is not an object"]
    issues = catalog.validate_tool_input(call.name, data)
    return (data if not issues else None), issues


async def propose(
    client: AIClient,
    ctx: TermContext,
    user_content: str | list[dict[str, Any]],
    lang: str,
    *,
    lookup: SourceLookup | None = None,
) -> tuple[list[ProposedConstraint], list[ProposedSectionEdit], list[dict[str, Any]], str]:
    """One strict ``propose_constraints`` round -> resolved proposals, section edits, unparsed, note."""
    message = await client.complete(
        system=build_system(ctx, lang),
        messages=[{"role": "user", "content": user_content}],
        tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
        max_tokens=MAX_TOKENS,
        effort=EFFORT,
        disable_parallel_tool_use=True,
    )
    note = text_of(message)
    calls = [c for c in tool_uses(message) if c.name == "propose_constraints"]
    if getattr(message, "stop_reason", None) == "max_tokens" and calls:
        # a truncated tool input may still parse; never act on it
        log.warning("elicit output truncated at max_tokens; dropping the partial tool call")
        return [], [], [{"text": "", "reason": "model output truncated; split the input"}], note
    proposals: list[ProposedConstraint] = []
    edits: list[ProposedSectionEdit] = []
    unparsed: list[dict[str, Any]] = []

    def src(raw: dict[str, Any]) -> SourceRef | None:
        ref = raw.get("source_ref")
        if lookup is not None and isinstance(ref, int) and not isinstance(ref, bool) and ref > 0:
            return lookup(ref)
        return lookup(0) if lookup is not None else None

    def tag(item: ProposedConstraint | ProposedSectionEdit, raw: dict[str, Any]) -> None:
        ref = src(raw)
        if ref is not None and ref.filename:
            item.source, item.source_ref = "UPLOAD", ref.to_ref()

    for call in calls:
        data, schema_issues = _validated_call_input(call)
        if data is None:
            log.warning("propose_constraints input failed validation (%d issues)", len(schema_issues))
            unparsed.append(
                {"text": "", "reason": "model output failed schema validation: " + "; ".join(schema_issues[:3])}
            )
            continue
        for raw in data.get("proposals") or []:
            try:
                p = resolve_proposal(ctx, dict(raw))
                tag(p, raw)
                proposals.append(enforce_source_policy(p))
            except Exception as exc:  # noqa: BLE001 - one bad proposal must not lose the others
                log.warning("proposal resolution failed: %s", type(exc).__name__)
                bad = ProposedConstraint(
                    kind=str(raw.get("kind") or "?"),
                    nl_text=str(raw.get("nl_text") or ""),
                    status="rejected",
                    issues=[f"resolution error: {type(exc).__name__}"],
                )
                tag(bad, raw)
                proposals.append(bad)
        for raw in data.get("section_edits") or []:
            try:
                e = resolve_section_edit(ctx, str(raw.get("op") or ""), dict(raw))
                tag(e, raw)
                edits.append(e)
            except Exception as exc:  # noqa: BLE001
                log.warning("section edit resolution failed: %s", type(exc).__name__)
        for u in data.get("unparsed") or []:
            ref = src(u)
            unparsed.append(
                {
                    "text": str(u.get("text") or ""),
                    "reason": str(u.get("reason") or ""),
                    "source_ref": ref.to_ref() if ref is not None else None,
                }
            )
    if not calls and not note:
        note = "No rules could be extracted."
    return proposals, edits, unparsed, note


async def elicit_constraints(
    session: AsyncSession, term_id: int, text: str, lang: str = "tr", *, client: AIClient
) -> ElicitOut:
    """``text`` -> proposals (validated, resolved, never applied). ``client`` from :func:`app.ai.client.get_client`."""
    ctx = await load_term_context(session, term_id)
    text = strip_controls(text)  # invisible / bidi characters can hide instructions from the reviewer
    content = (
        f"Planner's preferences ({'Turkish' if lang == 'tr' else 'English'}):\n\n{text}\n\n"
        "Call propose_constraints once with every rule and section edit you can map."
    )
    proposals, edits, unparsed, note = await propose(client, ctx, content, lang)
    if not proposals and not edits and not note:
        note = "Kural çıkarılamadı." if lang == "tr" else "No rules could be extracted."
    log.info(
        "elicit term=%s proposals=%d edits=%d unparsed=%d ok=%d",
        term_id,
        len(proposals),
        len(edits),
        len(unparsed),
        sum(p.status == "ok" for p in proposals),
    )
    return ElicitOut(
        proposals=proposals,
        section_edits=edits,
        unparsed=unparsed,
        assistant_message=note,
        usage=UsageOut(**client.usage.to_out()),
    )


# ---------------------------------------------------------------------------
# Accept (persist) - every id re-verified against the database
# ---------------------------------------------------------------------------


def check_proposal(p: ProposedConstraint, source: str | None = None) -> list[str]:
    """Problems that block persisting a proposal (unresolved names, schema violations, the per-source
    kind/hardness allowlist of :func:`app.ai.catalog.source_policy_issues`)."""
    issues = [f"unresolved {e.type} '{e.text}'" for e in p.entities if e.resolved_id is None]
    issues += catalog.validate_params(p.kind, p.params, p.hardness)
    issues += catalog.source_policy_issues(
        p.kind, p.params, p.hardness, model_source(source or p.source), weight=p.weight
    )
    if p.status == "rejected":
        issues.append("proposal was rejected")
    if p.hardness == "soft" and not 1 <= int(p.weight) <= 10:
        issues.append("weight must be 1..10")
    return issues


async def verify_ids(session: AsyncSession, term_id: int | None, params: dict[str, Any]) -> list[str]:
    """Every room / event id in ``params`` must exist (and belong to the term)."""
    issues: list[str] = []
    room_ids = [int(r) for r in params.get("room_ids") or []]
    if params.get("room_id") is not None:
        room_ids.append(int(params["room_id"]))
    if room_ids:
        found = set((await session.execute(select(Room.id).where(Room.id.in_(room_ids)))).scalars())
        issues += [f"room id {r} does not exist" for r in room_ids if r not in found]
    event_ids = [int(e) for e in params.get("event_ids") or []]
    if event_ids:
        q = select(MeetingRequest.id).join(Section, Section.id == MeetingRequest.section_id)
        q = q.where(MeetingRequest.id.in_(event_ids))
        if term_id is not None:
            q = q.where(Section.term_id == term_id)
        found = set((await session.execute(q)).scalars())
        qe = select(ExamRequest.id).where(ExamRequest.id.in_(event_ids))
        if term_id is not None:
            qe = qe.where(ExamRequest.term_id == term_id)
        found |= set((await session.execute(qe)).scalars())
        missing = [e for e in event_ids if e not in found]
        if missing:
            issues.append(f"event ids not in this term: {missing[:10]}")
    return issues


async def accept_proposals(
    session: AsyncSession,
    term_id: int | None,
    proposals: list[ProposedConstraint],
    *,
    user_id: int | None = None,
    run_id: int | None = None,
    source: str | None = None,
    commit: bool = True,
    declined: list[ProposedConstraint] | None = None,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Persist accepted proposals as ``ConstraintRow`` (source ``AI`` or ``UPLOAD``); returns (ids, rejected).

    Every proposal's outcome is kept in ``ai_proposal_decisions`` (``accepted`` / ``rejected`` with the reasons /
    ``declined`` for the ones the planner dismissed in review), the learning lane's input.

    The upload reference (``{"file": ..., "row": 12}``) is stored in the ``constraints.source_ref``
    column; the solver params stay free of metadata (a stray ``_source_ref`` key sent back by the
    browser is moved to the column too)."""
    rejected: list[dict[str, Any]] = []
    rows: list[ConstraintRow] = []
    decisions: list[tuple[AIProposalDecision, ConstraintRow]] = []

    def decide(p: ProposedConstraint, decision: str, reasons: list[str], src: str) -> AIProposalDecision:
        d = AIProposalDecision(
            term_id=term_id,
            run_id=run_id,
            decision=decision,
            kind=str(p.kind)[:64],
            params={k: v for k, v in dict(p.params or {}).items() if not str(k).startswith("_")},
            hardness=str(p.hardness or "hard")[:8],
            weight=int(p.weight or 1),
            source=src,
            source_ref=p.source_ref,
            nl_text=(p.nl_text or p.title or "")[:4000] or None,
            status=p.status,
            reasons=[str(r)[:500] for r in reasons][:20],
            created_by=user_id,
        )
        session.add(d)
        return d

    for i, p in enumerate(proposals):
        effective = model_source(source or p.source)
        issues = check_proposal(p, effective)
        if not issues:
            issues = await verify_ids(session, term_id, p.params)
        if not issues:
            # round-1 R1-M-03: an approved AI / upload / import pin never seats a class in a room that cannot hold it
            # (no override on this path: an administrator writes such a pin by hand, with a reason)
            from app.services import pin_guard

            short = await pin_guard.shortfalls(session, p.kind, p.params, p.hardness, term_id=term_id)
            if short:
                issues = [pin_guard.refusal(short, overridable=False)["message_tr"]]
        if issues:
            rejected.append({"index": i, "kind": p.kind, "issues": issues})
            decide(p, "rejected", issues, effective)
            continue
        params = dict(p.params)
        legacy_ref = params.pop("_source_ref", None)
        source_ref = p.source_ref or (legacy_ref if isinstance(legacy_ref, dict) else None)
        row = ConstraintRow(
            term_id=term_id if run_id is None else None,
            run_id=run_id,
            kind=p.kind,
            params=params,
            hardness=p.hardness,
            weight=max(1, min(10, int(p.weight))),
            source=effective,
            nl_text=(p.nl_text or p.title or "")[:4000] or None,
            enabled=True,
            created_by=user_id,
            source_ref=source_ref,
        )
        session.add(row)
        rows.append(row)
        decisions.append((decide(p, "accepted", [], effective), row))
    for p in declined or []:
        decide(p, "declined", ["declined by the planner in review"], model_source(source or p.source))
    await session.flush()
    for d, made in decisions:
        d.constraint_id = made.id
    created = [r.id for r in rows]
    if commit:
        await session.commit()
    return created, rejected


__all__ = [
    "accept_proposals",
    "enforce_source_policy",
    "model_source",
    "build_system",
    "check_proposal",
    "elicit_constraints",
    "propose",
    "verify_ids",
]
