"""Helper guardrails (HB-08; architecture doc §5.6): the helper serves SmartSched itself, nothing else.

:func:`check` runs before any model call and costs 0 tokens:

1. the gateway's deterministic input guard (:func:`app.ai.guardrails.check_user_input`): prompt injection, code-like
   input, code / essays / translation / general knowledge, with the helper's own length cap (1000 characters);
2. the **index vocabulary** as the scope signal: a text with no scheduling word *and* no word of the feature index
   (exact, or one typo away) is out of scope. So "şifre", "bildirim" or "takvim" are in scope because the index has
   them, and "hava nasıl" is not. The refusal carries the top 3 index hits the person may open.

:func:`ground_answer` is the output rule: a model answer that names a page without a ``nav`` card for it is replaced
by the index answer (hallucinated menus are impossible).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.ai import guardrails as g
from app.ai.helper.index import STOPWORDS, Hit, fold_phrase, get_index

#: longest text a person may type into the helper
MAX_INPUT_CHARS = 1000
#: the share of a text's meaningful words the index must know for an in-scope verdict without a scheduling word
MIN_COVERAGE = 0.34
OUT_OF_SCOPE = "out_of_scope_helper"
REFUSAL_TR = "Ben yalnızca SmartSched'i kullanmanıza yardım edebilirim: ders, sınav, derslik ve rezervasyon işleri."
REFUSAL_EN = "I can only help you use SmartSched: classes, exams, rooms and bookings."
_WORD = re.compile(r"[a-z0-9]+")
#: a role handed to the assistant ("artık yöneticisin", "you are now the admin", "act as an administrator"). A person
#: saying who *they* are ("ben yöneticiyim") is harmless: rights come from their account, never from text
_ROLE_HANDOFF = re.compile(
    r"\b(artik|simdi|bundan sonra)\b.{0,20}\b(yonetici|admin|sistem yoneticisi|root)\w*(sin|sun|siniz|sunuz)\b"
    r"|\b(sen|siz)\b.{0,10}\b(yonetici|admin)\w*(sin|sun|siniz|sunuz)\b"
    r"|\byou are now\b.{0,20}\b(admin|administrator|root|superuser)\b"
    r"|\b(act|behave|pretend)\b.{0,12}\bas\b.{0,8}\b(an? )?(admin|administrator|root|superuser)\b",
    re.IGNORECASE,
)


@dataclass
class Verdict:
    allowed: bool
    code: str | None = None
    message_tr: str = ""
    message_en: str = ""
    #: the index hits the person may open (the refusal's "Menüde ara" rows, or the turn's pre-route)
    hits: list[Hit] = field(default_factory=list)
    rule: str | None = None


def _known_share(text: str) -> float:
    """Share of the text's meaningful words the index knows (exact stem, surface form, or one typo away)."""
    idx = get_index()
    words = [w for w in _WORD.findall(g.fold(text)) if w not in STOPWORDS and len(w) >= 2]
    if not words:
        return 0.0
    return sum(1 for w in words if idx.knows(w)) / len(words)


def check(text: str, perms: Iterable[str]) -> Verdict:
    """The helper's pre-model verdict for typed text. ``perms`` only filters the hits shown; the scope decision is
    the same for everyone (an academician asking about LDAP is in scope, they just get no admin page)."""
    raw = text or ""
    held = frozenset(perms)
    hits = get_index().search(raw, held, limit=3)
    if len(raw) > MAX_INPUT_CHARS:
        tr, en = g.message_for("input_too_long")
        return Verdict(False, "input_too_long", tr, en, hits, "length")
    v = g.check_user_input(raw, "helper")
    if not v.allowed:
        return Verdict(False, v.reason_code, v.message_tr, v.message_en, hits, v.rule)
    if _ROLE_HANDOFF.search(g.fold(raw)):
        tr, en = g.message_for("prompt_injection_roleplay")
        return Verdict(False, "prompt_injection_roleplay", tr, en, hits, "helper_role_handoff")
    if g.has_scheduling_signal(raw):
        return Verdict(True, hits=hits)
    if _known_share(raw) >= MIN_COVERAGE:
        return Verdict(True, hits=hits)
    return Verdict(False, OUT_OF_SCOPE, REFUSAL_TR, REFUSAL_EN, hits, "index_vocabulary")


def ground_answer(answer: str, emitted_feature_ids: Iterable[str]) -> bool:
    """``True`` when the model's answer may stand: it names no index page title for which no ``nav`` card was sent
    this turn, and shows no crumb path ("A › B") without any ``nav`` card. ``False`` = replace the text with the
    index answer (the person then sees only paths the server built, for pages they may open)."""
    emitted = set(emitted_feature_ids)
    if "›" in (answer or "") and not emitted:
        return False
    folded = f" {fold_phrase(answer)} "
    for e in get_index().entries:
        if e.id in emitted:
            continue
        for title in (e.title.tr, e.title.en):
            t = fold_phrase(title)
            if len(t) >= 5 and f" {t} " in folded:
                return False
    return True


__all__ = ["MAX_INPUT_CHARS", "OUT_OF_SCOPE", "REFUSAL_EN", "REFUSAL_TR", "Verdict", "check", "ground_answer"]
