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

Running stack (FIX-J, round-4 E2EA-F01): `audit_events` is append-only (alembic 0031_kvkk). Its rows are masked
through the sanctioned path of app/services/kvkk.py: an `anonymise` window in `audit_purge_windows` per entity,
opened and deleted in the same transaction as the update, so `stack.sh mask` repairs a live database too.
Each masked instructor also gets a `catalog_aliases` row (entity instructor, alias = the masked canonical name) when
its initials are unique, so a re-import of the masked workbooks matches the existing rows instead of adding new ones.
People whose initials collide (FIX-K, E2EA-F08: 72 of the Bahar instructors) get a person key instead: the fewest
leading letters, word by word, that tell them apart ("Ad. K." / "Ay. K."), derived from the names alone, so the
database pass and the workbook copies (same saved name list) agree and each of them gets its alias too. A database
masked before FIX-K keeps its duplicate initials; a fresh `stack.sh up` applies the keys.

    python3 scripts/record/kvkk_mask.py --workbooks SRC_DIR DST_DIR --names FILE   masked copies of the workbooks
    python3 scripts/record/kvkk_mask.py --files DIR --names FILE                     mask stored uploads in place

--workbooks writes a masked copy of every .xlsx / .csv in SRC_DIR (cells, comments, document authors) to DST_DIR;
stack.sh keeps them in $REC_WORKDIR/fixtures, the only workbooks a test stack accepts (app/core/kvkk_guard.py).
--files masks the import and council uploads the stack stored (preview files included).

--verify also scans, with --names FILE, every text and JSON column (import preview rows in `import_jobs.summary`,
audit snapshots, council artifacts) for two consecutive words of a known name, and with --uploads DIR every stored
.xlsx / .csv upload; it reports `table.column: N cells` / `upload: N files`, never a value.

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
# FIX-K (E2EA-F08): a person key of colliding initials extends a word to its first few letters ("Ad. K.")
INITIAL = re.compile(r"[^\W\d_][^\W\d_]{0,4}\.(?:-[^\W\d_]\.)*")
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


def person_norm(full: str) -> str:
    """The person a name means, whatever its casing: 'AYAZ Kamer' and 'Ayaz KAMER' are one person."""
    return lower_tr(" ".join(name_words(full)))


def _prefix(w: str, n: int) -> str:
    """The masked form of one word: its initial ('K.'), or its first ``n`` letters ('Ka.') for a person key."""
    if n <= 1:
        return initial(w)
    letters = [ch for ch in w if ch.isalpha()]
    return upper_tr(letters[0]) + lower_tr("".join(letters[1:n])) + "."


def person_keys(full_names: list[str]) -> dict[str, str]:
    """FIX-K (E2EA-F08): person -> masked name. Unique initials stay initials ("D. Ö."); people whose initials
    collide get the fewest leading letters, word by word, that tell them apart ("Ad. K." / "Ay. K."; "A. Ku." /
    "A. Ka."). Derived from the names alone, so the database pass and the workbook copies (same saved name list)
    agree, and each masked person keeps one alias a re-import matches. Two spellings of one person are one key."""
    people: dict[str, list[str]] = {}
    for full in full_names:
        ws = name_words(full)
        if ws:
            people.setdefault(person_norm(full), ws)
    groups: dict[str, list[str]] = {}
    for key, ws in people.items():
        groups.setdefault(lower_tr(initials(" ".join(ws))), []).append(key)
    out: dict[str, str] = {}
    for members in groups.values():
        words = [people[m] for m in members]
        lengths = [1] * max(len(w) for w in words)

        def masked(ws: list[str], lens: list[int] = lengths) -> str:
            return " ".join(_prefix(w, lens[i]) for i, w in enumerate(ws))

        def count(group: list[list[str]] = words) -> int:
            return len({lower_tr(masked(w)) for w in group})

        for pos in range(len(lengths)):
            before = count()
            longest = max(sum(ch.isalpha() for ch in w[pos]) for w in words if pos < len(w))
            while count() < len(words) and lengths[pos] < longest:
                lengths[pos] += 1
            if count() == before:  # this word does not tell them apart ("Aday" twice): keep its initial
                lengths[pos] = 1
            if count() == len(words):
                break
        for m, w in zip(members, words, strict=True):
            out[m] = masked(w)
    return out


def mask_person(full: str, keys: dict[str, str]) -> str:
    """A name (leading title tokens kept) as its person key, or its initials when the person is not known."""
    key = keys.get(person_norm(full))
    if key is None:
        return initials(full)
    lead = []
    for w in full.split():
        if not is_title(w):
            break
        lead.append(w)
    return " ".join([*lead, key])


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
        self.keys = person_keys(full_names)

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
            out.append(mask_person(s[m.start() : m.end()], self.keys))
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
            # keys too: some summaries key their counts by the cell text (an instructor's spelling)
            return {self.text(k) if isinstance(k, str) else k: self.value(x) for k, x in v.items()}
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


def _read_text(path: str) -> tuple[str, str]:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp1254"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def _upload_files(folder: str) -> list[str]:
    import os

    out = []
    for base, _dirs, files in os.walk(folder):
        out += [os.path.join(base, f) for f in files if f.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt"))]
    return sorted(out)


def _file_texts(path: str) -> list[str]:
    """The texts of an upload: for a workbook the XML of its strings, sheets, comments and document properties
    (read straight from the zip, fast on large grids), one item per string."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        import html
        import zipfile

        parts = re.compile(r"^(xl/(sharedStrings|comments[^/]*|worksheets/[^/]+)|docProps/(core|app))\.xml$", re.I)
        try:
            with zipfile.ZipFile(path) as z:
                xml = [z.read(n).decode("utf-8", "replace") for n in z.namelist() if parts.match(n)]
        except (OSError, zipfile.BadZipFile):
            return []
        # one item per shared string / cell / comment / property; rich-text runs inside one item stay together
        items = (re.sub(r"<[^>]+>", "", x) for doc in xml for x in re.split(r"</(?:\w+:)?(?:si|c|comment|is)>|(?<=>)(?=<dc:|<cp:)", doc))
        return [html.unescape(x) for x in items if x.strip()]
    return _read_text(path)[0].splitlines()


def _load_names(path: str | None) -> list[str]:
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return list(json.load(fh))
    except FileNotFoundError:
        print(f"warning: {path} not found")
        return []


def full_name_runs(names: list[str]) -> re.Pattern[str] | None:
    """Two or more consecutive whole name words (initials a workbook already wrote, "B." in "Ayşe B. Kaya", break
    a run), so masked output ("A. B. K.") never matches its own pattern."""
    runs: set[str] = set()
    for full in names:
        for part in re.split(r"\S*\b[^\W\d_]\.\S*", " ".join(name_words(full))):
            ws = [w for w in part.split() if sum(ch.isalpha() for ch in w) >= 2]
            for i in range(len(ws)):
                for j in range(i + 2, len(ws) + 1):
                    runs.add(lower_tr(" ".join(ws[i:j])))
    return bounded(runs) if runs else None


def verify(db: str, names_file: str | None = None, uploads: str | None = None) -> int:
    con = sqlite3.connect(db, timeout=60)
    left: list[str] = []
    for table in ("instructors", "users"):
        for (val,) in con.execute(f'select full_name from "{table}" where full_name is not null'):
            if val.strip() and val not in PLACEHOLDER_NAMES and not is_masked(val):
                left.append(table + ": " + " ".join(w if is_title(w) or INITIAL.fullmatch(w) else w[:1] + "*" for w in val.split()))
    runs = full_name_runs(_load_names(names_file))
    if runs is not None:
        # every text / JSON column: import preview rows (import_jobs.summary), audit snapshots, council artifacts
        for t, c in text_columns(con):
            n = 0
            for (val,) in con.execute(f'select "{c}" from "{t}" where "{c}" is not null'):
                if isinstance(val, str) and runs.search(lower_tr(readable(val))):
                    n += 1
            if n:
                left.append(f"{t}.{c}: {n} cells")
        if uploads:
            bad = [p for p in _upload_files(uploads) if any(runs.search(lower_tr(x)) for x in _file_texts(p))]
            if bad:
                left.append(f"upload: {len(bad)} files")
    elif names_file or uploads:
        print("warning: no names to look for; text columns and uploads were not scanned")
    con.close()
    print(f"left {len(left)}" + (f" ({'; '.join(left[:10])})" if left else ""))
    return 1 if left else 0


def mask_file(src: str, dst: str, masker: Masker) -> bool:
    """A masked copy of one workbook / CSV (dst may equal src). True when something changed."""
    if src.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        from openpyxl.comments import Comment

        wb = load_workbook(src, keep_vba=src.lower().endswith(".xlsm"))
        changed = False
        for attr in ("creator", "lastModifiedBy"):
            if getattr(wb.properties, attr):
                setattr(wb.properties, attr, "SmartSched")
                changed = True
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str):
                        new = masker.text(c.value)
                        if new != c.value:
                            c.value, changed = new, True
                    if c.comment is not None:
                        text, author = masker.text(c.comment.text or ""), masker.text(c.comment.author or "")
                        if (text, author) != (c.comment.text or "", c.comment.author or ""):
                            c.comment, changed = Comment(text, author), True
        if changed or dst != src:
            wb.save(dst)
        return changed
    text, enc = _read_text(src)
    new = "\n".join(masker.text(line) for line in text.split("\n"))
    if new != text or dst != src:
        with open(dst, "w", encoding="utf-8" if enc == "utf-8-sig" else enc, newline="") as fh:
            fh.write(new)
    return new != text


def mask_files(argv: list[str]) -> int:
    import os
    import shutil

    names_file = argv[argv.index("--names") + 1] if "--names" in argv else None
    masker = Masker(_load_names(names_file))
    if masker.runs is None:
        print("error: --names FILE with the saved name list is required")
        return 1
    if "--workbooks" in argv:
        i = argv.index("--workbooks")
        src, dst = argv[i + 1], argv[i + 2]
        os.makedirs(dst, exist_ok=True)
        n = 0
        for f in sorted(os.listdir(src)):
            p = os.path.join(src, f)
            if not os.path.isfile(p):
                continue
            if f.lower().endswith((".xlsx", ".xlsm", ".csv", ".txt")):
                mask_file(p, os.path.join(dst, f), masker)
            else:
                shutil.copyfile(p, os.path.join(dst, f))
            n += 1
        print(f"masked copies: {n} files in {dst}")
        return 0
    folder = argv[argv.index("--files") + 1]
    n = sum(1 for p in _upload_files(folder) if mask_file(p, p, masker))
    print(f"masked uploads: {n} files")
    return 0


def _audit_updates(con: sqlite3.Connection, col: str, updates: list[tuple[str, int]]) -> None:
    """Masked audit cells through the anonymise windows of the append-only trigger (app/services/kvkk.py)."""
    windows = []
    for _new, rowid in updates:
        et, eid, actor = con.execute("select entity_type, entity_id, actor_id from audit_events where rowid = ?", (rowid,)).fetchone()
        if eid is not None:
            windows.append(("anonymise", None, et, eid))
        elif actor is not None:
            windows.append(("anonymise", actor, None, None))
    now = "2000-01-01 00:00:00"
    ids = []
    for w in set(windows):
        cur = con.execute(
            "insert into audit_purge_windows (kind, subject_actor_id, entity_type, entity_id, created_at) values (?, ?, ?, ?, ?)",
            (*w, now),
        )
        ids.append(cur.lastrowid)
    try:
        for new, rowid in updates:
            try:
                con.execute(f'update audit_events set "{col}" = ? where rowid = ?', (new, rowid))
            except sqlite3.IntegrityError:
                print(f"  audit_events.{col}: row {rowid} has no entity or actor; left as it is")
    finally:
        con.executemany("delete from audit_purge_windows where id = ?", [(i,) for i in ids])


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    if "--workbooks" in argv or "--files" in argv:
        return mask_files(argv)
    if "--verify" in argv:
        names = argv[argv.index("--names") + 1] if "--names" in argv else None
        uploads = argv[argv.index("--uploads") + 1] if "--uploads" in argv else None
        return verify(argv[0], names, uploads)
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
    todo = [(iid, full, mask_person(full, masker.keys)) for iid, full, _ in todo]
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
                if t == "audit_events":
                    _audit_updates(con, c, updates)
                else:
                    con.executemany(f'update "{t}" set "{c}" = ? where rowid = ?', updates)
    if not check:
        for iid, _full, m in todo:
            con.execute("update instructors set full_name = ?, canonical_name = ? where id = ?", (m, f"{lower_tr(m)} #{iid}", iid))
        # the masked workbooks name these rows by their initials: an alias per unique masked name, so a re-import
        # of $REC_WORKDIR/fixtures matches them (catalog.instructor -> CatalogAlias) instead of creating new rows
        if con.execute("select 1 from sqlite_master where type='table' and name='catalog_aliases'").fetchone():
            masked = Counter()
            keyed: dict[str, int] = {}
            for iid, full in con.execute("select id, full_name from instructors"):
                key = lower_tr(" ".join(w for w in (full or "").split() if not is_title(w)))
                if key:
                    masked[key] += 1
                    keyed[key] = iid
            con.executemany(
                "insert or ignore into catalog_aliases (entity, alias, target_id, created_at) values ('instructor', ?, ?, ?)",
                [(k, keyed[k], "2000-01-01 00:00:00") for k, n in masked.items() if n == 1 and is_masked(k)],
            )
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
