"""KVKK upload guard for recording and test stacks (FIX-J, round-4 E2EA-F01 / E2EA2-F02).

The seed workbooks under ``tests/fixtures`` name every instructor. A recording stack (scripts/record/stack.sh)
imports them once, masks the database to title + initials, and keeps masked copies of the workbooks in
``$REC_WORKDIR/fixtures``. Re-uploading a raw workbook through /import or the council would bring the full
names back (and store them in the preview job and the upload folder), so with ``KVKK_UPLOAD_GUARD=1`` such an
upload is refused before anything is stored or parsed:

* byte-for-byte one of the seed workbooks -> ``kvkk_seed_workbook``;
* any text of the file (cells, comments, document properties; CSV / text as decoded) holding two consecutive
  words of a known person's name (``KVKK_NAMES_FILE``, the JSON list stack.sh saves) -> ``kvkk_unmasked_names``.

Only honoured when ``ENVIRONMENT`` is dev or test; production never reads it. The messages never repeat a name.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path

from app.core.config import RELAXED_ENVIRONMENTS, get_settings

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
#: title tokens (lower case, without the dot) that are not part of a person's name
_TITLES = {
    "prof", "doç", "dr", "öğr", "üyesi", "üye", "gör", "arş", "uzm", "eğt", "eğitmen", "okt", "ecz", "öğretim",
    "görevlisi", "asst", "assoc", "yrd", "tek", "hoca", "öğretmen",
}  # fmt: skip
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_TAG = re.compile(r"<[^>]+>")
_TEXT_PARTS = re.compile(r"^(xl/(sharedStrings|comments[^/]*|worksheets/[^/]+)|docProps/(core|app))\.xml$", re.I)


def lower_tr(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def _words(text: str) -> list[str]:
    return [w for w in (lower_tr(m) for m in _WORD.findall(text)) if len(w) >= 2 and w not in _TITLES]


def active() -> bool:
    st = get_settings()
    return bool(st.kvkk_upload_guard) and st.environment in RELAXED_ENVIRONMENTS


@lru_cache(maxsize=1)
def _seed_hashes() -> frozenset[str]:
    if not FIXTURES.is_dir():
        return frozenset()
    return frozenset(hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURES.glob("*.xls*"))


@lru_cache(maxsize=4)
def _pairs(names_file: str | None) -> frozenset[tuple[str, str]]:
    if not names_file:
        return frozenset()
    try:
        names = json.loads(Path(names_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    out: set[tuple[str, str]] = set()
    for full in names if isinstance(names, list) else []:
        ws = _words(str(full))
        out.update(zip(ws, ws[1:], strict=False))
    return frozenset(out)


def reset_cache() -> None:
    _seed_hashes.cache_clear()
    _pairs.cache_clear()


def is_seed_workbook(data: bytes) -> bool:
    return hashlib.sha256(data).hexdigest() in _seed_hashes()


def _texts(data: bytes, filename: str | None) -> list[str]:
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return [
                    html.unescape(_TAG.sub(" ", z.read(n).decode("utf-8", "replace")))
                    for n in z.namelist()
                    if _TEXT_PARTS.match(n)
                ]
        except (zipfile.BadZipFile, OSError):
            return []
    for enc in ("utf-8", "cp1254"):
        try:
            return data.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return []


def unmasked_hits(data: bytes, filename: str | None) -> int:
    """How many text pieces of the upload hold a known person's name (two consecutive name words)."""
    pairs = _pairs(get_settings().kvkk_names_file)
    if not pairs:
        return 0
    hits = 0
    for text in _texts(data, filename):
        # one shared-strings part holds every cell: count per line / string item, never print the text
        for piece in re.split(r"\s{2,}|\n", text):
            ws = _words(piece)
            if any(p in pairs for p in zip(ws, ws[1:], strict=False)):
                hits += 1
    return hits


class KvkkRefused(Exception):
    def __init__(self, code: str, tr: str, en: str) -> None:
        super().__init__(en)
        self.code, self.message_tr, self.message_en = code, tr, en


def check(data: bytes, filename: str | None) -> None:
    """Raise :class:`KvkkRefused` for a raw seed workbook or a file with unmasked names (guard on only)."""
    if not active():
        return
    if is_seed_workbook(data):
        raise KvkkRefused(
            "kvkk_seed_workbook",
            "KVKK: bu dosya maskelenmemiş örnek çalışma kitaplarından biri. Bu test yığınında yalnızca maskelenmiş "
            "kopyayı yükleyin ($REC_WORKDIR/fixtures).",
            "KVKK: this is one of the unmasked seed workbooks. On this test stack upload only the masked copy "
            "($REC_WORKDIR/fixtures).",
        )
    n = unmasked_hits(data, filename)
    if n:
        raise KvkkRefused(
            "kvkk_unmasked_names",
            f"KVKK: dosyada maskelenmemiş {n} kişi adı var. Bu test yığınında adlar yalnızca baş harfleriyle "
            "yüklenebilir; maskelenmiş kopyayı kullanın ($REC_WORKDIR/fixtures).",
            f"KVKK: the file holds {n} unmasked person names. On this test stack names may only be uploaded as "
            "initials; use the masked copy ($REC_WORKDIR/fixtures).",
        )
