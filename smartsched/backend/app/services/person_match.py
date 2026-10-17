"""Is a file's instructor a known person, a renamed one, or new? (T-R1-25 open part; owner decision 2026-10-17,
ledger ``decisions-2026-10-17``.)

A pure function for the intake review (no database, no I/O): the caller passes the instructor as the file names it
(with the courses that row teaches and, when the file has such columns, a staff number / e-posta) and the term's
known people with their courses. :func:`match_person` answers one of

* ``key`` -- a staff number or e-mail in the file equals exactly one known person's: the same person, whatever the
  name says now (the key is used first);
* ``exact`` -- the folded name (titles stripped, Turkish İ/ı, other diacritics, NBSP, case) is a known person's;
* ``near`` -- no exact match, but exactly one known person who shares at least one course has the same given names
  (initials-aware: ``M. B. Karakuş`` = ``Meryem Bektaş Karakuş``; a dropped middle name is allowed) and a surname at
  most two edits away (``Şahin`` / ``Şahan``; one edit needs a surname of 3+ letters, two edits 5+ letters): the review
  asks "Aynı kişi mi?" (:func:`review_item`) instead of silently creating a second person;
* ``ambiguous`` -- more than one candidate (never merged automatically, never a merge question);
* ``new`` -- nobody.

A known person whose key differs from the file's key is never offered by name (two people may share a name).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.importers import normalize as n

MatchKind = Literal["key", "exact", "near", "ambiguous", "new"]

#: how far a renamed surname may be from the known one (owner decision 2026-10-17)
MAX_SURNAME_EDITS = 2


@dataclass(frozen=True)
class KnownPerson:
    """A person the term already has (``Instructor``): id, name as stored, the course codes they teach."""

    id: int
    name: str
    courses: frozenset[str] = field(default_factory=frozenset)
    email: str | None = None
    staff_no: Any = None


@dataclass(frozen=True)
class IncomingPerson:
    """An instructor as an intake file names them, with the course codes of the rows that name them."""

    name: str
    courses: frozenset[str] = field(default_factory=frozenset)
    email: str | None = None
    staff_no: Any = None


@dataclass(frozen=True)
class PersonMatch:
    kind: MatchKind
    person_id: int | None = None
    #: every known person that qualified (``ambiguous``: two or more)
    candidates: tuple[int, ...] = ()
    #: ``email`` | ``staff_no`` (key), ``name`` (exact), ``surname`` | ``initials`` | ``given_names`` (near)
    reason: str | None = None
    #: edits between the surnames (``near``)
    distance: int | None = None
    #: the course codes both teach (``near``), in the known person's spelling
    shared_courses: tuple[str, ...] = ()


# ------------------------------------------------------------------ normalisation


def email_key(value: Any) -> str | None:
    """An e-mail for comparison: NBSP / spaces dropped, Turkish-safe casefold (``İ`` -> ``i``)."""
    if value is None:
        return None
    s = n.fold(value).replace(" ", "")
    return s if "@" in s else None


def staff_key(value: Any) -> str | None:
    """A staff number for comparison: Excel's ``123.0`` = ``"123"`` = ``"00123"``; spaces and case ignored."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    s = n.fold(value).replace(" ", "")
    if re.fullmatch(r"\d+([.,]0+)?", s):  # "123,0" (comma decimal) or "123.0" written as text
        s = re.split(r"[.,]", s)[0].lstrip("0") or "0"
    return s or None


def _course_keys(codes: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in codes:
        code = n.canon_course_code(c) or n.clean_text(c)
        if code:
            out.setdefault(n.course_key(code), n.display_course_code(code))
    return out


def name_tokens(raw: str) -> list[str]:
    """Folded name words without titles: ``"Dr.Öğr.Üyesi M. BEKTAŞ-KARAKUŞ"`` -> ``["m", "bektas", "karakus"]``;
    ``"Karakuş, Meryem"`` -> ``["meryem", "karakus"]``."""
    p = n.canon_person_name(raw)
    text = p.full_name if p else (n.clean_text(raw) or "")
    if text.count(",") == 1:  # "Surname, Given names"
        last, first = (x.strip() for x in text.split(","))
        text = f"{first} {last}"
    return [t for t in (n.fold(w) for w in re.split(r"[\s.\-]+", text)) if t]


def display_name(raw: str) -> str:
    p = n.canon_person_name(raw)
    return p.full_name if p else (n.clean_text(raw) or raw)


def _edits(a: str, b: str) -> int:
    """Levenshtein distance."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def surname_distance(a: str, b: str) -> int:
    """Edits between two surnames after folding (``ŞAHİN`` = ``sahin``, ``Kırımlı`` = ``Kirimli``)."""
    return _edits(n.fold(a).replace(" ", ""), n.fold(b).replace(" ", ""))


def _surname_close(a: str, b: str) -> int | None:
    d = _edits(a, b)
    shortest = min(len(a), len(b))
    if d == 0 or (d == 1 and shortest >= 3) or (d == 2 and shortest >= 5):
        return d
    return None


def _given_compatible(a: Sequence[str], b: Sequence[str]) -> tuple[bool, bool]:
    """(compatible, used an initial): in order, each word of the shorter list equals a word of the longer one or is
    its initial; the first words always pair up."""
    if not a or not b:
        return False, False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    used_initial = False

    def same(x: str, y: str) -> bool:
        nonlocal used_initial
        if x == y:
            return True
        if (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y)):
            used_initial = True
            return True
        return False

    if not same(short[0], long_[0]):
        return False, False
    j = 1
    for w in short[1:]:
        while j < len(long_) and not same(w, long_[j]):
            j += 1
        if j >= len(long_):
            return False, False
        j += 1
    return True, used_initial


# ------------------------------------------------------------------ matching


def match_person(incoming: IncomingPerson, known: Iterable[KnownPerson]) -> PersonMatch:
    """See the module docstring. Pure: the same input gives the same answer."""
    people = list(known)
    in_email, in_staff = email_key(incoming.email), staff_key(incoming.staff_no)

    # 1. a key in the file decides first
    for reason, key, of in (("staff_no", in_staff, lambda p: staff_key(p.staff_no)), ("email", in_email, lambda p: email_key(p.email))):
        if key is None:
            continue
        hits = tuple(p.id for p in people if of(p) == key)
        if len(hits) == 1:
            return PersonMatch("key", hits[0], hits, reason)
        if len(hits) > 1:
            return PersonMatch("ambiguous", None, hits, reason)

    # a known person with another key of the same kind is someone else
    def eligible(p: KnownPerson) -> bool:
        if in_email and email_key(p.email) and email_key(p.email) != in_email:
            return False
        return not (in_staff and staff_key(p.staff_no) and staff_key(p.staff_no) != in_staff)

    pool = [p for p in people if eligible(p)]
    words = name_tokens(incoming.name)
    if not words:
        return PersonMatch("new")

    # 2. the folded name
    exact = tuple(p.id for p in pool if name_tokens(p.name) == words)
    if len(exact) == 1:
        return PersonMatch("exact", exact[0], exact, "name")
    if len(exact) > 1:
        return PersonMatch("ambiguous", None, exact, "name")

    # 3. a near name of exactly one person who teaches one of the same courses
    if len(words) < 2 or len(words[-1]) == 1:
        return PersonMatch("new")
    mine = _course_keys(incoming.courses)
    near: list[tuple[KnownPerson, int, str, tuple[str, ...]]] = []
    for p in pool:
        theirs = _course_keys(p.courses)
        shared = tuple(sorted(theirs[k] for k in set(mine) & set(theirs)))
        if not shared:
            continue
        other = name_tokens(p.name)
        if len(other) < 2:
            continue
        d = _surname_close(words[-1], other[-1])
        if d is None or d > MAX_SURNAME_EDITS:
            continue
        ok, initials = _given_compatible(words[:-1], other[:-1])
        if not ok:
            continue
        reason = "surname" if d else "initials" if initials else "given_names"
        near.append((p, d, reason, shared))
    if len(near) == 1:
        p, d, reason, shared = near[0]
        return PersonMatch("near", p.id, (p.id,), reason, d, shared)
    if len(near) > 1:
        return PersonMatch("ambiguous", None, tuple(x[0].id for x in near), "near")
    return PersonMatch("new")


def review_item(incoming: IncomingPerson, match: PersonMatch, known: Iterable[KnownPerson]) -> dict[str, Any] | None:
    """The intake review's "Aynı kişi mi?" item for a ``near`` match (``None`` otherwise): merge the file's person
    into the existing one, or keep them as a new person. Turkish first, English second."""
    if match.kind != "near" or match.person_id is None:
        return None
    existing = next(p for p in known if p.id == match.person_id)
    mine, theirs = display_name(incoming.name), display_name(existing.name)
    courses = ", ".join(match.shared_courses)
    return {
        "kind": "person_merge",
        "title_tr": "Aynı kişi mi?",
        "title_en": "Same person?",
        "incoming_name": mine,
        "existing_id": existing.id,
        "existing_name": theirs,
        "shared_courses": list(match.shared_courses),
        "reason": match.reason,
        "distance": match.distance,
        "message_tr": f"Dosyadaki “{mine}”, {courses} dersini veren “{theirs}” ile neredeyse aynı. Aynı kişi mi?",
        "message_en": f"“{mine}” in the file is almost the same as “{theirs}”, who teaches {courses}. Same person?",
        "options": [
            {"code": "merge", "label_tr": f"Evet, “{theirs}” ile birleştir", "label_en": f"Yes, merge into “{theirs}”"},
            {"code": "keep_new", "label_tr": "Hayır, yeni kişi olarak ekle", "label_en": "No, add as a new person"},
        ],
        "default": "merge",
    }
