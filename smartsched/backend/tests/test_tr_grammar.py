"""Turkish suffix helpers for generated sentences (round-1 R1-S-23 / R1-S-24, lane H T-R1-47 / T-R1-49)."""

from __future__ import annotations

import pytest
from app.services.tr_grammar import dative, pct, week_list


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("B 201", "B 201'e"),  # iki yüz bir
        ("C 606", "C 606'ya"),  # altı yüz altı
        ("A 204", "A 204'e"),  # dört
        ("B 30", "B 30'a"),  # otuz
        ("LAB", "LAB'a"),
        ("Amfi", "Amfi'ye"),  # a proper name ending in a vowel: buffer y
        # a room named by a common noun with a possessive: no apostrophe, buffer n (R1-S-24: "Test dersliği'ye")
        ("Test dersliği", "Test dersliğine"),
        ("Büyük amfisi", "Büyük amfisine"),
        ("Konferans salonu", "Konferans salonuna"),
        ("Bilgisayar laboratuvarı", "Bilgisayar laboratuvarına"),
    ],
)
def test_dative(text: str, expected: str) -> None:
    assert dative(text) == expected


def test_week_list_is_singular_for_one_week_and_lists_runs() -> None:
    assert week_list([3]) == "3. hafta"
    assert week_list([3, 5]) == "3. ve 5. haftalar"
    assert week_list([1, 2, 3, 4]) == "1.–4. haftalar"
    assert week_list([1, 2, 3, 4, 6]) == "1.–4. ve 6. haftalar"
    assert week_list([]) == ""
    assert week_list([3], "en") == "week 3"
    assert week_list([3, 5], "en") == "weeks 3 and 5"
    assert week_list([1, 2, 3, 4], "en") == "weeks 1–4"


def test_pct_never_prints_a_space_before_the_sign() -> None:
    assert pct(100) == "%100"
    assert pct(0.6) == "%0,6"
    assert pct(95.0) == "%95"
    assert pct(100, "en") == "100%"
    assert pct(0.6, "en") == "0.6%"
