"""Pre-generation constraint elicitation: free text (TR/EN) -> validated ``ProposedConstraint`` list.

Flow: catalogue + compact term context in a cached system prompt -> one strict ``propose_constraints``
tool call -> every proposal is resolved (names -> ids, :mod:`app.ai.resolve`) and validated against the
catalogue schema. Nothing is written to the database here; :func:`accept_proposals` does that after
the planner reviewed the list.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import catalog
from app.ai.client import AIClient, text_of, tool_uses
from app.ai.resolve import TermContext, load_term_context, resolve_proposal
from app.models import ConstraintRow
from app.schemas.ai import ElicitOut, ProposedConstraint, UsageOut

log = logging.getLogger(__name__)

MAX_TOKENS = 8000

_RULES_EN = """You are SmartSched's constraint elicitation assistant for a university room-planning office.
Turn the planner's free text into typed rules from the catalogue below by calling `propose_constraints` exactly once.

Rules:
- Name rooms, programmes, courses and instructors exactly as written by the planner (e.g. "A 206", "Psikoloji", "PHAR 240"). You never see or invent database ids; the server resolves names.
- One proposal per rule; copy the originating sentence into `nl_text`; explain the mapping in `rationale` in the planner's language ({lang}).
- Hardness: "must/never/only/sadece/olmasın/zorunlu" => hard; "prefer/should/keep/kalsın/tercihen/mümkünse" => soft with weight 1-10 (default 5). Overlap kinds are always hard.
- Times: periods are 1..18 (P1 08:30-09:10 ... P11 16:50-17:30, P12 17:30-18:00, P13 18:00-18:40 ... P18 22:10-22:50). "after 17:30 no lectures" => day_window latest=11. "morning" => periods 1-5, "afternoon" => 6-11, "evening (İÖ)" => 12-18.
- Days: 1=Monday/Pazartesi ... 5=Friday/Cuma, 6=Saturday, 7=Sunday.
- Dates like "23 Şubat" / "from 23 Feb" => `from_date` as ISO date in the term's year; "last 7 weeks" => `last_n_weeks`=7; the server converts to week indexes.
- Class year: "1. sınıf" => class_years [1]; "ilk yıl"/"first-year" => [1]; "hemşirelik 1. sınıf" => program_name "Hemşirelik", class_years [1].
- "TIP rooms only for medicine" => room_tags hard with forbidden_tags ["TIP"] and selector match "" (all events) - the medicine programme itself keeps access via its own TIP requests; say so in the rationale.
- "Keep pharmacy in C block Mondays" => building_preference soft, program_name "Eczacılık", building "C", days [1].
- "PHAR 240 moves to A 206 from 23 Feb" => room_pin hard, course_codes ["PHAR 240"], room_codes ["A 206"], from_date.
- "NRS 450 only last 7 weeks" => this is a week pattern, not a room rule: put it in `unparsed` with reason "week pattern - edit the meeting request's weeks" unless a room is also named.
- If a sentence cannot be expressed with the catalogue, put it in `unparsed` with a short reason; never force a wrong kind.
- Confidence: 1.0 when every name is explicit and the kind is unambiguous; lower when you guessed.
"""


def build_system(ctx: TermContext, lang: str) -> list[dict[str, Any]]:
    """Two blocks: rules + catalogue (stable, cached), term context (stable per term, cached)."""
    rules = _RULES_EN.format(lang="Turkish" if lang == "tr" else "English")
    cat = "Catalogue of constraint kinds (kind [allowed hardness, default; params]: description, examples):\n" + catalog.catalog_prompt(lang)
    return [
        {"type": "text", "text": rules + "\n" + cat, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "Term context:\n" + ctx.prompt_block(), "cache_control": {"type": "ephemeral"}},
    ]


async def elicit_constraints(
    session: AsyncSession, term_id: int, text: str, lang: str = "tr", *, client: AIClient
) -> ElicitOut:
    """``text`` -> proposals (validated, resolved, never applied). ``client`` from :func:`app.ai.client.get_client`."""
    ctx = await load_term_context(session, term_id)
    message = await client.complete(
        system=build_system(ctx, lang),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Planner's preferences ({'Turkish' if lang == 'tr' else 'English'}):\n\n{text}\n\n"
                    "Call propose_constraints once with every rule you can map."
                ),
            }
        ],
        tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
        max_tokens=MAX_TOKENS,
        disable_parallel_tool_use=True,
    )
    calls = [c for c in tool_uses(message) if c.name == "propose_constraints"]
    proposals: list[ProposedConstraint] = []
    unparsed: list[dict[str, str]] = []
    for call in calls:
        data: dict[str, Any] = dict(call.input or {})
        for raw in data.get("proposals") or []:
            try:
                proposals.append(resolve_proposal(ctx, dict(raw)))
            except Exception as exc:  # noqa: BLE001 - one bad proposal must not lose the others
                log.warning("proposal resolution failed: %s", type(exc).__name__)
                proposals.append(
                    ProposedConstraint(kind=str(raw.get("kind") or "?"), nl_text=str(raw.get("nl_text") or ""), status="rejected", issues=[f"resolution error: {type(exc).__name__}"])
                )
        for u in data.get("unparsed") or []:
            unparsed.append({"text": str(u.get("text") or ""), "reason": str(u.get("reason") or "")})
    note = text_of(message)
    if not calls:
        note = note or ("Kural çıkarılamadı." if lang == "tr" else "No rules could be extracted.")
    log.info("elicit term=%s proposals=%d unparsed=%d ok=%d", term_id, len(proposals), len(unparsed), sum(p.status == "ok" for p in proposals))
    return ElicitOut(proposals=proposals, unparsed=unparsed, assistant_message=note, usage=UsageOut(**{k: v for k, v in client.usage.to_dict().items() if k != "type"}))


def check_proposal(p: ProposedConstraint) -> list[str]:
    """Problems that block persisting a proposal (unresolved names, schema violations)."""
    issues = [f"unresolved {e.type} '{e.text}'" for e in p.entities if e.resolved_id is None and e.type != "date"]
    issues += catalog.validate_params(p.kind, p.params, p.hardness)
    if p.status == "rejected":
        issues.append("proposal was rejected")
    return issues


async def accept_proposals(
    session: AsyncSession,
    term_id: int | None,
    proposals: list[ProposedConstraint],
    *,
    user_id: int | None = None,
    run_id: int | None = None,
    source: str = "AI",
) -> tuple[list[int], list[dict[str, Any]]]:
    """Persist the proposals the planner accepted as ``ConstraintRow(source=AI)``; returns (ids, rejected)."""
    created: list[int] = []
    rejected: list[dict[str, Any]] = []
    rows: list[ConstraintRow] = []
    for i, p in enumerate(proposals):
        issues = check_proposal(p)
        if issues:
            rejected.append({"index": i, "kind": p.kind, "issues": issues})
            continue
        row = ConstraintRow(
            term_id=term_id if run_id is None else None,
            run_id=run_id,
            kind=p.kind,
            params=p.params,
            hardness=p.hardness,
            weight=max(1, min(10, int(p.weight))),
            source=source,
            nl_text=p.nl_text or p.title,
            enabled=True,
            created_by=user_id,
        )
        session.add(row)
        rows.append(row)
    if rows:
        await session.flush()
        created = [r.id for r in rows]
        await session.commit()
    return created, rejected


__all__ = ["accept_proposals", "build_system", "check_proposal", "elicit_constraints"]
