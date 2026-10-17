"""Renamed instructors (T-R1-25 open part; owner decision 2026-10-17, ledger ``decisions-2026-10-17``): a pure matcher
that tells the intake review whether a file's instructor is a known person (staff number / e-mail first, then the
folded name), a near match of exactly one known person ("Aynı kişi mi?"), or new.

The known people and their courses are read from the real Bahar 2026 planning list
(``tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx``, columns "Ders Kodu" and "Dersin 1./2. Öğretim Elemanı").
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import openpyxl
import pytest
from app.importers import normalize as n
from app.services.person_match import (
    IncomingPerson,
    KnownPerson,
    match_person,
    review_item,
    surname_distance,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bahar_derslik_planlama_listesi_v5.xlsx"


@pytest.fixture(scope="module")
def known() -> list[KnownPerson]:
    wb = openpyxl.load_workbook(FIXTURE, read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(c or "") for c in next(rows)]
    code_col = header.index("Ders Kodu")
    people_cols = [i for i, h in enumerate(header) if "Öğretim Elemanı" in h and "Şekli" not in h]
    courses: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    for r in rows:
        code = n.canon_course_code(r[code_col])
        for i in people_cols:
            p = n.canon_person_name(r[i])
            if p and code and n.looks_like_person(p.raw):
                courses[p.canonical].add(code)
                names.setdefault(p.canonical, p.full_name)
    wb.close()
    out = [KnownPerson(id=k + 1, name=names[c], courses=frozenset(courses[c])) for k, c in enumerate(sorted(names))]
    assert len(out) > 100
    return out


def _id(known: list[KnownPerson], name: str) -> int:
    folded = n.fold(n.canon_person_name(name).full_name)  # type: ignore[union-attr]
    (hit,) = [p.id for p in known if n.fold(p.name) == folded]
    return hit


def test_the_same_name_in_other_capitals_titles_and_nbsp_is_the_known_person(known):
    sahin = _id(known, "Hülya Dündar Şahin")
    for typed in (
        "DR. ÖĞR. ÜYESİ HÜLYA DÜNDAR ŞAHİN",
        "Dr.Öğr.Üyesi Hülya\xa0Dündar Şahın",  # dotless ı typed for i, NBSP between the words
        "hulya dundar sahin",
    ):
        m = match_person(IncomingPerson(typed, frozenset({"TUR 112"})), known)
        assert (m.kind, m.person_id) == ("exact", sahin), typed
        assert review_item(IncomingPerson(typed, frozenset({"TUR 112"})), m, known) is None


def test_a_renamed_surname_within_two_edits_on_the_same_course_is_a_merge_question(known):
    sahin = _id(known, "Hülya Dündar Şahin")
    inc = IncomingPerson("Dr. Öğr. Üyesi Hülya Dündar Şahan", frozenset({"TUR112"}))  # course spelled without a space
    m = match_person(inc, known)
    assert (m.kind, m.person_id, m.distance) == ("near", sahin, 1)
    item = review_item(inc, m, known)
    assert item is not None
    assert item["kind"] == "person_merge" and item["title_tr"] == "Aynı kişi mi?"
    assert item["existing_id"] == sahin and item["incoming_name"] == "Hülya Dündar Şahan"
    assert [o["code"] for o in item["options"]] == ["merge", "keep_new"]
    assert item["default"] == "merge"
    assert "Hülya Dündar Şahin" in item["message_tr"] and "TUR 112" in item["message_tr"]
    assert item["message_en"] != item["message_tr"]


def test_initials_match_the_full_given_names(known):
    bektas = _id(known, "Meryem BEKTAŞ KARAKUŞ")
    m = match_person(IncomingPerson("Arş. Gör. M. Bektaş Karakuş", frozenset({"FZT 270"})), known)
    assert (m.kind, m.person_id, m.reason) == ("near", bektas, "initials")
    m = match_person(IncomingPerson("Arş. Gör. M. B. Karakuş", frozenset({"FZT 270"})), known)
    assert (m.kind, m.person_id) == ("near", bektas)


def test_a_near_name_without_a_shared_course_is_new(known):
    m = match_person(IncomingPerson("Dr. Öğr. Üyesi Hülya Dündar Şahan", frozenset({"MAT 112"})), known)
    assert m.kind == "new" and m.person_id is None
    m = match_person(IncomingPerson("Dr. Öğr. Üyesi Hülya Dündar Şahan", frozenset()), known)
    assert m.kind == "new"


def test_three_edits_or_a_different_given_name_is_new(known):
    assert match_person(IncomingPerson("Hülya Dündar Şenkaya", frozenset({"TUR 112"})), known).kind == "new"
    assert match_person(IncomingPerson("Gülay Dündar Şahin", frozenset({"TUR 112"})), known).kind == "new"


def test_two_candidates_are_ambiguous_and_never_a_merge_question(known):
    demirel = _id(known, "Yasin Demirel")
    other = KnownPerson(id=99999, name="Yusuf Demirel", courses=frozenset({"ING 112"}))
    inc = IncomingPerson("Öğr. Gör. Y. Demirel", frozenset({"ING 112"}))
    m = match_person(inc, [*known, other])
    assert m.kind == "ambiguous" and m.person_id is None and set(m.candidates) == {demirel, 99999}
    assert review_item(inc, m, [*known, other]) is None


def test_a_staff_number_or_e_mail_in_the_file_is_the_key_first(known):
    sahin = _id(known, "Hülya Dündar Şahin")
    keyed = [
        KnownPerson(p.id, p.name, p.courses, email="hulya.sahin@uni.edu.tr", staff_no="00123")
        if p.id == sahin
        else p
        for p in known
    ]
    # an e-mail in other capitals, NBSP around it: the same person, whatever the name now says
    inc = IncomingPerson("Hülya Kaya", frozenset(), email="\xa0HULYA.SAHIN@UNI.EDU.TR ")
    m = match_person(inc, keyed)
    assert (m.kind, m.person_id, m.reason) == ("key", sahin, "email")
    # a staff number read from Excel as a float, or with its zeros
    for staff in (123.0, "123", "00123", " 0 0123"):
        m = match_person(IncomingPerson("Hülya Kaya", frozenset(), staff_no=staff), keyed)
        assert (m.kind, m.person_id, m.reason) == ("key", sahin, "staff_no"), staff
    # a key that names nobody: a known person with a different key is never offered by name
    m = match_person(IncomingPerson("Hülya Dündar Şahan", frozenset({"TUR 112"}), email="h.sahan@uni.edu.tr"), keyed)
    assert m.kind == "new"


def test_surname_distance_is_turkish_folded_and_guards_short_surnames():
    assert surname_distance("ŞAHİN", "sahin") == 0
    assert surname_distance("Kırımlı", "Kirimli") == 0
    assert surname_distance("Şahin", "Şahan") == 1
    assert surname_distance("Ak", "Er") == 2
    assert match_person(
        IncomingPerson("Ali Er", frozenset({"MAT 112"})), [KnownPerson(1, "Ali Ak", frozenset({"MAT 112"}))]
    ).kind == "new"  # two edits on a two-letter surname is another person
