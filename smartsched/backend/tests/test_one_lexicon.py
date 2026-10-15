"""Review D9 with the Ingestion Council merged: the importers and the council share one matching form and one
Turkish day lexicon (``normalize.fold`` / ``normalize.DAY_NAMES``; ``council/text.py`` delegates)."""

from __future__ import annotations

import pytest
from app.council import text as ct
from app.importers import normalize as n


@pytest.mark.parametrize(
    "raw",
    ["ÇARŞAMBA", "Perşembe\xa0 ", "SALI", "İŞL 101", "ışık", "Straße", "  çok   boşluk ", None, 12.5],
)
def test_council_fold_is_the_importer_fold(raw) -> None:
    assert ct.fold(raw) == n.fold(raw)
    assert ct.fold is n.fold


def test_turkish_days_agree() -> None:
    for name, num in n.DAY_NAMES.items():
        for spelling in (name, n.tr_upper(name), n.fold(name), n.fold(name).upper()):
            assert ct.parse_days(spelling) == [num], spelling
            assert n.parse_day(spelling).days == [num], spelling
    # every Turkish day word the council knows is one the importer knows
    tr = {k: v for k, v in ct.DAY_WORDS.items() if k in {n.fold(d) for d in n.DAY_NAMES}}
    assert tr == {n.fold(k): v for k, v in n.DAY_NAMES.items()}
