#!/usr/bin/env python3
"""KVKK: reduce instructor names to title + initials in a recording database, so no full name appears in a
recording or screenshot.

    python3 scripts/record/kvkk_mask.py DB [--check] [--save-names FILE] [--names FILE]
    python3 scripts/record/kvkk_mask.py DB --verify

DB is the throwaway SQLite database of the recording stack ($REC_WORKDIR/rec.db, see stack.sh). Never point it
at product data. Every instructor keeps its row, its id and its title; only the name changes:

    title "Dr. Öğr. Üyesi", full_name "Ahmet Can Küçükkurt"  ->  full_name "A. C. K."  (shown "Dr. Öğr. Üyesi A. C. K.")

The masked value is derived from the real name, so nothing is invented, and two instructors with the same
initials stay two rows (the ids differ), so the solver sees exactly the same data. The same replacement runs
over every text and JSON column (imported source rows, exam requests' instructor text, grid block labels, run
results): any run of two or more consecutive words of an instructor's name, in any casing ("Elif DORMAN",
"Merve ANTMEN" for "Fatma Merve Antmen"), becomes its initials, and so does a lone surname right after an initial
or a title ("D. D. Deliormanlı"), and a first name before "hoca" ("EMRAH HOCA" -> "E. HOCA"). JSON cells are decoded first, so \\u-escaped names are found too. Instructors'
e-mail addresses and phone numbers are cleared.

--save-names FILE writes the names found (before masking) to FILE, and --names FILE adds the names in FILE: the
fresh-database journeys (import-generate, onboarding-intake) import the workbooks during the take, so their
instructors are masked with the names saved by the seeded stack (stack.sh keeps FILE in $REC_WORKDIR, next to the
throwaway database, never in the repository).

--verify changes nothing: it is the KVKK check of docs/testing/flows/README.md §7. Every person name
(instructors.full_name and users.full_name, except the placeholder accounts) must consist of title tokens and
initials only ("Dr. Öğr. Üyesi A. C. K.", "Üye. E. N. K." where the workbook wrote "Dr. Öğr. Üye.", the hyphenated
"A. Y.-K."). It prints `left N` with the shapes of the rows that fail (first letter + "*", never the name) and exits
1 when N > 0. stack.sh runs it after every masking pass.

--check changes nothing and only reports. The last lines count the cells that still hold a whole word equal to
an original surname: these are ordinary words that happen to be surnames ("Bulut", "Bellek" in course names);
read the samples before publishing media.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter

# leading tokens that are (parts of) academic titles; kept as written
TITLE_TOKENS = {
    "prof.", "doç.", "dr.", "öğr.", "üyesi", "üye.", "gör.", "gör", "arş.", "uzm.", "eğt.", "eğitmen", "okt.", "ecz.",
    "öğretim", "görevlisi", "asst.", "assoc.", "yrd.", "doç", "prof", "dr", "öğr", "tek.", "okt", "hoca",
}
# words that make a free-text segment a unit, not a person ("Hemşirelik Bölümü")
NOT_A_NAME = re.compile(
    r"(?i)(bölüm|fakülte|okul|enstitü|merkez|hastane|koordinat|müdür|daire|birim|department|faculty|school|"
    r"program|ders|staj|lab|kulüp|toplantı|sınav|seminer|eğitim|klinik|ünite|anabilim)"
)
# a first name used with "hoca" ("EMRAH HOCA", "syb emre hoca dersi") -> its initial
HOCA = re.compile(r"(?<!\w)[^\W\d_]{2,}(?=\s+hoca(?:sı|nın|ya|yla)?(?!\w))")
TEXT_TYPES = ("CHAR", "TEXT", "JSON", "CLOB")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# an initial as initials() writes it: "K.", or one per part of a hyphenated name: "Y.-K."
INITIAL = re.compile(r"[^\W\d_]\.(?:-[^\W\d_]\.)*")
# accounts that stack.sh / the backend create with a role word, not a person's name
PLACEHOLDER_NAMES = {"Administrator", "Yönetici", "Akademik Personel"}


def upper_tr(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def lower_tr(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def is_title(w: str) -> bool:
    return lower_tr(w) in TITLE_TOKENS


def initial(w: str) -> str:
    """'Küçükkurt' -> 'K.'; hyphenated parts get one each ('Yılmaz-Kaya' -> 'Y.-K.')."""
    parts = [p for p in w.split("-") if any(ch.isalpha() for ch in p)]
    return "-".join(upper_tr(next(ch for ch in p if ch.isalpha())) + "." for p in parts)


def initials(name: str) -> str:
    """'Ahmet Can KÜÇÜKKURT' -> 'A. C. K.'; leading title fragments ('Üye.') are kept; '-' and digits dropped."""
    out: list[str] = []
    lead = True
    for w in name.split():
        if lead and is_title(w):
            out.append(w)
            continue
        lead = False
        if any(ch.isalpha() for ch in w):
            out.append(initial(w))
    return " ".join(out) or name


def name_words(full: str) -> list[str]:
    return [w for w in full.split() if not is_title(w) and any(ch.isalpha() for ch in w)]


def names_in_text(text: str) -> list[str]:
    """Free-text instructor cells ('Prof.Dr.Irmak D. Subaşı, Öğr. Gör. X Y') -> the names without titles."""
    spaced = re.sub(r"\.(?=[^\W\d_])", ". ", text)
    out = []
    for seg in re.split(r"[,;/&\n]+|\s+ve\s+|\s+-\s+", spaced):
        ws = name_words(seg)
        if ws and 2 <= len(ws) <= 5 and not any(NOT_A_NAME.search(w) for w in ws):
            out.append(" ".join(ws))
    return out


def trie_pattern(words: set[str]) -> str:
    """One pattern for many literal words, factored into a trie (a flat alternation of thousands of names is
    far too slow in Python's re); at each node the longer continuation is tried first."""
    root: dict = {}
    for w in words:
        node = root
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = True

    def build(node: dict) -> str:
        alts = [re.escape(ch) + build(child) for ch, child in sorted(node.items()) if ch]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
        return f"(?:{body})?" if "" in node else body

    return build(root)


def bounded(words: set[str]) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + trie_pattern(words) + r")(?!\w)")


class Masker:
    def __init__(self, full_names: list[str], vocabulary: set[str] = frozenset()) -> None:
        runs: set[str] = set()
        surnames: set[str] = set()
        for full in full_names:
            ws = name_words(full)
            if ws and len(ws[-1]) >= 3:
                surnames.add(lower_tr(ws[-1]))
            # every run of 2+ consecutive name words ("Merve Antmen" inside "Fatma Merve Antmen")
            for i in range(len(ws)):
                for j in range(i + 2, len(ws) + 1):
                    runs.add(lower_tr(" ".join(ws[i:j])))
        self.runs = bounded(runs) if runs else None
        # a lone surname right after an initial or a title: "D. D. Deliormanlı", "Dr. Arslan"
        # ("D. D. Deliormanlı", "Ö.KURT")
        self.lone = re.compile(r"(?:(?<=[^\W\d_]\. )|(?<=[^\W\d_]\.))(?:" + trie_pattern(surnames) + r")(?!\w)") if surnames else None
        self.surnames = surnames
        # a capitalised word + a surname that is not also an ordinary word ("Fatih DeMİR" in a grid note);
        # vocabulary = words of course, programme, faculty and room names ("Modern Türk Edebiyatı" stays)
        pair = {x for x in surnames if x not in vocabulary and len(x) >= 4}
        self.pair = re.compile(r"(?<!\w)[^\W\d_]{2,}\s+(?:" + trie_pattern(pair) + r")(?!\w)") if pair else None
        self.hits: Counter[str] = Counter()

    def _sub(self, rx: re.Pattern[str] | None, s: str, capital: bool = False) -> str:
        if rx is None:
            return s
        low = lower_tr(s)
        if len(low) != len(s):  # casing changed the length: match the text as written
            low = s
        out, last = [], 0
        for m in rx.finditer(low):
            if capital and not s[m.start()].isupper():
                continue
            out.append(s[last : m.start()])
            out.append(initials(s[m.start() : m.end()]))
            last = m.end()
            self.hits["names"] += 1
        out.append(s[last:])
        return "".join(out)

    def text(self, s: str) -> str:
        s = self._sub(self.lone, self._sub(self.runs, s))
        return self._sub(HOCA, self._sub(self.pair, s, capital=True))

    def value(self, v: object) -> object:
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if isinstance(v, dict):
            return {k: self.value(x) for k, x in v.items()}
        return v

    def cell(self, val: str) -> str:
        """A database cell; JSON (as SQLAlchemy writes it) is decoded, masked and written back the same way."""
        if val[:1] in "[{":
            try:
                data = json.loads(val)
            except ValueError:
                data = None
            if data is not None:
                for ascii_ in (True, False):
                    if json.dumps(data, ensure_ascii=ascii_) == val:
                        return json.dumps(self.value(data), ensure_ascii=ascii_)
        return self.text(val)


def readable(val: str) -> str:
    if val[:1] in "[{":
        try:
            return json.dumps(json.loads(val), ensure_ascii=False)
        except ValueError:
            pass
    return val


def text_columns(con: sqlite3.Connection) -> list[tuple[str, str]]:
    out = []
    for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
        for col in con.execute(f"pragma table_info('{t}')"):
            if any(k in (col[2] or "").upper() for k in TEXT_TYPES):
                out.append((t, col[1]))
    return out


def is_masked(name: str) -> bool:
    """True when every token is a title token or an initial (README §7)."""
    return all(is_title(w) or INITIAL.fullmatch(w) for w in name.split())


def verify(db: str) -> int:
    con = sqlite3.connect(db, timeout=60)
    left: list[str] = []
    for table in ("instructors", "users"):
        for (val,) in con.execute(f'select full_name from "{table}" where full_name is not null'):
            if val.strip() and val not in PLACEHOLDER_NAMES and not is_masked(val):
                left.append(table + ": " + " ".join(w if is_title(w) or INITIAL.fullmatch(w) else w[:1] + "*" for w in val.split()))
    con.close()
    print(f"left {len(left)}" + (f" ({'; '.join(left[:10])})" if left else ""))
    return 1 if left else 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    if "--verify" in argv:
        return verify(argv[0])
    db, check = argv[0], "--check" in argv

    def opt(flag: str) -> str | None:
        return argv[argv.index(flag) + 1] if flag in argv else None
    con = sqlite3.connect(db, timeout=60)
    rows = con.execute("select id, full_name, title from instructors").fetchall()
    todo = [(iid, full, initials(full)) for iid, full, _ in rows if full and initials(full) != full]
    # names that never became an instructor row: free-text instructor columns (the exam list's "Öğretim Üyesi")
    extra: set[str] = set()
    for t, c in text_columns(con):
        if "instructor" in c.lower() and t != "instructors":
            for (val,) in con.execute(f'select distinct "{c}" from "{t}" where "{c}" is not null'):
                extra.update(n for n in names_in_text(val) if len(n.split()) >= 2)
    vocabulary: set[str] = set()
    for t, c in (("courses", "name"), ("programs", "name"), ("faculties", "name"), ("rooms", "display_name"), ("exam_requests", "course_name")):
        try:
            for (val,) in con.execute(f'select distinct "{c}" from "{t}" where "{c}" is not null'):
                vocabulary.update(re.findall(r"[^\W\d_]+", lower_tr(val)))
        except sqlite3.OperationalError:
            pass
    known = [full for _, full, _ in todo] + sorted(extra)
    names_file = opt("--names")
    if names_file:
        try:
            with open(names_file, encoding="utf-8") as fh:
                known += json.load(fh)
        except FileNotFoundError:
            print(f"warning: {names_file} not found; only the names in this database are masked")
    save = opt("--save-names")
    if save:
        with open(save, "w", encoding="utf-8") as fh:
            json.dump(sorted(set(known)), fh, ensure_ascii=False)
    masker = Masker(known, vocabulary)
    print(f"  + {len(extra)} names from free-text instructor columns")
    print(f"{len(rows)} instructors, {len(todo)} with a full name")
    changed = 0
    for t, c in text_columns(con):
        if t == "instructors":
            continue
        updates = []
        for rowid, val in con.execute(f'select rowid, "{c}" from "{t}" where "{c}" is not null'):
            if isinstance(val, str):
                new = masker.cell(val)
                if new != val:
                    updates.append((new, rowid))
        if updates:
            print(f"  {t}.{c}: {len(updates)} cells")
            changed += len(updates)
            if not check:
                con.executemany(f'update "{t}" set "{c}" = ? where rowid = ?', updates)
    if not check:
        for iid, _full, m in todo:
            con.execute("update instructors set full_name = ?, canonical_name = ? where id = ?", (m, f"{lower_tr(m)} #{iid}", iid))
        cols = {r[1] for r in con.execute("pragma table_info('instructors')")}
        for col in ("email", "phone"):
            if col in cols:
                con.execute(f"update instructors set {col} = NULL where {col} is not null")
        con.commit()
    print(f"{'would mask' if check else 'masked'} {len(todo)} instructors and {changed} other cells ({masker.hits['names']} names)")

    # what is left: whole words equal to an original surname (mostly ordinary words such as course names)
    if masker.surnames and not check:
        srx = bounded(masker.surnames)
        left: Counter[tuple[str, str]] = Counter()
        sample: dict[tuple[str, str], set[str]] = {}
        for t, c in text_columns(con):
            for (val,) in con.execute(f'select "{c}" from "{t}" where "{c}" is not null'):
                if isinstance(val, str):
                    for m in srx.finditer(lower_tr(readable(val))):
                        left[(t, c)] += 1
                        sample.setdefault((t, c), set()).add(m.group(0))
        for (t, c), n in left.most_common():
            print(f"  surname-like word left in {t}.{c}: {n} ({', '.join(sorted(sample[(t, c)])[:10])})")
    emails = sum(1 for (v,) in con.execute("select email from users where email is not null") if EMAIL.fullmatch(v or "") and not v.endswith("@smartsched.local"))
    print(f"user e-mails outside @smartsched.local: {emails}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
