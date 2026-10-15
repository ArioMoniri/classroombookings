"""Rule miner: notes, comments and memo text -> constraint proposals from the existing catalogue.

The miner reuses the elicitation stack (:mod:`app.ai.elicit`): the same system prompt, constraint
catalogue and strict ``propose_constraints`` tool. The difference is the context block. At ingestion
time no term exists yet, so it is built from the council's reconciled records (rooms, programmes,
course codes) as transient ORM objects that are never added to a session.

Proposals are stored *raw*, in the model's name-based form. They are resolved to ids only when the
job is committed into a term (:mod:`app.council.commit` -> :func:`app.ai.resolve.resolve_proposal`),
because ids exist only then. Without an API key the miner proposes nothing. It lists the rule-like
texts for the reviewer and says that the AI step was skipped.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai import catalog
from app.ai.client import AIClient, text_of, tool_uses
from app.ai.elicit import MAX_TOKENS, build_system
from app.ai.resolve import TermContext
from app.models import Course, Program, Room, Term

log = logging.getLogger(__name__)

CHUNK_CHARS = 10000
MAX_CHUNKS = 8
MAX_TEXTS = 600


def context_from_dataset(dataset: dict[str, Any], term_code: str = "NEW", week_count: int = 14) -> TermContext:
    """A :class:`TermContext` built from council records, for the prompt only (no ids)."""
    term = Term(code=term_code, name=term_code, week_count=week_count)
    rooms = [
        Room(
            code=r["key"],
            display_name=r.get("label") or r["code"],
            capacity=int(r.get("capacity") or 0),
            exam_capacity=int(r.get("exam_capacity") or 0),
            tags=list(r.get("tags") or []),
        )
        for r in dataset.get("rooms", [])[:400]
    ]
    programs = [Program(name=p["name"], canonical_name=p["canonical"]) for p in dataset.get("programs", [])[:300]]
    courses = [
        Course(code=c["code"], display_code=c["code"], name=c.get("name")) for c in dataset.get("courses", [])[:1500]
    ]
    return TermContext(term, [], rooms, programs, courses, [])


def _chunks(texts: list[dict[str, Any]]) -> list[list[tuple[int, dict[str, Any]]]]:
    out: list[list[tuple[int, dict[str, Any]]]] = []
    cur: list[tuple[int, dict[str, Any]]] = []
    size = 0
    for i, t in enumerate(texts, start=1):
        line = len(t["text"]) + 40
        if cur and size + line > CHUNK_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append((i, t))
        size += line
    if cur:
        out.append(cur)
    return out


async def mine(
    client: AIClient | None,
    texts: list[dict[str, Any]],
    dataset: dict[str, Any],
    *,
    lang: str = "en",
    model: str | None = None,
) -> dict[str, Any]:
    """``texts`` = rule_text records -> {proposals, section_edits, unparsed, messages, texts}."""
    texts = texts[:MAX_TEXTS]
    result: dict[str, Any] = {"proposals": [], "section_edits": [], "unparsed": [], "messages": [], "texts": len(texts)}
    if not texts:
        return result
    if client is None:
        result["messages"].append(
            f"{len(texts)} rule-like text(s) found; turning them into constraints needs the AI model "
            "(no Anthropic API key configured). They are listed for review; add them as rules in the "
            "Generator Studio or configure a key and re-run."
        )
        result["pending"] = [
            {"text": t["text"], "course_codes": t["course_codes"], "source": t["source"]} for t in texts
        ]
        return result
    ctx = context_from_dataset(dataset)
    system = build_system(ctx, lang)
    chunks = _chunks(texts)
    if len(chunks) > MAX_CHUNKS:
        result["messages"].append(f"only the first {MAX_CHUNKS} parts of the rule text were analysed")
        chunks = chunks[:MAX_CHUNKS]
    for part, chunk in enumerate(chunks, start=1):
        by_n = {n: t for n, t in chunk}
        lines = "\n".join(
            f"[{n}] " + (f"({', '.join(t['course_codes'][:6])}) " if t.get("course_codes") else "") + t["text"][:700]
            for n, t in chunk
        )
        content = (
            f"Notes and memos from the institution's files (part {part} of {len(chunks)}). Each line is tagged "
            "[n]; codes in parentheses are the courses the note belongs to. Set source_ref=n. "
            "Lines that only restate a normal timetable entry produce nothing.\n\n"
            f"<document>\n{lines}\n</document>\n\nCall propose_constraints once with every rule you can map."
        )
        message = await client.complete(
            system=system,
            messages=[{"role": "user", "content": content}],
            tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
            max_tokens=MAX_TOKENS,
            effort="medium",
            disable_parallel_tool_use=True,
            model=model or None,
        )
        note = text_of(message)
        if note:
            result["messages"].append(note[:1000])
        calls = [c for c in tool_uses(message) if c.name == "propose_constraints"]
        if getattr(message, "stop_reason", None) == "max_tokens":
            result["messages"].append(f"part {part}: model output truncated; discarded")
            continue
        for call in calls:
            data = call.input if isinstance(call.input, dict) else None
            issues = catalog.validate_tool_input(call.name, data) if data is not None else ["not an object"]
            if issues or data is None:
                result["messages"].append(f"part {part}: model output failed validation: {'; '.join(issues[:3])}")
                continue
            for key in ("proposals", "section_edits", "unparsed"):
                for raw in data.get(key) or []:
                    ref = raw.get("source_ref")
                    src = by_n[ref]["source"] if isinstance(ref, int) and ref in by_n else None
                    text = by_n[ref]["text"] if isinstance(ref, int) and ref in by_n else None
                    result[key].append({**raw, "_source": src, "_text": text})
    log.info(
        "rule miner: texts=%d chunks=%d proposals=%d edits=%d",
        len(texts),
        len(chunks),
        len(result["proposals"]),
        len(result["section_edits"]),
    )
    return result


__all__ = ["context_from_dataset", "mine"]
