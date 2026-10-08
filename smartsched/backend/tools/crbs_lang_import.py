"""Import the classroombookings (CRBS) language files as SmartSched message catalogues (ROADMAP P18-LANG).

CRBS ships 13 UI languages under ``crbs-core/application/language/<language>/*.php`` (English is the source;
the English CodeIgniter system strings live in ``crbs-core/system/language/english``). This tool

* parses those PHP files **without executing PHP**: a small tokenizer reads ``$lang['key'] = '...';`` and
  ``$lang = ['key' => '...', ...];`` with single- or double-quoted literals, ``.`` concatenation and
  comments; anything else (variables, function calls, heredocs) is skipped, never evaluated;
* maps CRBS keys to SmartSched message keys: a SmartSched key is *CRBS-shared* when its English text is the
  English text of a CRBS key (exact match after HTML-entity decoding and whitespace trimming) or it is listed
  in :data:`EXPLICIT`; the CRBS translation is used only when its placeholders are the SmartSched ones;
* writes ``smartsched/frontend/messages/<code>.json`` (sparse: only keys CRBS translates; every other key
  falls back to English per key at runtime), the shared locale data (CRBS day and month names, the ICU
  default date patterns) for the frontend and the backend, and the coverage report.

Nothing is machine-translated: a string CRBS does not translate stays English (organisations fill the rest in
Settings → Translations, ``GET /org/i18n`` overlays them at runtime).

    python -m tools.crbs_lang_import            # from smartsched/backend: regenerate everything
    python -m tools.crbs_lang_import --check    # exit 1 when a generated file is stale
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent.parent
CRBS = ROOT / "crbs-core"
FRONTEND = BACKEND.parent / "frontend"
MESSAGES = FRONTEND / "messages"
FRONTEND_DATA = FRONTEND / "src" / "lib" / "i18n" / "locale-data.json"
BACKEND_DATA = BACKEND / "app" / "services" / "crbs_lang_data.json"
REPORT = ROOT / "docs" / "testing" / "language-coverage.md"


@dataclass(frozen=True)
class Language:
    code: str  # SmartSched code (profile language, org default, cookie, message file name)
    crbs: str  # CRBS folder under application/language
    name: str  # endonym (ICU ``Intl.DisplayNames`` of the language in itself, first letter upper-cased)
    tag: str  # BCP 47 tag for Intl (numbers, plural rules)
    #: CRBS "(Default)" date formats = ``IntlDateFormatter`` FULL / MEDIUM / SHORT of the locale and the numeric
    #: day-month-year order (ICU 77 / CLDR 47, read with ``Intl.DateTimeFormat#formatToParts``; the tr and en
    #: rows reproduce the tables SmartSched already shipped)
    long: str
    weekday: str
    time: str
    short: str


#: the 12 CRBS languages besides English, in SmartSched code order; ``tr`` and ``en`` are SmartSched's own
LANGUAGES: tuple[Language, ...] = (
    Language("cs", "czech", "Čeština", "cs", "EEEE d. MMMM yyyy", "d. M. yyyy", "H:mm", "dd. MM. yyyy"),
    Language("cy", "welsh", "Cymraeg", "cy", "EEEE, d MMMM yyyy", "d MMM yyyy", "HH:mm", "dd/MM/yyyy"),
    Language("da", "danish", "Dansk", "da", "EEEE' den 'd. MMMM yyyy", "d. MMM yyyy", "HH.mm", "dd.MM.yyyy"),
    Language("de", "german", "Deutsch", "de", "EEEE, d. MMMM yyyy", "dd.MM.yyyy", "HH:mm", "dd.MM.yyyy"),
    Language("es", "spanish", "Español", "es", "EEEE, d' de 'MMMM' de 'yyyy", "d MMM yyyy", "H:mm", "dd/MM/yyyy"),
    Language("fi", "finnish", "Suomi", "fi", "EEEE d. MMMM yyyy", "d.M.yyyy", "H.mm", "dd.MM.yyyy"),
    Language("fr", "french", "Français", "fr", "EEEE d MMMM yyyy", "d MMM yyyy", "HH:mm", "dd/MM/yyyy"),
    Language("it", "italian", "Italiano", "it", "EEEE d MMMM yyyy", "d MMM yyyy", "HH:mm", "dd/MM/yyyy"),
    Language("nl", "dutch", "Nederlands", "nl", "EEEE d MMMM yyyy", "d MMM yyyy", "HH:mm", "dd-MM-yyyy"),
    Language(
        "pt", "portuguese", "Português", "pt-PT", "EEEE, d' de 'MMMM' de 'yyyy", "dd/MM/yyyy", "HH:mm", "dd/MM/yyyy"
    ),
    Language(
        "pt-br",
        "portuguese-brazilian",
        "Português (Brasil)",
        "pt-BR",
        "EEEE, d' de 'MMMM' de 'yyyy",
        "d' de 'MMM' de 'yyyy",
        "HH:mm",
        "dd/MM/yyyy",
    ),
    Language("sv", "swedish", "Svenska", "sv", "EEEE d MMMM yyyy", "d MMM yyyy", "HH:mm", "yyyy-MM-dd"),
)
CODES = tuple(lang.code for lang in LANGUAGES)

#: SmartSched key -> CRBS key where the English texts differ but the meaning is the CRBS string
#: (checked: the key must exist in CRBS English; an entry whose SmartSched key is gone is reported)
EXPLICIT: dict[str, str] = {}

#: CRBS catalogues never used as a source: developer-tool texts (unit-test report, profiler, database, FTP,
#: image library, migrations) whose words mean something else on a SmartSched screen (``ut_failed`` is a failed
#: test, German "Durchgefallen", not a failed job)
DENY_PREFIXES: tuple[str, ...] = ("ut_", "profiler_", "db_", "ftp_", "imglib_", "migration_")

#: key prefixes of the CodeIgniter system catalogues (the only ones CRBS translates)
SYSTEM_PREFIXES: tuple[str, ...] = (
    "cal_",
    "date_",
    "form_validation_",
    "pagination_",
    "upload_",
    "email_",
    "terabyte_",
    "gigabyte_",
    "megabyte_",
    "kilobyte_",
    "bytes",
    *DENY_PREFIXES,
)

#: SmartSched keys with the English text of a CRBS string but another meaning (never taken from CRBS)
NOT_SHARED: dict[str, str] = {
    "classes.col.year": "grade level (tr 'Sınıf'), CRBS date_year is a calendar year",
    "classes.f.year": "grade level (tr 'Sınıf'), CRBS date_year is a calendar year",
    "studio.classes.col.year": "grade level (tr 'Sınıf'), CRBS date_year is a calendar year",
    "studio.classes.year": "grade level (tr 'Sınıf'), CRBS date_year is a calendar year",
}

#: defects in the CRBS files, fixed from the same file (each one is listed in the coverage report)
CORRECTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "it": {"cal_sat": ("Sab", "CRBS has 'Dom' (Sunday) for Saturday; 'Sab' = its own cal_saturday 'Sabato'")},
}

_CAL_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "mayl",  # CodeIgniter's key for the full name of May ("may" is the short one)
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_CAL_MONTHS_SHORT = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_CAL_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_CAL_WEEKDAYS_SHORT = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


# --------------------------------------------------------------------------------------------------
# PHP language file tokenizer (never executes PHP)
# --------------------------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|\#[^\n]*|/\*.*?\*/)
  | (?P<sq>'(?:[^'\\]|\\.)*')
  | (?P<dq>"(?:[^"\\]|\\.)*")
  | (?P<var>\$[A-Za-z_][A-Za-z0-9_]*)
  | (?P<arrow>=>)
  | (?P<op>[\[\]=;,.()])
  | (?P<open><\?php)
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)
_DQ_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "v": "\v", "f": "\f", "\\": "\\", '"': '"', "$": "$", "e": "\x1b"}


def _single(body: str) -> str:
    return re.sub(r"\\([\\'])", r"\1", body)


def _double(body: str) -> str | None:
    """A double-quoted literal; ``None`` when it interpolates a variable (not a constant string)."""
    if re.search(r"(?<!\\)\$[A-Za-z_{]", body):
        return None
    return re.sub(r"\\(.)", lambda m: _DQ_ESCAPES.get(m.group(1), "\\" + m.group(1)), body, flags=re.DOTALL)


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup or "other"
        if kind in ("ws", "comment", "open"):
            continue
        value = m.group()
        if kind == "sq":
            out.append(("str", _single(value[1:-1])))
        elif kind == "dq":
            s = _double(value[1:-1])
            out.append(("str", s) if s is not None else ("bad", value))
        else:
            out.append((kind, value))
    return out


def _literal(toks: list[tuple[str, str]], i: int) -> tuple[str | None, int]:
    """``'a' . "b"`` starting at ``i`` -> (text, index after it); (None, i) when it is not a constant string."""
    if i >= len(toks) or toks[i][0] != "str":
        return None, i
    parts = [toks[i][1]]
    i += 1
    while i + 1 < len(toks) and toks[i] == ("op", ".") and toks[i + 1][0] == "str":
        parts.append(toks[i + 1][1])
        i += 2
    return "".join(parts), i


def parse_php_lang(text: str) -> dict[str, str]:
    """``$lang[...]`` assignments of one CRBS language file -> key -> text (later assignments win, as in PHP)."""
    toks = _tokens(text)
    out: dict[str, str] = {}
    i = 0
    while i < len(toks):
        if toks[i] != ("var", "$lang"):
            i += 1
            continue
        # $lang['key'] = <literal> ;
        if i + 4 < len(toks) and toks[i + 1] == ("op", "[") and toks[i + 2][0] == "str" and toks[i + 3] == ("op", "]"):
            key = toks[i + 2][1]
            if toks[i + 4] == ("op", "="):
                value, j = _literal(toks, i + 5)
                if value is not None and j < len(toks) and toks[j] == ("op", ";"):
                    out[key] = value
                    i = j + 1
                    continue
            i += 1
            continue
        # $lang = [ 'key' => <literal>, ... ];   /   $lang = array( ... );
        if i + 2 < len(toks) and toks[i + 1] == ("op", "="):
            j = i + 2
            if toks[j] == ("op", "["):
                close = "]"
                j += 1
            elif toks[j] == ("word", "array") and j + 1 < len(toks) and toks[j + 1] == ("op", "("):
                close = ")"
                j += 2
            else:
                i += 1
                continue
            while j < len(toks) and toks[j] != ("op", close):
                if toks[j][0] == "str" and j + 1 < len(toks) and toks[j + 1] == ("arrow", "=>"):
                    key = toks[j][1]
                    value, k = _literal(toks, j + 2)
                    if value is not None:
                        out[key] = value
                        j = k
                        continue
                j += 1
            i = j + 1
            continue
        i += 1
    return out


def read_language(folder: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for php in sorted(folder.glob("*.php")):
        out.update(parse_php_lang(php.read_text(encoding="utf-8")))
    return out


# --------------------------------------------------------------------------------------------------
# mapping
# --------------------------------------------------------------------------------------------------


def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        elif isinstance(v, str):
            out[f"{prefix}{k}"] = v
    return out


def nest(flat: dict[str, str], order: list[str]) -> dict[str, Any]:
    """Flat keys -> nested dict, in the key order of ``en.json`` (stable diffs)."""
    out: dict[str, Any] = {}
    for key in order:
        if key not in flat:
            continue
        node = out
        *parents, leaf = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = flat[key]
    return out


def norm(text: str) -> str:
    """CRBS texts carry HTML entities (``&lsaquo; First``); React escapes, so compare and ship decoded text."""
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


_PH = re.compile(r"\{(\w+)\}|%(?:\d+\$)?[sdf]")


def placeholders(text: str) -> list[str]:
    return sorted(m.group(0) for m in _PH.finditer(text))


@dataclass
class Result:
    english: dict[str, str]  # CRBS English key -> text
    sources: dict[str, dict[str, str]]  # code -> CRBS key -> text
    mapping: dict[str, str]  # SmartSched key -> CRBS key
    catalogues: dict[str, dict[str, str]]  # code -> SmartSched key -> translated text (flat)
    total: int
    order: list[str]
    rejected: dict[str, list[str]] = field(default_factory=dict)  # code -> keys with mismatched placeholders
    stale_explicit: list[str] = field(default_factory=list)


def build(crbs: Path = CRBS, messages: Path = MESSAGES) -> Result:
    english: dict[str, str] = {}
    english.update(read_language(crbs / "system" / "language" / "english"))
    english.update(read_language(crbs / "application" / "language" / "english"))
    sources = {lang.code: read_language(crbs / "application" / "language" / lang.crbs) for lang in LANGUAGES}
    for code, fixes in CORRECTIONS.items():
        for key, (text, _why) in fixes.items():
            sources[code][key] = text

    en_tree = json.loads((messages / "en.json").read_text(encoding="utf-8"))
    en = flatten(en_tree)
    order = list(en)

    # English text -> CRBS keys with that text; a key translated by more CRBS languages wins
    by_text: dict[str, list[str]] = {}
    for key, text in english.items():
        if key.startswith(DENY_PREFIXES):
            continue
        by_text.setdefault(norm(text), []).append(key)
    for keys in by_text.values():
        keys.sort(key=lambda k: (-sum(k in s for s in sources.values()), k))

    mapping: dict[str, str] = {}
    for key, text in en.items():
        if key in NOT_SHARED:
            continue
        hits = by_text.get(norm(text))
        if hits:
            mapping[key] = hits[0]
    stale = []
    for ss_key, crbs_key in EXPLICIT.items():
        if ss_key in en and crbs_key in english:
            mapping[ss_key] = crbs_key
        else:
            stale.append(ss_key)

    catalogues: dict[str, dict[str, str]] = {}
    rejected: dict[str, list[str]] = {}
    for lang in LANGUAGES:
        cat: dict[str, str] = {}
        for ss_key, crbs_key in mapping.items():
            text = sources[lang.code].get(crbs_key)
            if text is None or not norm(text):
                continue
            if placeholders(text) != placeholders(en[ss_key]):
                rejected.setdefault(lang.code, []).append(ss_key)
                continue
            cat[ss_key] = norm(text)
        catalogues[lang.code] = cat
    return Result(english, sources, mapping, catalogues, len(en), order, rejected, stale)


# --------------------------------------------------------------------------------------------------
# outputs
# --------------------------------------------------------------------------------------------------


def _names(src: dict[str, str], english: dict[str, str], keys: tuple[str, ...]) -> tuple[list[str], int]:
    """CRBS ``cal_*`` names of one language; a name CRBS lacks falls back to English (and is counted)."""
    out, fallback = [], 0
    for k in keys:
        text = src.get(f"cal_{k}")
        if text is None or not norm(text):
            fallback += 1
            text = english[f"cal_{k}"]
        out.append(norm(text))
    return out, fallback


def locale_data(res: Result) -> dict[str, Any]:
    langs: dict[str, Any] = {}
    for lang in LANGUAGES:
        src = res.sources[lang.code]
        months, f1 = _names(src, res.english, _CAL_MONTHS)
        months_short, f2 = _names(src, res.english, _CAL_MONTHS_SHORT)
        weekdays, f3 = _names(src, res.english, _CAL_WEEKDAYS)
        weekdays_short, f4 = _names(src, res.english, _CAL_WEEKDAYS_SHORT)
        for table in (months, months_short, weekdays, weekdays_short):
            if len(set(table)) != len(table):
                raise ValueError(f"{lang.code}: duplicate CRBS date names {table}; add a CORRECTIONS entry")
        langs[lang.code] = {
            "name": lang.name,
            "crbs": lang.crbs,
            "tag": lang.tag,
            "months": months,
            "months_short": months_short,
            "weekdays": weekdays,
            "weekdays_short": weekdays_short,
            "date_names_fallback": f1 + f2 + f3 + f4,
            "date_defaults": {"long": lang.long, "weekday": lang.weekday, "time": lang.time},
            "short": lang.short,
            "translated": len(res.catalogues[lang.code]),
            "total": res.total,
        }
    return {
        "_source": "generated by smartsched/backend/tools/crbs_lang_import.py from crbs-core/application/language; "
        "do not edit by hand",
        "languages": langs,
    }


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def report(res: Result, data: dict[str, Any]) -> str:
    shared = len(res.mapping)
    lines = [
        "# Language coverage (P18-LANG)",
        "",
        f"Generated by `smartsched/backend/tools/crbs_lang_import.py` on {dt.date.today().isoformat()} from the "
        "classroombookings language files in `crbs-core/application/language/<language>/*.php`. Do not edit by "
        "hand; rerun the tool.",
        "",
        "## What CRBS actually translates",
        "",
        "The 12 non-English CRBS language folders contain only the CodeIgniter system catalogues (calendar, date, "
        "form validation, pagination, upload, e-mail, database, FTP, image library, migration, number, profiler, "
        "unit test; about 275 strings each). The CRBS application strings (`booking_lang.php`, `room_lang.php`, "
        "`setup_lang.php`, ...) exist **in English only**, so CRBS itself shows its screens in English when one "
        "of those languages is chosen. SmartSched reuses every CRBS translation that matches one of its strings "
        "and keeps English for the rest, as instructed: nothing here is machine-translated.",
        "",
        f"- SmartSched message keys (en.json): **{res.total}**",
        f"- keys whose English text is a CRBS string (CRBS-shared): **{shared}** "
        f"({sum(1 for k in res.mapping.values() if k.startswith(SYSTEM_PREFIXES))} "
        "from the CodeIgniter system catalogues, the rest from the English-only application catalogues)",
        "- every key CRBS does not translate falls back to **English per key** at runtime "
        "(`translate()` in `smartsched/frontend/src/lib/i18n/index.ts`); an organisation fills in the rest in "
        "Admin → Settings → Translations (`GET /org/i18n` overlays them without a rebuild)",
        "",
        "## Per language",
        "",
        "| Code | Language | CRBS folder | From CRBS | English fallback | Coverage | Date names from CRBS |",
        "|---|---|---|---:|---:|---:|---:|",
        f"| tr | Türkçe | - | {res.total} (SmartSched's own) | 0 | 100% | own table |",
        f"| en | English | english | {res.total} (source) | - | 100% | source |",
    ]
    for lang in LANGUAGES:
        d = data["languages"][lang.code]
        n = d["translated"]
        pct = 100 * n / res.total if res.total else 0
        names = 38 - d["date_names_fallback"]
        lines.append(f"| {lang.code} | {lang.name} | {lang.crbs} | {n} | {res.total - n} | {pct:.1f}% | {names}/38 |")
    lines += [
        "",
        '"Date names" are the 12 + 12 month and 7 + 7 weekday names (CRBS `calendar_lang.php`) used by the '
        "booking grid, the date picker, the e-mails and every organisation date pattern, in both the frontend "
        "(`src/lib/i18n/locale-data.json`) and the backend (`app/services/crbs_lang_data.json`). The default "
        'date patterns (CRBS "(Default)" = `IntlDateFormatter` FULL / MEDIUM / SHORT) are the ICU patterns of '
        "each locale.",
        "",
        "## Keys taken from CRBS",
        "",
        "| SmartSched key | CRBS key | English | " + " | ".join(lang.code for lang in LANGUAGES) + " |",
        "|---|---|---|" + "---|" * len(LANGUAGES),
    ]
    translated_keys = sorted({k for cat in res.catalogues.values() for k in cat})
    en = flatten(json.loads((MESSAGES / "en.json").read_text(encoding="utf-8"))) if MESSAGES.exists() else {}
    for key in translated_keys:
        cells = [res.catalogues[lang.code].get(key, "-") for lang in LANGUAGES]
        lines.append(
            f"| `{key}` | `{res.mapping[key]}` | {en.get(key, '')} | "
            + " | ".join(c.replace("|", "\\|") for c in cells)
            + " |"
        )
    shared_only = sorted(k for k in res.mapping if k not in translated_keys)
    lines += [
        "",
        f"## CRBS-shared keys CRBS does not translate ({len(shared_only)})",
        "",
        "These SmartSched strings are CRBS strings too, but CRBS only has them in English (application "
        "catalogues), so they read the same in CRBS and SmartSched for the 12 languages:",
        "",
        ", ".join(f"`{k}` ({res.mapping[k]})" for k in shared_only) or "-",
        "",
    ]
    if any(res.rejected.values()):
        lines += ["## Skipped (placeholders differ from the SmartSched string)", ""]
        for code, keys in res.rejected.items():
            lines.append(f"- {code}: " + ", ".join(f"`{k}`" for k in keys))
        lines.append("")
    lines += ["## Corrections of CRBS defects", ""]
    for code, fixes in CORRECTIONS.items():
        for key, (text, why) in fixes.items():
            lines.append(f"- {code} `{key}` = {text!r}: {why}")
    lines += [
        "",
        "## Not taken from CRBS (same English word, other meaning)",
        "",
        "- CRBS catalogues skipped as a source: " + ", ".join(f"`{p}*`" for p in DENY_PREFIXES) + " (developer tools)",
    ]
    lines += [f"- `{k}`: {why}" for k, why in NOT_SHARED.items()]
    lines += [
        "",
        "## Backend texts",
        "",
        "- E-mails (`app/services/bookings_i18n.py` `BASE_STRINGS`, set `email`): Turkish and English are "
        "SmartSched's own; CRBS has no translated e-mail texts (its `email_lang.php` holds the mailer's error "
        "messages), so the 12 languages send the English text per key unless the organisation overrides it. Dates "
        "inside the e-mails use the recipient's language with the CRBS day and month names.",
        "- iCalendar feeds carry no translatable words (room, period, notes, user name, `SmartSched – <name>`).",
        "- CSV export: CRBS writes fixed English column names and MySQL `DAYNAME()` weekdays in every language "
        "(`Bookings_model::export_unbuffered`); SmartSched does the same.",
        "- Run diagnoses and data issues are Turkish/English pairs; the 12 languages show the English text.",
        "",
    ]
    return "\n".join(lines)


def outputs(res: Result) -> dict[Path, str]:
    data = locale_data(res)
    files: dict[Path, str] = {}
    for lang in LANGUAGES:
        files[MESSAGES / f"{lang.code}.json"] = _json(nest(res.catalogues[lang.code], res.order))
    files[FRONTEND_DATA] = _json(data)
    files[BACKEND_DATA] = _json(data)
    files[REPORT] = report(res, data)
    return files


def _without_date(text: str) -> str:
    return re.sub(r"on \d{4}-\d{2}-\d{2} from", "on <date> from", text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when a generated file differs (writes nothing)")
    args = ap.parse_args(argv)
    if not (CRBS / "application" / "language").is_dir():
        print(f"CRBS language files not found under {CRBS}", file=sys.stderr)
        return 2
    res = build()
    stale = []
    for path, text in outputs(res).items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        same = old is not None and (old == text or (path == REPORT and _without_date(old) == _without_date(text)))
        if same:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for code, keys in res.rejected.items():
        print(f"{code}: {len(keys)} CRBS translation(s) skipped (placeholders differ)", file=sys.stderr)
    if res.stale_explicit:
        print(f"EXPLICIT entries without a key: {', '.join(res.stale_explicit)}", file=sys.stderr)
    for lang in LANGUAGES:
        n = len(res.catalogues[lang.code])
        print(f"{lang.code:6} {lang.crbs:22} {n:4} / {res.total} from CRBS ({100 * n / res.total:.1f}%)")
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
