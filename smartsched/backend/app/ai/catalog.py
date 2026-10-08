"""Constraint catalogue + tool schemas the model is allowed to use.

One :class:`KindSpec` per constraint kind registered in :mod:`app.solver.constraints` (falls back to
the frozen list in ``app.solver.model.CONSTRAINT_KINDS_V1`` if the solver package cannot be imported).
Every spec carries a JSON schema for the *resolved* params (ids), TR/EN descriptions, examples and the
allowed hardness; :func:`validate_params` checks a params dict against it.

Tool definitions are **strict** (``additionalProperties: false``, every property required, optional
fields nullable) so the SDK guarantees the shape; the model only ever names entities (room codes,
programme names, course codes) - ids are resolved server side by :mod:`app.ai.resolve`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.solver.model import CONSTRAINT_KINDS_V1

try:  # the registry is the source of truth for hardness rules; the list in model.py is the fallback
    from app.solver.constraints import HANDLERS as _HANDLERS
except Exception:  # pragma: no cover - solver package mid-edit
    _HANDLERS = {}

HARDNESS = ("hard", "soft")

# ---------------------------------------------------------------------------
# JSON-schema helpers
# ---------------------------------------------------------------------------


def _s(t: str, **extra: Any) -> dict[str, Any]:
    return {"type": t, **extra}


def _arr(items: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"type": "array", "items": items, **extra}


def strict_object(properties: dict[str, dict[str, Any]], description: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
    if description:
        out["description"] = description
    return out


# ---------------------------------------------------------------------------
# Selectors (resolved form, as the solver's ``select_events`` reads them)
# ---------------------------------------------------------------------------

SELECTOR_SCHEMA: dict[str, dict[str, Any]] = {
    "event_ids": _arr(_s("integer"), description="meeting/exam request ids"),
    "program": _s("string", description="programme canonical name -> cohort keys PROG:<name>:*"),
    "programs": _arr(_s("string")),
    "cohort": _s("string", description="exact cohort key, e.g. PROG:Psikoloji:Y1"),
    "cohorts": _arr(_s("string")),
    "match": _s("string", description="case-insensitive substring of a label or cohort key"),
    "instructor": _s("string", description="instructor key INS:<id>"),
    "instructors": _arr(_s("string")),
    "kinds": _arr(_s("string", enum=["course", "exam"])),
}

#: Model-facing selector: names only, ids are resolved server side.
#: Strict-tool budget (API limits: <= 24 optional params and <= 16 union-typed params across *all*
#: strict tools of one request): every field is required and non-nullable; "not set" is an explicit
#: sentinel - empty string, empty list or 0 - stripped by :func:`app.ai.resolve.clean_sentinels`.
MODEL_SELECTOR_SCHEMA = strict_object(
    {
        "course_codes": _arr(_s("string"), description="course codes as written, e.g. 'PHAR 240'; [] = none"),
        "program_name": _s("string", description="programme / department name as written; '' = none"),
        "class_years": _arr(_s("integer"), description="1..6; [] = all years of the programme"),
        "instructor_name": _s("string", description="'' = none"),
        "match": _s("string", description="free substring when nothing else fits (low confidence); '' = none"),
        "kinds": _arr(_s("string", enum=["course", "exam"]), description="[] = both"),
    },
    "Which events the rule applies to. All fields empty = all events.",
)

#: Model-facing params superset (one flat object keeps the tool strict without per-kind unions).
MODEL_PARAMS_SCHEMA = strict_object(
    {
        "room_codes": _arr(_s("string"), description="room codes as written, e.g. 'A 206'"),
        "buildings": _arr(_s("string"), description="building letters A-D"),
        "required_tags": _arr(_s("string", enum=["TIP", "PC", "LAB", "AMPHI"])),
        "forbidden_tags": _arr(_s("string", enum=["TIP", "PC", "LAB", "AMPHI"])),
        "days": _arr(_s("integer"), description="1=Monday .. 7=Sunday"),
        "periods": _arr(_s("integer"), description="explicit period indexes 1..18"),
        "earliest": _s("integer", description="first allowed period (day_window) or range start; 0 = unset"),
        "latest": _s("integer", description="last allowed period (day_window) or range end; 0 = unset"),
        "weeks": _arr(_s("integer"), description="week indexes 1..N"),
        "from_date": _s("string", description="ISO date YYYY-MM-DD, resolved to a week index; '' = unset"),
        "to_date": _s("string", description="ISO date YYYY-MM-DD; '' = unset"),
        "last_n_weeks": _s("integer", description="e.g. 'only the last 7 weeks' = 7; 0 = unset"),
        "amount": _s(
            "integer",
            description="the kind's number: capacity size, min_capacity_waste unit, exam_gap min periods, "
            "max_exams_per_day n, fixed_time start period; 0 = unset",
        ),
        "label": _s("string", description="room_closed label; '' = none"),
    },
    "Rule parameters. Fill only what the kind needs; leave the rest empty ('' / [] / 0).",
)


# ---------------------------------------------------------------------------
# Kind specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KindSpec:
    kind: str
    title: dict[str, str]
    description: dict[str, str]
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)  # kind-specific resolved params
    examples: list[dict[str, Any]] = field(default_factory=list)
    selectable: bool = True  # accepts the event selector
    default_hardness: str = "soft"
    allowed_hardness: tuple[str, ...] = HARDNESS
    implicit: bool = False
    registered: bool = True

    @property
    def params_schema(self) -> dict[str, Any]:
        props = {**(SELECTOR_SCHEMA if self.selectable else {}), **self.fields}
        return {"type": "object", "properties": props, "additionalProperties": False}

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "params_schema": self.params_schema,
            "examples": self.examples,
            "allowed_hardness": list(self.allowed_hardness),
            "default_hardness": self.default_hardness,
            "implicit": self.implicit,
            "registered": self.registered,
        }


_ROOM_IDS = {"room_ids": _arr(_s("integer"), description="room ids (resolved from codes)")}
_WEEKS = {"weeks": _arr(_s("integer"))}

_SPECS: list[KindSpec] = [
    KindSpec(
        "capacity",
        {"tr": "Kapasite", "en": "Capacity"},
        {
            "tr": (
                "Derslik kapasitesi (sınavda sınav kapasitesi) öğrenci sayısını karşılamalı. Hedefli "
                "biçimde 'size' ile koltuk ihtiyacı değiştirilir."
            ),
            "en": (
                "Room capacity (exam capacity for exams) must cover the enrolment. Targeted form overrides "
                "the seats needed with 'size'."
            ),
        },
        {"size": _s("integer")},
        [{"nl": "Birleştirilmiş sınav için 120 koltuk yeter", "params": {"size": 120}, "hardness": "hard"}],
        default_hardness="hard",
    ),
    KindSpec(
        "no_room_overlap",
        {"tr": "Derslik çakışması yok", "en": "No room overlap"},
        {
            "tr": "Aynı derslik, gün, saat ve haftada en fazla bir etkinlik. Her zaman zorunlu.",
            "en": "At most one event per room, day, period and week. Always hard.",
        },
        selectable=False,
        default_hardness="hard",
        allowed_hardness=("hard",),
    ),
    KindSpec(
        "no_cohort_overlap",
        {"tr": "Sınıf çakışması yok", "en": "No cohort overlap"},
        {
            "tr": "Aynı program+sınıf aynı anda iki derse giremez. Her zaman zorunlu.",
            "en": "The same programme+year never has two events at once. Always hard.",
        },
        {"keys": _arr(_s("string"))},
        selectable=False,
        default_hardness="hard",
        allowed_hardness=("hard",),
    ),
    KindSpec(
        "no_instructor_overlap",
        {"tr": "Öğretim elemanı çakışması yok", "en": "No instructor overlap"},
        {
            "tr": "Bir öğretim elemanı aynı anda iki derslikte olamaz. Her zaman zorunlu.",
            "en": "An instructor cannot be in two rooms at once. Always hard.",
        },
        {"keys": _arr(_s("string"))},
        selectable=False,
        default_hardness="hard",
        allowed_hardness=("hard",),
    ),
    KindSpec(
        "fixed_time",
        {"tr": "Sabit gün/saat", "en": "Fixed time"},
        {
            "tr": (
                "Talep edilen gün ve saat korunur (varsayılan zorunlu). Hedefli: seçilen dersleri 'day' ve "
                "'start' ile belirli saate sabitler/tercih ettirir."
            ),
            "en": (
                "Honour requested day/time (hard by default). Targeted: pin or prefer 'day' + 'start' for "
                "the selected events."
            ),
        },
        {"day": _s("integer"), "start": _s("integer")},
        [{"nl": "MAT 112 pazartesi 4. derse", "params": {"day": 1, "start": 4}, "hardness": "hard"}],
        default_hardness="hard",
    ),
    KindSpec(
        "room_tags",
        {"tr": "Derslik etiketleri", "en": "Room tags"},
        {
            "tr": (
                "Gerekli / yasak derslik etiketleri (TIP, PC, LAB, AMPHI). 'TIP derslikleri sadece Tıp "
                "için' => diğer programlara forbidden_tags=[TIP]."
            ),
            "en": (
                "Required / forbidden room tags (TIP, PC, LAB, AMPHI). 'TIP rooms only for medicine' => "
                "forbidden_tags=[TIP] for everyone else."
            ),
        },
        {"required_tags": _arr(_s("string")), "forbidden_tags": _arr(_s("string"))},
        [
            {
                "nl": "TIP derslikleri sadece Tıp Fakültesi için",
                "params": {"forbidden_tags": ["TIP"]},
                "hardness": "hard",
            },
            {"nl": "Bilgisayar laboratuvarı zorunlu", "params": {"required_tags": ["PC"]}, "hardness": "hard"},
        ],
        default_hardness="hard",
    ),
    KindSpec(
        "room_pin",
        {"tr": "Derslik sabitleme", "en": "Room pin"},
        {
            "tr": "Seçilen dersler listedeki dersliklerden birini kullanmalı (zorunlu) veya tercih etmeli (esnek).",
            "en": "Selected events must (hard) or should (soft) use one of the listed rooms.",
        },
        {**_ROOM_IDS, **_WEEKS},
        [{"nl": "PHAR 240 A 206'da olsun", "params": {"room_ids": [12]}, "hardness": "hard"}],
        default_hardness="hard",
    ),
    KindSpec(
        "room_forbid",
        {"tr": "Derslik yasağı", "en": "Room forbid"},
        {
            "tr": "Seçilen dersler listedeki derslikleri kullanmamalı.",
            "en": "Selected events must not use the listed rooms.",
        },
        _ROOM_IDS,
        [{"nl": "Psikoloji 1. sınıf A 204'e girmesin", "params": {"room_ids": [3]}, "hardness": "hard"}],
        default_hardness="hard",
    ),
    KindSpec(
        "building_preference",
        {"tr": "Bina tercihi", "en": "Building preference"},
        {
            "tr": (
                "Seçilen dersler belirli bina(lar)da olsun; esnek = ceza, zorunlu = diğer binalar elenir. "
                "'days' ile belirli günlere sınırlanabilir (inceleme gerekir)."
            ),
            "en": "Selected events in given building(s); soft = penalty, hard = other buildings pruned.",
        },
        {"building": _s("string"), "buildings": _arr(_s("string")), "days": _arr(_s("integer"))},
        [{"nl": "Eczacılık pazartesi C blokta kalsın", "params": {"building": "C", "days": [1]}, "hardness": "soft"}],
    ),
    KindSpec(
        "room_preference",
        {"tr": "Derslik tercihi", "en": "Room preference"},
        {
            "tr": "Sıralı tercih listesi; ceza = seçilen dersliğin sırası.",
            "en": "Ordered preferred rooms; penalty = rank of the chosen room.",
        },
        _ROOM_IDS,
        [{"nl": "BME 419 için önce A 204 sonra A 203", "params": {"room_ids": [3, 4]}, "hardness": "soft"}],
    ),
    KindSpec(
        "same_room_across_weeks",
        {"tr": "Haftalar arası aynı derslik", "en": "Same room across weeks"},
        {"tr": "Hafta desenine bölünmüş bir ders tek derslikte kalsın.", "en": "A week-split meeting keeps one room."},
        {"groups": _arr(_arr(_s("integer")))},
    ),
    KindSpec(
        "same_room_group",
        {"tr": "Aynı derslik grubu", "en": "Same room group"},
        {
            "tr": "Seçilen dersler aynı derslikte olsun ('X dersi ile aynı derslik').",
            "en": "Selected events share one room ('same room as X').",
        },
        {"groups": _arr(_arr(_s("integer")))},
        [{"nl": "OPT 126 ile aynı derslik", "params": {"event_ids": [41, 42]}, "hardness": "soft"}],
    ),
    KindSpec(
        "min_capacity_waste",
        {"tr": "Boş koltuk israfı", "en": "Capacity waste"},
        {
            "tr": "20 kişilik dersi 156 kişilik amfiye koyma; 'unit' koltuk başına ceza birimi.",
            "en": "Avoid 20 students in a 156-seat hall; 'unit' seats per penalty unit.",
        },
        {"unit": _s("integer")},
        [{"nl": "Büyük amfileri küçük derslere verme", "params": {"unit": 10}, "hardness": "soft"}],
        allowed_hardness=("soft",),
    ),
    KindSpec(
        "exam_gap",
        {"tr": "Sınav aralığı", "en": "Exam gap"},
        {
            "tr": "Aynı sınıfın aynı gündeki iki sınavı arasında en az 'min_periods' boş ders saati.",
            "en": "Two exams of one cohort on a day are at least 'min_periods' periods apart.",
        },
        {"min_periods": _s("integer")},
        [
            {
                "nl": "Aynı sınıfın sınavları arasında en az 2 saat boşluk",
                "params": {"min_periods": 2, "kinds": ["exam"]},
                "hardness": "soft",
            }
        ],
    ),
    KindSpec(
        "max_exams_per_day",
        {"tr": "Günlük sınav sınırı", "en": "Max exams per day"},
        {"tr": "Bir sınıfın bir günde en fazla 'n' sınavı.", "en": "At most 'n' exams per day for a cohort."},
        {"n": _s("integer")},
        [
            {
                "nl": "Hemşirelik 1. sınıfa günde en fazla 1 sınav",
                "params": {"n": 1, "cohorts": ["PROG:Hemşirelik:Y1"], "kinds": ["exam"]},
                "hardness": "hard",
            }
        ],
    ),
    KindSpec(
        "stability",
        {"tr": "Değişiklikleri azalt", "en": "Stability"},
        {
            "tr": "Önceki çözüme yakın kal; hedefli+zorunlu = seçilen dersleri önceki yerinde tut.",
            "en": "Stay close to the previous run; targeted+hard = keep the selected events where they were.",
        },
        {},
        [{"nl": "NRS 450 yerinde kalsın", "params": {"event_ids": [77]}, "hardness": "hard"}],
    ),
    KindSpec(
        "room_closed",
        {"tr": "Derslik kapalı", "en": "Room closed"},
        {
            "tr": "Bir derslik belirli gün/saat/haftalarda kullanılamaz ('A 204 çarşamba 7-9. saat boş kalsın').",
            "en": "A room is unavailable in given day/periods/weeks ('keep A 204 free Wed P7-P9').",
        },
        {
            "room_id": _s("integer"),
            "room": _s("string"),
            "day": _s("integer"),
            "days": _arr(_s("integer")),
            "periods": _arr(_s("integer")),
            "start": _s("integer"),
            "end": _s("integer"),
            "weeks": _arr(_s("integer")),
            "label": _s("string"),
        },
        [
            {
                "nl": "A 204 çarşamba 7-9. saatler boş",
                "params": {"room_id": 3, "day": 3, "periods": [7, 8, 9]},
                "hardness": "hard",
            }
        ],
        selectable=False,
        default_hardness="hard",
    ),
    KindSpec(
        "day_window",
        {"tr": "Gün penceresi", "en": "Day window"},
        {
            "tr": (
                "Seçilen dersler 'earliest'..'latest' ders saatleri arasında olsun ('hemşirelik 1. sınıf "
                "17:30'dan sonra ders olmasın' => latest=11)."
            ),
            "en": (
                "Selected events inside periods earliest..latest ('no lectures after 17:30 for first-year "
                "nursing' => latest=11)."
            ),
        },
        {
            "periods": _arr(_s("integer")),
            "earliest": _s("integer"),
            "latest": _s("integer"),
            "days": _arr(_s("integer")),
        },
        [
            {
                "nl": "Hemşirelik 1. sınıf 17:30'dan sonra ders olmasın",
                "params": {"cohorts": ["PROG:Hemşirelik:Y1"], "latest": 11},
                "hardness": "hard",
            }
        ],
        default_hardness="hard",
    ),
    KindSpec(
        "evening_programs_in_buildings",
        {"tr": "İkinci öğretim binaları", "en": "Evening programmes in buildings"},
        {
            "tr": "İkinci öğretim (İÖ) programları listedeki binalarda kalsın.",
            "en": "Evening (İÖ) programmes stay in the listed buildings.",
        },
        {"buildings": _arr(_s("string"))},
        [{"nl": "İÖ dersleri B ve C bloklarda", "params": {"buildings": ["B", "C"]}, "hardness": "soft"}],
    ),
]


def _build_kinds() -> dict[str, KindSpec]:
    specs = {s.kind: s for s in _SPECS}
    registered = set(_HANDLERS) if _HANDLERS else set(CONSTRAINT_KINDS_V1)
    out: dict[str, KindSpec] = {}
    for kind in list(CONSTRAINT_KINDS_V1) + sorted(registered - set(CONSTRAINT_KINDS_V1)):
        spec = specs.get(kind) or KindSpec(kind, {"tr": kind, "en": kind}, {"tr": kind, "en": kind})
        h = _HANDLERS.get(kind) if _HANDLERS else None
        if h is not None:
            allowed = HARDNESS if h.may_soften else ("hard",)
            if spec.kind == "min_capacity_waste":
                allowed = ("soft",)
            spec = KindSpec(
                spec.kind,
                spec.title,
                spec.description,
                spec.fields,
                spec.examples,
                spec.selectable,
                "hard" if h.default_hard else "soft",
                allowed,
                h.implicit,
                True,
            )
        elif kind not in registered:
            spec = KindSpec(
                spec.kind,
                spec.title,
                spec.description,
                spec.fields,
                spec.examples,
                spec.selectable,
                spec.default_hardness,
                spec.allowed_hardness,
                spec.implicit,
                False,
            )
        out[kind] = spec
    return out


KINDS: dict[str, KindSpec] = _build_kinds()
KIND_NAMES: tuple[str, ...] = tuple(KINDS)


# ---------------------------------------------------------------------------
# Validation of resolved params (no external dependency)
# ---------------------------------------------------------------------------


def _check(value: Any, schema: dict[str, Any], path: str, issues: list[str]) -> None:
    t = schema.get("type")
    types = t if isinstance(t, list) else [t] if t else []
    if value is None:
        if "null" not in types and types:
            issues.append(f"{path}: must not be null")
        return
    ok = False
    for ty in types or ["any"]:
        if ty == "any":
            ok = True
        elif ty == "integer" and isinstance(value, int) and not isinstance(value, bool):
            ok = True
        elif ty == "number" and isinstance(value, int | float) and not isinstance(value, bool):
            ok = True
        elif ty == "string" and isinstance(value, str):
            ok = True
        elif ty == "boolean" and isinstance(value, bool):
            ok = True
        elif ty == "array" and isinstance(value, list):
            ok = True
            for i, item in enumerate(value):
                _check(item, schema.get("items", {}), f"{path}[{i}]", issues)
        elif ty == "object" and isinstance(value, dict):
            ok = True
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in value:
                    issues.append(f"{path}.{k}: required")
            for k, v in value.items():
                if k in props:
                    _check(v, props[k], f"{path}.{k}", issues)
                elif schema.get("additionalProperties") is False:
                    issues.append(f"{path}.{k}: unknown field")
        elif ty == "null":
            continue
    if not ok:
        issues.append(f"{path}: expected {'/'.join(types)}")
    if "enum" in schema and value not in schema["enum"]:
        issues.append(f"{path}: must be one of {schema['enum']}")


def validate_params(kind: str, params: dict[str, Any], hardness: str | None = None) -> list[str]:
    """Problems with ``params`` (and ``hardness``) for ``kind``; empty list = valid."""
    spec = KINDS.get(kind)
    if spec is None:
        return [f"unknown constraint kind '{kind}'"]
    issues: list[str] = []
    if not spec.registered:
        issues.append(f"kind '{kind}' is not registered in the solver")
    if hardness and hardness not in spec.allowed_hardness:
        issues.append(f"kind '{kind}' cannot be {hardness}")
    # 'match' accepts str or list in the solver; normalise before checking
    schema = spec.params_schema
    params = {k: v for k, v in params.items() if not str(k).startswith("_")}  # metadata such as _source_ref
    if isinstance(params.get("match"), list):
        schema = {**schema, "properties": {**schema["properties"], "match": _arr(_s("string"))}}
    _check(params, schema, "params", issues)
    return issues


# ---------------------------------------------------------------------------
# Tool definitions (strict)
# ---------------------------------------------------------------------------


def _proposal_props() -> dict[str, dict[str, Any]]:
    return {
        "kind": _s("string", enum=list(KIND_NAMES)),
        "hardness": _s("string", enum=list(HARDNESS)),
        "weight": _s("integer", description="1..10 for soft rules (10 = very important); 0 for hard rules"),
        "title": _s("string", description="short label in the user's language"),
        "nl_text": _s("string", description="the exact sentence of the user's text this rule comes from"),
        "rationale": _s("string", description="one sentence: why this kind and these params"),
        "confidence": _s("number", description="0..1 how sure the mapping is"),
        "source_ref": _s("integer", description="row / paragraph number given in the input ([R12] => 12); 0 = none"),
        "selector": MODEL_SELECTOR_SCHEMA,
        "params": MODEL_PARAMS_SCHEMA,
    }


#: Model-facing section edit (used by file ingestion and by chat tools).
SECTION_TARGET_PROPS: dict[str, dict[str, Any]] = {
    "section_ids": _arr(_s("integer"), description="ids returned by find_sections; [] when naming by course"),
    "course_codes": _arr(_s("string"), description="course codes as written; [] when using section_ids"),
    "program_name": _s("string", description="narrow course codes to one programme; '' = all"),
    "section_label": _s("string", description="şube / section label, e.g. '1'; '' = all sections"),
}

SECTION_FIELD_PROPS: dict[str, dict[str, Any]] = {
    "enrolment": _s("integer", description="new student count; 0 = keep"),
    "day": _s("integer", description="new day 1..7; 0 = keep"),
    "start_period": _s("integer", description="new first period 1..18; 0 = keep"),
    "end_period": _s("integer", description="new last period 1..18; 0 = keep"),
    "mode": _s("string", enum=["", "F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"]),
    "preferred_room_codes": _arr(_s("string"), description="ordered preferred rooms as written; [] = keep"),
}


def _section_edit_schema() -> dict[str, Any]:
    return strict_object(
        {
            "op": _s("string", enum=["include", "exclude", "set_field"]),
            **SECTION_TARGET_PROPS,
            **SECTION_FIELD_PROPS,
            "nl_text": _s("string"),
            "rationale": _s("string"),
            "confidence": _s("number"),
            "source_ref": _s("integer", description="row / paragraph number; 0 = none"),
        }
    )


PROPOSE_CONSTRAINTS_TOOL: dict[str, Any] = {
    "name": "propose_constraints",
    "description": (
        "Turn the planner's text (or an uploaded preference file) into typed scheduling rules from the "
        "catalogue and, when the text asks to add/drop sections or change a section's enrolment, day/time, "
        "mode or preferred rooms, into section edits. Call it exactly once with everything you could map; "
        "put sentences you could not map into 'unparsed'. Never invent ids: name rooms, programmes, courses "
        "and instructors exactly as written."
    ),
    "strict": True,
    "input_schema": strict_object(
        {
            "proposals": _arr(strict_object(_proposal_props())),
            "section_edits": _arr(_section_edit_schema()),
            "unparsed": _arr(
                strict_object(
                    {"text": _s("string"), "reason": _s("string"), "source_ref": _s("integer", description="0 = none")}
                )
            ),
        }
    ),
}


def _tool(name: str, description: str, props: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "description": description, "strict": True, "input_schema": strict_object(props)}


_REASON = {"reason": _s("string", description="why, in the user's language")}

#: Read-only tools: executed immediately during the chat loop (results come from the database).
READ_TOOLS: list[dict[str, Any]] = [
    _tool(
        "find_assignments",
        "Look up placed events of this run by course code / label text, room, day or week. Returns the "
        "assignment ids you must use for edits.",
        {
            "query": _s("string", description="course code or label substring, e.g. 'PHAR 240'; '' = any"),
            "room_code": _s("string", description="'' = any"),
            "day": _s("integer", description="0 = any"),
            "week": _s("integer", description="0 = any"),
            "limit": _s("integer", description="max rows, <= 40"),
        },
    ),
    _tool(
        "room_schedule",
        "Occupied periods of a room on a day (optionally one week): who is there and which periods are free.",
        {"room_code": _s("string"), "day": _s("integer"), "week": _s("integer", description="0 = all weeks")},
    ),
    _tool(
        "find_sections",
        "Look up sections of the run's term by course code (optionally programme): ids, enrolment, mode, "
        "meetings and whether they are planned for a room. Use before section edits.",
        {"course_code": _s("string"), "program_name": _s("string", description="'' = any")},
    ),
    _tool(
        "explain_assignment",
        "Structured reasons for one placement (capacity, tags, pins, constraints, alternatives). Read-only.",
        {"assignment_id": _s("integer")},
    ),
]

#: Mutation tools: recorded into the ProposedDiff, never executed by the chat loop.
EDIT_TOOLS: list[dict[str, Any]] = [
    _tool(
        "move_event",
        "Propose moving one assignment to another day/periods/rooms/weeks (0 / [] = keep). The server "
        "validates it with the solver when the planner applies the diff.",
        {
            "assignment_id": _s("integer"),
            "day": _s("integer", description="0 = keep"),
            "start_period": _s("integer", description="0 = keep"),
            "end_period": _s("integer", description="0 = keep (duration preserved)"),
            "room_codes": _arr(_s("string"), description="[] = keep"),
            "weeks": _arr(_s("integer"), description="[] = keep"),
            **_REASON,
        },
    ),
    _tool(
        "swap_rooms",
        "Propose swapping the rooms of two assignments.",
        {"assignment_id_a": _s("integer"), "assignment_id_b": _s("integer"), **_REASON},
    ),
    _tool(
        "lock_assignment",
        "Propose locking an assignment so re-solves keep it.",
        {"assignment_id": _s("integer"), **_REASON},
    ),
    _tool("unlock_assignment", "Propose unlocking an assignment.", {"assignment_id": _s("integer"), **_REASON}),
    _tool(
        "add_constraint",
        "Propose a new rule from the catalogue (names only, ids are resolved by the server).",
        _proposal_props(),
    ),
    _tool(
        "remove_constraint",
        "Propose disabling an existing constraint by id (ids from the context list only).",
        {"constraint_id": _s("integer"), **_REASON},
    ),
    _tool(
        "set_weight",
        "Propose changing the weight (1..10, 0 = keep) and/or hardness ('' = keep) of an existing constraint.",
        {
            "constraint_id": _s("integer"),
            "weight": _s("integer"),
            "hardness": _s("string", enum=["", *HARDNESS]),
            **_REASON,
        },
    ),
    _tool(
        "include_sections",
        "Propose including sections in room planning again (they get rooms on the next solve).",
        {**SECTION_TARGET_PROPS, **_REASON},
    ),
    _tool(
        "exclude_sections",
        "Propose excluding sections from room planning (e.g. moved online, cancelled).",
        {**SECTION_TARGET_PROPS, **_REASON},
    ),
    _tool(
        "set_section_field",
        "Propose changing a section's enrolment, day/time, mode or preferred rooms (0 / '' / [] = keep).",
        {**SECTION_TARGET_PROPS, **SECTION_FIELD_PROPS, **_REASON},
    ),
    _tool(
        "re_solve",
        "Propose re-running the solver after the edits (stability=true keeps the current plan as close as possible).",
        {"stability": _s("boolean"), **_REASON},
    ),
]

CHAT_TOOLS: list[dict[str, Any]] = READ_TOOLS + EDIT_TOOLS
READ_TOOL_NAMES = frozenset(t["name"] for t in READ_TOOLS)
EDIT_TOOL_NAMES = frozenset(t["name"] for t in EDIT_TOOLS)

#: Documented structured-output limits (claude-api skill / structured-outputs docs).
MAX_STRICT_TOOLS = 20
MAX_OPTIONAL_PARAMS = 24
MAX_UNION_PARAMS = 16


def schema_complexity(tools: list[dict[str, Any]]) -> dict[str, int]:
    """Count what the API limits across all strict tools of one request."""
    counts = {"strict_tools": 0, "optional_params": 0, "union_params": 0, "non_strict_objects": 0}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                req = set(node.get("required", []))
                counts["optional_params"] += sum(1 for k in props if k not in req)
                if node.get("additionalProperties") is not False:
                    counts["non_strict_objects"] += 1
                for v in props.values():
                    if isinstance(v, dict) and ("anyOf" in v or isinstance(v.get("type"), list)):
                        counts["union_params"] += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for t in tools:
        if t.get("strict"):
            counts["strict_tools"] += 1
            walk(t["input_schema"])
    return counts


def tool_by_name(name: str) -> dict[str, Any] | None:
    return next((t for t in [PROPOSE_CONSTRAINTS_TOOL, *CHAT_TOOLS] if t["name"] == name), None)


def validate_tool_input(name: str, data: Any) -> list[str]:
    """Client-side re-validation of a tool input against its strict schema (never trust the model)."""
    tool = tool_by_name(name)
    if tool is None:
        return [f"unknown tool '{name}'"]
    issues: list[str] = []
    _check(data, tool["input_schema"], "input", issues)
    return issues


def catalog_dict() -> dict[str, Any]:
    """Payload of ``GET /ai/catalog`` for the UI."""
    return {
        "kinds": [spec.to_dict() for spec in KINDS.values()],
        "tools": [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in [PROPOSE_CONSTRAINTS_TOOL, *CHAT_TOOLS]
        ],
        "selectors": {"resolved": SELECTOR_SCHEMA, "model": MODEL_SELECTOR_SCHEMA},
    }


#: Which model-facing params (MODEL_PARAMS_SCHEMA) each kind reads; shown in the prompt.
MODEL_FIELDS_BY_KIND: dict[str, str] = {
    "capacity": "amount=seats needed",
    "no_room_overlap": "- (always on)",
    "no_cohort_overlap": "- (always on)",
    "no_instructor_overlap": "- (always on)",
    "fixed_time": "days=[day], amount=start period",
    "room_tags": "required_tags / forbidden_tags",
    "room_pin": "room_codes (+ weeks / from_date / to_date / last_n_weeks)",
    "room_forbid": "room_codes",
    "building_preference": "buildings (+ days)",
    "room_preference": "room_codes in preference order",
    "same_room_across_weeks": "selector.course_codes",
    "same_room_group": "selector.course_codes (2+)",
    "min_capacity_waste": "amount=seats per penalty unit (default 10)",
    "exam_gap": "amount=min free periods",
    "max_exams_per_day": "amount=n",
    "stability": "selector only",
    "room_closed": "room_codes=[one room], days, periods or earliest..latest, weeks / from_date / to_date, label",
    "day_window": "periods or earliest..latest (+ days)",
    "evening_programs_in_buildings": "buildings",
}


def catalog_prompt(lang: str = "tr") -> str:
    """Compact catalogue text for the system prompt (stable => cacheable)."""
    lines = []
    for spec in KINDS.values():
        if not spec.registered:
            continue
        hard = "/".join(spec.allowed_hardness)
        ex = "; ".join(f"'{e['nl']}'" for e in spec.examples[:2])
        desc = spec.description.get(lang) or spec.description["en"]
        fields = MODEL_FIELDS_BY_KIND.get(spec.kind, "selector")
        sel = "" if spec.selectable else " (no selector)"
        lines.append(
            f"- {spec.kind} [{hard}, default {spec.default_hardness}; params: {fields}{sel}]: {desc}"
            + (f" e.g. {ex}" if ex else "")
        )
    return "\n".join(lines)


__all__ = [
    "CHAT_TOOLS",
    "EDIT_TOOLS",
    "EDIT_TOOL_NAMES",
    "HARDNESS",
    "KINDS",
    "KIND_NAMES",
    "MODEL_FIELDS_BY_KIND",
    "MODEL_PARAMS_SCHEMA",
    "MODEL_SELECTOR_SCHEMA",
    "PROPOSE_CONSTRAINTS_TOOL",
    "SECTION_FIELD_PROPS",
    "SECTION_TARGET_PROPS",
    "READ_TOOLS",
    "READ_TOOL_NAMES",
    "SELECTOR_SCHEMA",
    "KindSpec",
    "catalog_dict",
    "catalog_prompt",
    "schema_complexity",
    "strict_object",
    "tool_by_name",
    "validate_params",
    "validate_tool_input",
]
