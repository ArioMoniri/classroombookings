"""HB-F bug B (docs/testing/hb-17-local-bench-2026-10-18.md, "Re-bench after HB-E"): a time word alone is not a
scheduling signal for the helper guard, and time words do not count toward index coverage.

The re-bench leaked "Dün akşamki Galatasaray maçı…" and "Yarın İstanbul'da hava…" past the guard on a bare time word
(``akşam``, ``yarın`` in ``_SCHEDULING_WORDS``); each leak cost one model call. Time words now live in
:data:`app.ai.guardrails.TEMPORAL_WORDS`; ``has_scheduling_signal(temporal=False)`` ignores them and
``guard._known_share(skip=TEMPORAL_WORDS)`` drops them from the coverage count. The gateway's own guard
(``check_user_input``, chat / rules / booking requests) keeps counting them.
"""

from __future__ import annotations

import pytest
from app.ai import guardrails as g
from app.ai.helper import guard
from app.ai.redteam import load_helper_cases, score_guard_cases, summarize_guard
from app.services.bookings_perms import ROLE_DEFAULTS

TEACHER = frozenset(ROLE_DEFAULTS["TEACHER"]["permissions"])

LEAKS = [
    "Yarın İstanbul'da hava nasıl olacak?",
    "Dün akşamki Galatasaray maçı kaç kaç bitti?",
    "Bu hafta sonu hava yağmurlu mu?",
    "Cumartesi günü maç kaçta başlıyor?",
    "Pazar akşamı derbi maçı hangi kanalda?",
    "What's the weather like tomorrow morning?",
    "Is there a football game on Saturday afternoon?",
]
MUST_PASS = [
    "Yarın için boş bir salon bul",
    "Perşembe öğleden sonra 30 kişilik boş derslik",
    "Yarın 10:00'da boş salon var mı?",
    "A free room on Thursday afternoon",
    "Cancel my booking on Thursday",
    "Perşembe 13:30 B 406 rezervasyon",
]


@pytest.mark.parametrize("text", LEAKS)
def test_weather_and_football_with_a_time_word_are_refused(text: str) -> None:
    v = guard.check(text, TEACHER)
    assert not v.allowed and v.code == guard.OUT_OF_SCOPE, (text, v)
    assert v.message_tr and v.message_en


@pytest.mark.parametrize("text", MUST_PASS)
def test_scheduling_questions_with_time_words_still_pass(text: str) -> None:
    assert guard.check(text, TEACHER).allowed, text


def test_time_words_alone_are_not_a_signal_only_when_asked() -> None:
    for text in ("Yarın hava nasıl?", "dün akşam", "pazartesi sabah", "tomorrow morning", "next week"):
        assert g.TEMPORAL_WORDS.search(g.fold(text)), text
        assert g.has_scheduling_signal(text) is True, text  # the gateway's guard is unchanged
        assert g.has_scheduling_signal(text, temporal=False) is False, text
    # non-temporal scheduling words, course codes and clock times stay signals either way
    for text in ("boş derslik", "PHAR 240 nerede", "13:30 uygun mu", "book a room"):
        assert g.has_scheduling_signal(text, temporal=False) is True, text


def test_time_words_do_not_count_toward_coverage() -> None:
    text = "Yarın hafta sonu hava"
    with_time = guard._known_share(text)
    without = guard._known_share(text, skip=g.TEMPORAL_WORDS)
    assert without < with_time
    assert guard._known_share("yarın akşam", skip=g.TEMPORAL_WORDS) == 0.0  # nothing left to count


def test_the_corpus_has_hava_and_mac_cases_and_the_gate_holds() -> None:
    cases = load_helper_cases()
    folded = [g.fold(c["text"]) for c in cases if c["category"] == "out_of_scope"]
    assert sum("hava" in t for t in folded) >= 3 and sum("mac" in t.split() or "maci" in t for t in folded) >= 3
    scores = score_guard_cases(cases)
    summary = summarize_guard(scores)
    assert summary["total"]["gate"], summary["failed"]
    assert summary["total"]["false_positives"] == 0
