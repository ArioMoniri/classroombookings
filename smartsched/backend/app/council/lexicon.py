"""Header lexicon and value profiles: the heuristic "voter" of the structure analyst.

A column is mapped to a SmartSched field by two independent signals:

* **header score**: the folded header text against a multilingual synonym list per field (TR, EN, DE,
  FR, ES, IT, PT); a longer matching phrase wins over a shorter one ("derslik talebi" beats "derslik");
* **value fit**: the share of the column's non-empty values that look like the field's value kind
  (times, dates, day names, course codes, integers, people, long text, room codes).

The structure analyst combines both. When the model is available it votes as well, and disagreements
become review items.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.council import text as tx

#: field -> synonyms (folded with :func:`app.council.text.fold`)
FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "course_code": (
        "ders kodu",
        "dersin kodu",
        "kod",
        "course code",
        "course id",
        "course no",
        "course number",
        "code",
        "module code",
        "subject code",
        "catalog number",
        "lv-nummer",
        "kursnummer",
        "modulnummer",
        "code du cours",
        "code ue",
        "codigo",
        "codigo asignatura",
        "codice",
        "codice insegnamento",
        "codigo da disciplina",
    ),
    "course_name": (
        "ders adi",
        "dersin adi",
        "course name",
        "course title",
        "title",
        "module",
        "module name",
        "subject",
        "modul",
        "lehrveranstaltung",
        "veranstaltung",
        "intitule",
        "cours",
        "asignatura",
        "nombre asignatura",
        "insegnamento",
        "disciplina",
        "nome disciplina",
    ),
    "section": (
        "sube",
        "section",
        "group",
        "grup",
        "gruppe",
        "groupe",
        "grupo",
        "gruppo",
        "turma",
        "sec",
        "class group",
    ),
    "program": (
        "bolum/program",
        "bolum",
        "program",
        "programme",
        "department",
        "dept",
        "studiengang",
        "fachbereich",
        "filiere",
        "departement",
        "carrera",
        "titulacion",
        "corso di laurea",
        "dipartimento",
        "curso",
    ),
    "faculty": (
        "enstitu/fakulte/meslek yuksekokul",
        "enstitu/fakulte/meslek yuksekokulu",
        "fakulte",
        "enstitu",
        "faculty",
        "school",
        "college",
        "fakultat",
        "faculte",
        "facultad",
        "facolta",
        "faculdade",
    ),
    "class_year": (
        "sinif",
        "class year",
        "year of study",
        "study year",
        "year",
        "grade",
        "level",
        "jahrgang",
        "fachsemester",
        "annee",
        "niveau",
        "ano",
        "anno",
        "curso academico",
    ),
    "semester": ("yariyil", "semester", "term", "donem", "semestre", "periodo"),
    "enrolment": (
        "derse kayitlanacak ogrenci sayisi",
        "ogrenci sayisi",
        "derse kayitli ogr. sayisi",
        "ogr. sayisi",
        "kontenjan",
        "mevcut",
        "enrolment",
        "enrollment",
        "students",
        "expected students",
        "headcount",
        "number of students",
        "class size",
        "size",
        "teilnehmer",
        "teilnehmerzahl",
        "studierende",
        "effectif",
        "nombre d'etudiants",
        "alumnos",
        "matriculados",
        "iscritti",
        "studenti",
        "alunos",
    ),
    "day": ("dersin gunu", "gunu", "gun", "day", "weekday", "day of week", "tag", "wochentag", "jour", "dia", "giorno"),
    "start_time": (
        "dersin baslangic saati",
        "baslangic saati",
        "sinav baslangic saati",
        "baslangic",
        "start time",
        "start",
        "begins",
        "begin",
        "from",
        "beginn",
        "von",
        "debut",
        "heure de debut",
        "hora inicio",
        "inicio",
        "ora inizio",
        "inizio",
        "hora de inicio",
    ),
    "end_time": (
        "dersin bitis saati",
        "bitis saati",
        "sinav bitis saati",
        "bitis",
        "end time",
        "end",
        "ends",
        "finish",
        "until",
        "to",
        "ende",
        "bis",
        "fin",
        "heure de fin",
        "hora fin",
        "ora fine",
        "fine",
        "termino",
    ),
    "time_range": (
        "saat",
        "saatler",
        "time",
        "times",
        "hours",
        "slot",
        "time slot",
        "uhrzeit",
        "zeit",
        "heure",
        "horario",
        "orario",
    ),
    "room_request": (
        "derslik talebi",
        "talep",
        "sinavin yapilacagi yer",
        "requested room",
        "room request",
        "room requested",
        "preferred room",
        "room preference",
        "raumwunsch",
        "salle demandee",
        "aula solicitada",
    ),
    "room": (
        "derslik planlama - kesinlesen derslik",
        "kesinlesen derslik",
        "derslik",
        "salon",
        "room",
        "rooms",
        "room code",
        "room no",
        "room number",
        "room name",
        "code",
        "assigned room",
        "venue",
        "location",
        "raum",
        "horsaal",
        "salle",
        "aula",
        "sala",
        "local",
    ),
    "instructor": (
        "dersin 1. ogretim elemani",
        "1. ogretim elemani",
        "ogretim elemani",
        "ogretim uyesi",
        "instructor",
        "lecturer",
        "teacher",
        "professor",
        "tutor",
        "staff",
        "dozent",
        "dozentin",
        "lehrende",
        "enseignant",
        "profesor",
        "docente",
        "professor responsavel",
    ),
    "instructor2": (
        "dersin 2. ogretim elemani",
        "2. ogretim elemani",
        "second lecturer",
        "co-instructor",
        "co-lecturer",
        "assistant",
        "second instructor",
        "teaching assistant",
    ),
    "mode": (
        "dersin ogretim sekli",
        "ogretim sekli",
        "egitim sekli",
        "delivery mode",
        "mode",
        "delivery",
        "modality",
        "format",
        "lehrform",
        "modalite",
        "modalidad",
        "modalita",
        "modalidade",
    ),
    "weeks": (
        "dersligin kullanilacagi haftalar",
        "haftalar",
        "hafta",
        "weeks",
        "week",
        "teaching weeks",
        "wochen",
        "semaines",
        "semanas",
        "settimane",
    ),
    "notes": (
        "derse ozel aciklama",
        "aciklama",
        "not",
        "notlar",
        "notes",
        "note",
        "remarks",
        "remark",
        "comments",
        "comment",
        "bemerkung",
        "anmerkung",
        "remarque",
        "observaciones",
        "osservazioni",
        "observacoes",
    ),
    "date": ("sinav tarihi", "tarih", "date", "exam date", "datum", "fecha", "data", "jour de l'examen"),
    "duration": ("sure", "duration", "length", "minutes", "dauer", "duree", "duracion", "durata"),
    "capacity": (
        "kapasite",
        "capacity",
        "seats",
        "seat count",
        "kapazitat",
        "platze",
        "sitzplatze",
        "capacite",
        "places",
        "capacidad",
        "plazas",
        "capienza",
        "posti",
        "capacidade",
        "lugares",
    ),
    "exam_capacity": ("sinav kapasitesi", "exam capacity", "exam seats", "prufungsplatze", "places examen"),
    "building": ("blok", "bina", "building", "block", "gebaude", "batiment", "edificio", "edificio", "campus"),
    "floor": ("kat", "floor", "storey", "etage", "planta", "piano", "andar"),
    "room_type": (
        "tur",
        "derslik turu",
        "type",
        "room type",
        "features",
        "equipment",
        "tags",
        "ausstattung",
        "equipement",
        "equipamiento",
    ),
    "person_name": (
        "ad soyad",
        "adi soyadi",
        "name",
        "full name",
        "staff name",
        "nom",
        "nombre",
        "nome",
        "vorname nachname",
    ),
    "email": ("e-posta", "eposta", "email", "e-mail", "mail", "correo", "courriel"),
    "title": ("unvan", "academic title", "titel", "titre", "titulo"),
    "label": (
        "etkinlik",
        "event",
        "holiday",
        "tatil",
        "description",
        "veranstaltung",
        "evenement",
        "evento",
        "feriado",
    ),
    "start_date": ("baslangic tarihi", "start date", "from date", "beginn datum", "date de debut", "fecha inicio"),
    "end_date": ("bitis tarihi", "end date", "to date", "end datum", "date de fin", "fecha fin"),
}

#: field -> value kind used for the fit score
VALUE_KIND: dict[str, str] = {
    "course_code": "course_code",
    "course_name": "text",
    "section": "short",
    "program": "text",
    "faculty": "text",
    "class_year": "int",
    "semester": "short",
    "enrolment": "int",
    "day": "day",
    "start_time": "time",
    "end_time": "time",
    "time_range": "time_range",
    "room_request": "any",
    "room": "room",
    "instructor": "person",
    "instructor2": "person",
    "mode": "short",
    "weeks": "any",
    "notes": "long",
    "date": "date",
    "duration": "int",
    "capacity": "int",
    "exam_capacity": "int",
    "building": "short",
    "floor": "short",
    "room_type": "short",
    "person_name": "person",
    "email": "email",
    "title": "short",
    "label": "text",
    "start_date": "date",
    "end_date": "date",
}

FIELDS = tuple(FIELD_SYNONYMS)


def _norm_header(h: str) -> tuple[str, str]:
    """(main text before any parenthesis, full folded text)."""
    full = tx.fold(h).replace("\n", " ").replace("_", " ")
    main = re.split(r"[(\[]", full, maxsplit=1)[0].strip(" :*")
    return main, full


def header_scores(header: str) -> list[tuple[str, float, int]]:
    """Candidate fields for one header: (field, score 0..1, matched phrase length), best first."""
    if not header or not header.strip():
        return []
    main, full = _norm_header(header)
    out: list[tuple[str, float, int]] = []
    for field, syns in FIELD_SYNONYMS.items():
        best: tuple[float, int] | None = None
        for s in syns:
            if main == s:
                cand = (1.0, len(s))
            elif re.search(rf"(^|[\s/.-]){re.escape(s)}($|[\s/.-])", main):
                cand = (0.85 if len(s) >= 4 else 0.7, len(s))
            elif len(s) >= 5 and s in full:
                cand = (0.6, len(s))
            else:
                continue
            if best is None or cand > best:
                best = cand
        if best is not None:
            out.append((field, best[0], best[1]))
    out.sort(key=lambda t: (-t[1], -t[2]))
    return out


# ---------------------------------------------------------------------------
# Value fit
# ---------------------------------------------------------------------------


def _is_int(v: str) -> bool:
    return tx.parse_int(v) is not None and len(v) <= 8


def _is_time(v: str) -> bool:
    return tx.parse_clock(v) is not None and tx.parse_time_range(v) is None and len(v) <= 12


_KIND_TESTS: dict[str, Callable[[str], bool]] = {
    "course_code": lambda v: tx.course_code(v) is not None and len(v) <= 40,
    "int": _is_int,
    "time": _is_time,
    "time_range": lambda v: tx.parse_time_range(v) is not None,
    "day": lambda v: bool(tx.parse_days(v)),
    "date": lambda v: tx.parse_date(v, 2000) is not None,
    "person": tx.looks_like_person,
    "email": lambda v: "@" in v and "." in v.split("@")[-1],
    "room": lambda v: bool(tx.room_tokens(v)),
    "long": lambda v: len(v) >= 25,
    "text": lambda v: len(v) >= 3 and not v.replace(" ", "").isdigit(),
    "short": lambda v: 0 < len(v) <= 40,
    "any": lambda v: True,
}


def value_fit(field: str, values: list[str]) -> float:
    """Share of non-empty sample values that look like ``field``'s kind (0..1)."""
    vals = [v for v in values if v and v.strip()]
    if not vals:
        return 0.0
    test = _KIND_TESTS[VALUE_KIND.get(field, "any")]
    return round(sum(1 for v in vals if test(v)) / len(vals), 3)


@dataclass
class ColumnGuess:
    field: str | None
    confidence: float
    alternatives: list[tuple[str, float]]
    header_score: float
    value_fit: float


#: value kinds that may be inferred from values alone (headerless files)
_VALUE_ONLY = ("course_code", "time_range", "day", "date", "email")


def guess_column(header: str, values: list[str]) -> ColumnGuess:
    """Combine header score and value fit into one guess with alternatives."""
    cands = header_scores(header)
    scored: list[tuple[str, float, float, float]] = []
    for field, hs, _len in cands[:6]:
        vf = value_fit(field, values)
        kind = VALUE_KIND.get(field, "any")
        weight = 0.25 if kind in ("any", "short", "text") else 0.45
        scored.append((field, round((1 - weight) * hs + weight * vf, 3), hs, vf))
    if not scored:
        for field in _VALUE_ONLY:
            vf = value_fit(field, values)
            if vf >= 0.8:
                scored.append((field, round(0.55 * vf, 3), 0.0, vf))
    scored.sort(key=lambda t: -t[1])
    if not scored:
        return ColumnGuess(None, 0.0, [], 0.0, 0.0)
    top = scored[0]
    return ColumnGuess(top[0], top[1], [(f, s) for f, s, _, _ in scored[1:4]], top[2], top[3])
