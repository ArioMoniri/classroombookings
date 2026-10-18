"""The helper's feature index and its search core (HB-01): "where is X" with no AI.

``features.yaml`` (next to this file) lists every page, tab, setting and control a person can be sent to, with TR/EN
titles, crumb paths, synonyms (the CRBS words first) and ≤ 3 steps. :func:`load` validates it strictly (an unknown
field, a duplicate id, an unknown permission or an over-long step list is refused at start-up and in the tests).

Search is BM25 over the Turkish-folded text (``guardrails.fold``: İ/ı, diacritics, homoglyphs, zero-width) with a
light Turkish suffix strip, field weights (title 3, synonyms 2, path 1, steps 1), a phrase bonus for whole synonyms
and a typo tolerance (one edit for words of ≥ 5 letters, a transposition counts as one). **The permission filter runs
before ranking**: an entry the person cannot open is never scored, so it can never leak. ~60 entries in memory, well
under a millisecond per query, no dependency beyond PyYAML.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ai.guardrails import fold
from app.services.bookings_perms import PERMISSION_NAMES

FEATURES_PATH = Path(__file__).with_name("features.yaml")

_ID = r"^[a-z][a-z_]*(\.[a-z][a-z_]*)*$"
_ROUTE = r"^/[a-z0-9\-/]*([#?][a-z0-9\-=&]*)?$"
_ANCHOR = r"^[a-z][a-z0-9\-]*$"
_NO_MARKUP = re.compile(r"[<>]|://|\bwww\.", re.IGNORECASE)


class IndexInvalid(ValueError):
    """``features.yaml`` does not validate (the message names the entry and the field)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _plain(v: str) -> str:
    if not v.strip():
        raise ValueError("empty text")
    if _NO_MARKUP.search(v):
        raise ValueError(f"no URL or markup in index text: {v!r}")
    return v


class Text(_Strict):
    tr: str
    en: str

    @field_validator("tr", "en")
    @classmethod
    def _text(cls, v: str) -> str:
        return _plain(v)


class Texts(_Strict):
    tr: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)

    @field_validator("tr", "en")
    @classmethod
    def _texts(cls, v: list[str]) -> list[str]:
        return [_plain(str(x)) for x in v]


class FeatureEntry(_Strict):
    id: str = Field(pattern=_ID, max_length=64)
    kind: Literal["page", "tab", "setting", "control"]
    route: str = Field(pattern=_ROUTE, max_length=120)
    title: Text
    path: Texts
    synonyms: Texts
    steps: Texts = Field(default_factory=Texts)
    anchor: str | None = Field(default=None, pattern=_ANCHOR, max_length=64)
    #: any-of; empty = every signed-in person (the nav's "no permission")
    permission: list[str] = Field(default_factory=list)
    hide_with: str | None = None
    #: helper registry actions reachable from this entry ("Burada yap")
    actions: list[str] = Field(default_factory=list)
    since: str

    @field_validator("permission")
    @classmethod
    def _perms(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - PERMISSION_NAMES)
        if unknown:
            raise ValueError(f"unknown permission(s) {unknown}")
        return v

    @field_validator("hide_with")
    @classmethod
    def _hide(cls, v: str | None) -> str | None:
        if v is not None and v not in PERMISSION_NAMES:
            raise ValueError(f"unknown permission {v}")
        return v

    def model_post_init(self, _ctx: object) -> None:
        for name in ("path", "steps"):
            t: Texts = getattr(self, name)
            if len(t.tr) != len(t.en):
                raise ValueError(f"{self.id}: {name} has {len(t.tr)} Turkish and {len(t.en)} English items")
        if len(self.steps.tr) > 3:
            raise ValueError(f"{self.id}: at most 3 steps (simplicity rule)")
        if not self.path.tr:
            raise ValueError(f"{self.id}: a path is required")


def visible(entry: FeatureEntry, perms: Iterable[str]) -> bool:
    """The nav's own rule: any-of ``permission`` (none = everyone), hidden for holders of ``hide_with``."""
    held = set(perms)
    if entry.hide_with and entry.hide_with in held:
        return False
    return not entry.permission or any(p in held for p in entry.permission)


# ------------------------------------------------------------------------------------------------- text

#: folded words that carry no meaning for "where is it" (question words, pronouns, light verbs)
STOPWORDS = frozenset(
    """nasil nerede nereden neresi nereye nerden ne neden hangi hangisi kim kac bir ve ile veya mi mu icin ben bana beni
    benim sen siz bu su o da de ki ya yok istiyorum isterim istedim lazim olur gibi gore kadar ederim eder et etmek
    edilir edebilirim yaparim yapilir yapabilirim yapmak yapiyorum bulurum bulabilirim acarim gorurum var mi miyim
    teki deki daki the a an to where is are can how do does i me of for in on at what which want need it this that
    please from with be am should""".split()
)
#: folded Turkish suffixes, longest first; at most three are stripped and the stem keeps ≥ 3 letters
_SUFFIXES = sorted(
    """lerimizi larimizi lerimiz larimiz lerinizi lariniz leriniz lerini larini lerime larima lerim larim lerin larin
    leri lari ler lar imizi imiz umuz iniz unuz sini sunu nin nun dan den tan ten yla yle iyor uyor irim urim arim erim
    mak mek yi yu ya ye ni nu na ne si su da de ta te im um in un i u a e""".split(),
    key=len,
    reverse=True,
)
_WORD = re.compile(r"[a-z0-9]+")


def fold_phrase(text: str) -> str:
    """Lower-case, Turkish-folded, punctuation-free form of a phrase (comparisons in tests and the guard)."""
    return " ".join(_WORD.findall(fold(text)))


def stem(word: str) -> str:
    w = word
    for _ in range(3):
        for s in _SUFFIXES:
            if w.endswith(s) and len(w) - len(s) >= 3:
                w = w[: -len(s)]
                break
        else:
            break
    return w


def terms(text: str) -> list[str]:
    """Index terms of a text: per word its stem, then the folded surface form when it differs (an exact surface
    match, e.g. "rezervasyonlarım", scores above the bare stem)."""
    out: list[str] = []
    for w in _WORD.findall(fold(text)):
        if w in STOPWORDS:
            continue
        s = stem(w)
        out.append(s)
        if s != w:
            out.append(w)
    return out


def _stems(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(fold(text)) if w not in STOPWORDS]


def _near(a: str, b: str) -> bool:
    """Optimal string alignment distance ≤ 1 (insert, delete, substitute, swap two neighbours)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :]


# ------------------------------------------------------------------------------------------------ search

FIELD_WEIGHTS = {"title": 3.0, "synonyms": 2.0, "path": 1.0, "steps": 1.0}
K1, B = 1.2, 0.5
FUZZY_FACTOR = 0.7
PHRASE_BONUS = 1.5


@dataclass(frozen=True)
class Hit:
    entry: FeatureEntry
    score: float
    #: share of the query's meaningful words found in the entry (0..1); the helper guard reads it
    coverage: float


@dataclass
class _Doc:
    entry: FeatureEntry
    tf: dict[str, float]
    length: float
    #: stem sets of the title and of every synonym (the phrase bonus)
    phrases: list[frozenset[str]]


class Index:
    def __init__(self, entries: list[FeatureEntry]) -> None:
        self.entries = entries
        self._docs: list[_Doc] = []
        df: Counter[str] = Counter()
        for e in entries:
            tf: dict[str, float] = defaultdict(float)
            fields = {
                "title": [e.title.tr, e.title.en],
                "synonyms": [*e.synonyms.tr, *e.synonyms.en],
                "path": [*e.path.tr, *e.path.en],
                "steps": [*e.steps.tr, *e.steps.en],
            }
            for name, texts in fields.items():
                for t in texts:
                    for term in terms(t):
                        tf[term] += FIELD_WEIGHTS[name]
            phrases = [frozenset(_stems(t)) for t in (e.title.tr, e.title.en, *e.synonyms.tr, *e.synonyms.en)]
            self._docs.append(_Doc(e, tf, sum(tf.values()), [p for p in phrases if p]))
            df.update(set(tf))
        self._n = len(entries)
        self._avg = sum(d.length for d in self._docs) / max(self._n, 1)
        self._idf = {t: math.log(1 + (self._n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self._vocab = sorted(self._idf)
        self.by_id = {e.id: e for e in entries}

    def vocabulary(self) -> frozenset[str]:
        return frozenset(self._vocab)

    def knows(self, word: str) -> bool:
        """Whether a (folded) word is in the index vocabulary, by its stem, its surface form or one typo away."""
        s = stem(word)
        return s in self._idf or word in self._idf or (len(s) >= 5 and bool(self._expand(s)))

    def _expand(self, term: str) -> list[tuple[str, float]]:
        """The index terms a query term stands for: itself, else close spellings and prefixes (typos, cut words)."""
        if term in self._idf:
            return [(term, 1.0)]
        out: list[tuple[str, float]] = []
        for v in self._vocab:
            if len(term) >= 5 and len(v) >= 4 and _near(term, v):
                out.append((v, FUZZY_FACTOR))
            elif len(term) >= 4 and len(v) >= 4 and (v.startswith(term) or term.startswith(v)):
                out.append((v, FUZZY_FACTOR * 0.8))
        return out

    def search(self, q: str, perms: Iterable[str], limit: int = 5) -> list[Hit]:
        held = frozenset(perms)
        words = [w for w in _WORD.findall(fold(q or "")) if w not in STOPWORDS][:24]
        if not words:
            return []
        q_terms: list[tuple[str, list[tuple[str, float]]]] = []
        for w in words:
            s = stem(w)
            found = dict(self._expand(s))
            if s != w:
                for t, f in self._expand(w):
                    found[t] = max(found.get(t, 0.0), f)
            q_terms.append((s, list(found.items())))
        q_stems = frozenset(s for s, _ in q_terms)
        hits: list[Hit] = []
        for d in self._docs:
            if not visible(d.entry, held):
                continue  # filtered before ranking: never scored, never shown
            score, matched = 0.0, 0
            for _s, cands in q_terms:
                best = 0.0
                for t, factor in cands:
                    f = d.tf.get(t, 0.0)
                    if not f:
                        continue
                    norm = f * (K1 + 1) / (f + K1 * (1 - B + B * d.length / self._avg))
                    best = max(best, factor * self._idf[t] * norm)
                if best:
                    matched += 1
                    score += best
            if not matched:
                continue
            bonus = max((len(p) for p in d.phrases if len(p) >= 2 and p <= q_stems), default=0)
            if not bonus and any(p == q_stems for p in d.phrases):
                bonus = 1
            score += PHRASE_BONUS * bonus
            hits.append(Hit(d.entry, round(score, 4), matched / len(q_terms)))
        hits.sort(key=lambda h: -h.score)
        return hits[: max(1, limit)]


def load(path: Path = FEATURES_PATH) -> Index:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IndexInvalid(f"{path.name}: {exc}") from exc
    if not isinstance(raw, list):
        raise IndexInvalid(f"{path.name}: a list of entries is expected")
    entries: list[FeatureEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        try:
            e = FeatureEntry.model_validate(item)
        except (ValidationError, ValueError) as exc:
            name = item.get("id") if isinstance(item, dict) else i
            raise IndexInvalid(f"{path.name} entry {name}: {exc}") from exc
        if e.id in seen:
            raise IndexInvalid(f"{path.name}: duplicate id {e.id}")
        seen.add(e.id)
        entries.append(e)
    return Index(entries)


@lru_cache(maxsize=1)
def get_index() -> Index:
    return load()


__all__ = [
    "FEATURES_PATH",
    "FeatureEntry",
    "Hit",
    "Index",
    "IndexInvalid",
    "fold_phrase",
    "get_index",
    "load",
    "stem",
    "terms",
    "visible",
]
