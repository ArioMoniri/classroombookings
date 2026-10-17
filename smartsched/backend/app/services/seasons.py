"""Season calendar, season profiles and the effective solver weights of a run (adaptive scheduling AS-01..AS-03,
AS-18; docs/research/2026-10-17-adaptive-scheduling.md §3.1).

* :func:`season_of` names a term's season (``BAHAR`` / ``GUZ`` / ``YAZ`` / ``BUT`` / ``FINAL``, else its kind).
  It moved here from ``app.services.learning`` (re-exported there), so there is one definition.
* :func:`periods` turns a term's ``weeks`` (kinds), ``holidays`` and the admin's ``season_segments`` into dated
  **period segments** (``LECTURE`` / ``ADD_DROP`` / ``MIDTERM`` / ``EXAM`` / ``MAKEUP`` / ``HOLIDAY`` / ``SUMMER`` /
  ``BREAK``). :func:`closed_days` gives the (week, weekday) pairs no class meets on (HOLIDAY weeks and holiday
  dates); utilisation leaves them out of the numerator and the denominator.
* :func:`course_weeks` is the week filter of COURSE runs: classes are not planned in HOLIDAY, EXAM or MAKEUP weeks,
  nor in SUMMER weeks of a term that is not a summer term (a 19-week Bahar keeps its 15 lecture weeks).
* :func:`effective_weights` merges, later layers winning: ``DEFAULT_WEIGHTS`` < the admin's ``solver_weights``
  setting < the active season profile for (season, dominant period kind of the run's horizon) < ``run.params``
  ``weights``. The bridge stores the merged table and the source of every key on the run
  (``stats.weights_effective`` / ``stats.weights_source`` / ``stats.profile``), so every run says which profile
  and weights shaped it. ``params.season_profile`` (``"none"`` or a profile key) overrides the profile choice.

Profiles are suggestions an admin approves: drafts never apply; one version per key is active; editing an active
profile makes a new draft version; "Geri al" re-activates the parent. The built-in ``standard`` and ``exam_week``
profiles are code constants with no overrides, so an install without profiles behaves exactly as before.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import Holiday, ScheduleRun, Term, Week
from app.models.seasons import PERIOD_KINDS, SeasonProfile, SeasonSegment
from app.solver.weights import DEFAULT_WEIGHTS

log = logging.getLogger("smartsched.seasons")

#: week kinds no class is planned in (COURSE runs); SUMMER too unless the term is a summer term
COURSE_SKIP_KINDS = frozenset({"HOLIDAY", "EXAM", "MAKEUP"})
#: bounds of one weight (the run-param bound of ``app.services.run_params``)
MAX_WEIGHT = 10_000
MAX_WEIGHT_KEYS = 50
#: run param that overrides the profile choice: ``"none"`` (no profile) or a profile key
PROFILE_PARAM = "season_profile"
DEFAULT_PEAK_THRESHOLD = 85

KIND_LABEL: dict[str, tuple[str, str]] = {
    "LECTURE": ("Ders dönemi", "Lecture period"),
    "ADD_DROP": ("Ekle-bırak", "Add/drop"),
    "MIDTERM": ("Ara sınav haftası", "Midterm week"),
    "EXAM": ("Sınav dönemi", "Exam period"),
    "MAKEUP": ("Bütünleme", "Make-up exams"),
    "HOLIDAY": ("Tatil", "Holiday"),
    "SUMMER": ("Yaz dönemi", "Summer term"),
    "BREAK": ("Ara", "Break"),
}
SEASON_LABEL: dict[str, tuple[str, str]] = {
    "BAHAR": ("Bahar", "Spring"),
    "GUZ": ("Güz", "Fall"),
    "YAZ": ("Yaz", "Summer"),
    "FINAL": ("Final", "Final exams"),
    "BUT": ("Bütünleme", "Make-up exams"),
}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# ------------------------------------------------------------------------------------------------ seasons


def season_of(term: Term) -> str:
    """``BAHAR`` / ``GUZ`` / ``YAZ`` / ``BUT`` / ``FINAL`` from the term code (Turkish or English words; İ/ı and
    accents folded), else the term kind upper-cased (``REGULAR``)."""
    folded = n.fold(term.code or "").upper()
    for key, words in (
        ("BAHAR", ("BAHAR", "SPRING")),
        ("GUZ", ("GUZ", "FALL", "AUTUMN")),
        ("YAZ", ("YAZ", "SUMMER")),
        ("BUT", ("BUT",)),
        ("FINAL", ("FINAL",)),
    ):
        if any(w in folded for w in words):
            return key
    return (term.kind or "REGULAR").upper()


def is_summer_term(term: Term) -> bool:
    return season_of(term) == "YAZ" or (term.kind or "").upper() == "SUMMER"


def week_kinds(weeks_rows: Iterable[Week]) -> dict[int, str]:
    """week index -> kind (upper-cased; a week without a kind is a lecture week)."""
    return {int(w.index): (w.kind or "LECTURE").upper() for w in weeks_rows}


def course_weeks(weeks: Sequence[int], kinds: Mapping[int, str], term: Term) -> tuple[list[int], list[int]]:
    """(kept, dropped) weeks of a COURSE run: HOLIDAY / EXAM / MAKEUP weeks are dropped, SUMMER weeks too unless
    ``term`` is a summer term. Weeks without a ``Week`` row are kept (terms imported without week kinds)."""
    summer = is_summer_term(term)
    kept: list[int] = []
    dropped: list[int] = []
    for w in weeks:
        k = kinds.get(int(w), "LECTURE")
        if k in COURSE_SKIP_KINDS or (k == "SUMMER" and not summer):
            dropped.append(int(w))
        else:
            kept.append(int(w))
    return kept, dropped


# ------------------------------------------------------------------------------------------------ calendar


@dataclass(frozen=True)
class PeriodSegment:
    """One stretch of a term's calendar with one kind."""

    kind: str
    week_from: int | None
    week_to: int | None
    date_from: date | None
    date_to: date | None
    label: dict[str, str]
    #: week (from ``weeks.kind``) | holiday (a ``holidays`` row) | segment (an admin's ``season_segments`` row)
    source: str
    status: str = "active"
    segment_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "kind_label": _t(*KIND_LABEL.get(self.kind, (self.kind, self.kind))),
            "week_from": self.week_from,
            "week_to": self.week_to,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "label": self.label,
            "source": self.source,
            "status": self.status,
            "segment_id": self.segment_id,
        }


def _monday(term: Term, weeks_rows: Sequence[Week]) -> date | None:
    from app.services.calendar import term_monday

    return term_monday(term, list(weeks_rows))


def week_start(term: Term, week: int, weeks_rows: Sequence[Week]) -> date | None:
    """Monday of ``week``: the week row's own start date (sheet names like "Final 1 - 7 Haziran" date it), else
    the term's first Monday + (week - 1) weeks."""
    for w in weeks_rows:
        if int(w.index) == int(week) and w.start_date is not None:
            return w.start_date - timedelta(days=w.start_date.weekday())
    monday = _monday(term, weeks_rows)
    return monday + timedelta(weeks=int(week) - 1) if monday is not None else None


def week_of_date(term: Term, d: date, weeks_rows: Sequence[Week]) -> int | None:
    """The week a date falls in: a dated week row first, else the term's weekly arithmetic."""
    for w in weeks_rows:
        if w.start_date is not None:
            mon = w.start_date - timedelta(days=w.start_date.weekday())
            if mon <= d < mon + timedelta(days=7):
                return int(w.index)
    monday = _monday(term, weeks_rows)
    if monday is None:
        return None
    idx = (d - monday).days // 7 + 1
    known = {int(w.index) for w in weeks_rows}
    if known and idx not in known:
        return None if any(w.start_date is not None for w in weeks_rows) else idx
    return idx


def _dates(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def periods(
    term: Term,
    weeks_rows: Sequence[Week],
    holidays: Sequence[Holiday] = (),
    segments: Sequence[SeasonSegment] = (),
) -> list[PeriodSegment]:
    """Dated period segments of ``term``: runs of consecutive weeks of one kind, every holiday, every admin
    segment (drafts included, marked ``status = draft``). Sorted by start week / date."""
    out: list[PeriodSegment] = []
    rows = sorted(weeks_rows, key=lambda w: int(w.index))
    run: list[Week] = []

    def flush() -> None:
        if not run:
            return
        kind = (run[0].kind or "LECTURE").upper()
        if kind not in PERIOD_KINDS:
            kind = "LECTURE"
        first, last = int(run[0].index), int(run[-1].index)
        start = week_start(term, first, rows)
        end_mon = week_start(term, last, rows)
        tr, en = KIND_LABEL[kind]
        span_tr = f"{first}. hafta" if first == last else f"{first}–{last}. haftalar"
        span_en = f"week {first}" if first == last else f"weeks {first}–{last}"
        out.append(
            PeriodSegment(
                kind=kind,
                week_from=first,
                week_to=last,
                date_from=start,
                date_to=end_mon + timedelta(days=6) if end_mon else None,
                label=_t(f"{tr} ({span_tr})", f"{en} ({span_en})"),
                source="week",
            )
        )
        run.clear()

    for w in rows:
        if run and ((w.kind or "LECTURE").upper() != (run[-1].kind or "LECTURE").upper() or int(w.index) != int(run[-1].index) + 1):
            flush()
        run.append(w)
    flush()
    for h in holidays:
        wf = week_of_date(term, h.date_start, rows)
        wt = week_of_date(term, h.date_end, rows)
        out.append(
            PeriodSegment(
                kind="HOLIDAY",
                week_from=wf,
                week_to=wt,
                date_from=h.date_start,
                date_to=h.date_end,
                label=_t(h.name, h.name),
                source="holiday",
            )
        )
    for sg in segments:
        kind = (sg.kind or "LECTURE").upper()
        df = sg.date_from or (week_start(term, sg.week_from, rows) if sg.week_from else None)
        wt_mon = week_start(term, sg.week_to or sg.week_from, rows) if (sg.week_to or sg.week_from) else None
        dt = sg.date_to or (wt_mon + timedelta(days=6) if wt_mon else None)
        out.append(
            PeriodSegment(
                kind=kind,
                week_from=sg.week_from,
                week_to=sg.week_to or sg.week_from,
                date_from=df,
                date_to=dt,
                label=_t(sg.label_tr, sg.label_en),
                source="segment",
                status=sg.status or "active",
                segment_id=sg.id,
            )
        )
    out.sort(key=lambda s: (s.week_from or 0, s.date_from or date.min, s.source != "week"))
    return out


async def load_calendar(session: AsyncSession, term: Term) -> tuple[list[Week], list[Holiday], list[SeasonSegment]]:
    weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    holidays = list((await session.execute(select(Holiday).where(Holiday.term_id == term.id))).scalars())
    segs = list(
        (
            await session.execute(
                select(SeasonSegment).where(SeasonSegment.term_id == term.id).order_by(SeasonSegment.id)
            )
        ).scalars()
    )
    return weeks_rows, holidays, segs


async def load_periods(session: AsyncSession, term: Term) -> list[PeriodSegment]:
    weeks_rows, holidays, segs = await load_calendar(session, term)
    return periods(term, weeks_rows, holidays, segs)


def closed_days(term: Term, weeks_rows: Sequence[Week], holidays: Sequence[Holiday] = ()) -> set[tuple[int, int]]:
    """(week, weekday) pairs no class meets on: every day of a HOLIDAY week and every holiday date that falls in
    a week of the term."""
    out: set[tuple[int, int]] = set()
    for w in weeks_rows:
        if (w.kind or "").upper() == "HOLIDAY":
            out.update((int(w.index), d) for d in range(1, 8))
    for h in holidays:
        for d in _dates(h.date_start, h.date_end):
            wk = week_of_date(term, d, weeks_rows)
            if wk is not None:
                out.add((wk, d.isoweekday()))
    return out


def segment_kind_by_week(segments: Sequence[SeasonSegment]) -> dict[int, str]:
    """week -> kind of an *active* admin segment covering it (add/drop, midterm ...)."""
    out: dict[int, str] = {}
    for sg in segments:
        if (sg.status or "active") != "active" or sg.week_from is None:
            continue
        for w in range(int(sg.week_from), int(sg.week_to or sg.week_from) + 1):
            out[w] = (sg.kind or "LECTURE").upper()
    return out


def dominant_period_kind(
    run_kind: str, weeks: Sequence[int], kinds: Mapping[int, str], segment_kinds: Mapping[int, str] | None = None
) -> str:
    """The period kind most of a run's horizon weeks have (ties: the order of ``PERIOD_KINDS``). An exam run is
    ``EXAM`` (``MAKEUP`` when most of its weeks are make-up weeks), whatever its weeks are called."""
    seg = segment_kinds or {}
    counts = Counter(seg.get(int(w)) or kinds.get(int(w), "LECTURE") for w in weeks)
    if (run_kind or "COURSE").upper() == "EXAM":
        return "MAKEUP" if counts and counts.most_common(1)[0][0] == "MAKEUP" else "EXAM"
    if not counts:
        return "LECTURE"
    best = max(counts.values())
    return next(k for k in (*PERIOD_KINDS, *sorted(counts)) if counts.get(k) == best)


def period_kind_on(
    term: Term, d: date, weeks_rows: Sequence[Week], holidays: Sequence[Holiday], segments: Sequence[SeasonSegment]
) -> str:
    """The period kind of one date (a holiday date is HOLIDAY; an admin segment wins over the week kind)."""
    for h in holidays:
        if h.date_start <= d <= h.date_end:
            return "HOLIDAY"
    wk = week_of_date(term, d, weeks_rows)
    for sg in segments:
        if (sg.status or "active") != "active":
            continue
        if sg.date_from and sg.date_to and sg.date_from <= d <= sg.date_to:
            return (sg.kind or "LECTURE").upper()
        if wk is not None and sg.week_from is not None and sg.week_from <= wk <= (sg.week_to or sg.week_from):
            return (sg.kind or "LECTURE").upper()
    if wk is None:
        return "LECTURE"
    return week_kinds(weeks_rows).get(wk, "LECTURE")


# ------------------------------------------------------------------------------------------------ profiles

#: built-in, read-only profiles (no overrides): an install without profiles behaves exactly as before
BUILTIN_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "key": "standard",
        "version": 1,
        "name_tr": "Standart",
        "name_en": "Standard",
        "applies_to": [{"season": "*", "period_kind": "*"}],
        "solver_weights": {},
        "booking_overlays": [],
        "peak_threshold_pct": DEFAULT_PEAK_THRESHOLD,
        "explanation": _t(
            "Her dönem ve her dönem türü için varsayılan ağırlıklar; ek kural yok.",
            "Default weights for every season and period; no extra rules.",
        ),
    },
    {
        "key": "exam_week",
        "version": 1,
        "name_tr": "Sınav haftası",
        "name_en": "Exam week",
        "applies_to": [{"season": "*", "period_kind": "EXAM"}, {"season": "*", "period_kind": "MAKEUP"}],
        "solver_weights": {},
        "booking_overlays": [],
        "peak_threshold_pct": DEFAULT_PEAK_THRESHOLD,
        "explanation": _t(
            "Sınav ve bütünleme haftaları: rezervasyonlar sınav dönemi ayarına uyar (Rezervasyon kuralları).",
            "Exam and make-up weeks: bookings follow the exam-period setting (Booking rules).",
        ),
    },
)
BUILTIN_KEYS = frozenset(p["key"] for p in BUILTIN_PROFILES)


@dataclass(frozen=True)
class ResolvedProfile:
    key: str
    version: int
    id: int | None
    builtin: bool
    name: dict[str, str]
    solver_weights: dict[str, int]
    booking_overlays: list[dict[str, Any]]
    peak_threshold_pct: int
    applies_to: list[dict[str, str]]

    @property
    def label(self) -> str:
        return f"profile:{self.key}@{self.version}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "id": self.id,
            "builtin": self.builtin,
            "name": self.name,
            "source": self.label,
            "peak_threshold_pct": self.peak_threshold_pct,
        }


def _builtin(p: Mapping[str, Any]) -> ResolvedProfile:
    return ResolvedProfile(
        key=p["key"],
        version=int(p["version"]),
        id=None,
        builtin=True,
        name=_t(p["name_tr"], p["name_en"]),
        solver_weights=dict(p["solver_weights"]),
        booking_overlays=list(p["booking_overlays"]),
        peak_threshold_pct=int(p["peak_threshold_pct"]),
        applies_to=list(p["applies_to"]),
    )


def _resolved(row: SeasonProfile) -> ResolvedProfile:
    weights, _warn = clean_weights(row.solver_weights or {})
    return ResolvedProfile(
        key=row.key,
        version=int(row.version),
        id=row.id,
        builtin=False,
        name=_t(row.name_tr, row.name_en),
        solver_weights=weights,
        booking_overlays=[dict(o) for o in row.booking_overlays or [] if isinstance(o, Mapping)],
        peak_threshold_pct=int(row.peak_threshold_pct or DEFAULT_PEAK_THRESHOLD),
        applies_to=[dict(a) for a in row.applies_to or [] if isinstance(a, Mapping)],
    )


def match_score(applies_to: Iterable[Mapping[str, Any]], season: str, period_kind: str) -> int | None:
    """Specificity of the best ``applies_to`` entry for (season, period kind): exact season 2, exact kind 1,
    wildcards 0; ``None`` = no entry matches."""
    best: int | None = None
    for a in applies_to:
        s = str(a.get("season") or "*").upper()
        k = str(a.get("period_kind") or "*").upper()
        if s not in ("*", season) or k not in ("*", period_kind):
            continue
        score = (2 if s != "*" else 0) + (1 if k != "*" else 0)
        best = score if best is None else max(best, score)
    return best


async def active_profiles(session: AsyncSession) -> list[SeasonProfile]:
    return list(
        (
            await session.execute(select(SeasonProfile).where(SeasonProfile.status == "active").order_by(SeasonProfile.id))
        ).scalars()
    )


async def resolve_profile(
    session: AsyncSession, season: str, period_kind: str, override: str | None = None
) -> ResolvedProfile | None:
    """The profile for (season, period kind): ``override`` (a key; ``"none"`` = no profile) else the most specific
    active profile (an admin's beats a built-in at equal specificity; the latest approved wins a tie)."""
    if override is not None and str(override).lower() == "none":
        return None
    rows = await active_profiles(session)
    if override:
        for r in rows:
            if r.key == override:
                return _resolved(r)
        for p in BUILTIN_PROFILES:
            if p["key"] == override:
                return _builtin(p)
        return None
    best: tuple[int, int, int] | None = None
    chosen: ResolvedProfile | None = None
    for p in BUILTIN_PROFILES:
        sc = match_score(p["applies_to"], season, period_kind)
        if sc is not None and (best is None or (sc, 0, 0) > best):
            best, chosen = (sc, 0, 0), _builtin(p)
    for r in rows:
        sc = match_score(r.applies_to or [], season, period_kind)
        if sc is None:
            continue
        rank = (sc, 1, r.id)
        if best is None or rank > best:
            best, chosen = rank, _resolved(r)
    return chosen


# ------------------------------------------------------------------------------------------------ weights


def clean_weights(raw: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """(valid weights, warnings) of a weight table from a setting, a profile or a run: keys are names of at most 64
    characters, values whole numbers 0..:data:`MAX_WEIGHT`; anything else is skipped with a TR/EN warning."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return {}, [{"key": "*", "text": _t("Ağırlık ayarı JSON değil", "The weights setting is not JSON")}]
    if not isinstance(raw, Mapping):
        return {}, [{"key": "*", "text": _t("Ağırlıklar bir nesne olmalı", "Weights must be an object")}]
    out: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    for k, v in list(raw.items())[: MAX_WEIGHT_KEYS * 2]:
        ok_key = isinstance(k, str) and 0 < len(k) <= 64
        ok_val = isinstance(v, int | float) and not isinstance(v, bool) and float(v).is_integer()
        if ok_key and ok_val and 0 <= int(v) <= MAX_WEIGHT:
            out[str(k)] = int(v)
        else:
            warnings.append(
                {
                    "key": str(k)[:64],
                    "text": _t(
                        f"{str(k)[:64]} ağırlığı 0–{MAX_WEIGHT} arasında bir tam sayı olmalı; yok sayıldı",
                        f"weight {str(k)[:64]} must be a whole number 0–{MAX_WEIGHT}; ignored",
                    ),
                }
            )
    return out, warnings


@dataclass(frozen=True)
class EffectiveWeights:
    """The merged weight table of a run and where every key came from."""

    #: every key of ``DEFAULT_WEIGHTS`` plus any extra key a layer set
    weights: dict[str, int]
    #: key -> default | settings | profile:<key>@<version> | run
    source: dict[str, str]
    #: the keys a layer above the defaults set (what the solver input carries)
    overrides: dict[str, int]
    profile: ResolvedProfile | None
    season: str
    period_kind: str
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def stats(self) -> dict[str, Any]:
        return {
            "weights_effective": dict(self.weights),
            "weights_source": dict(self.source),
            "profile": self.profile.as_dict() if self.profile else None,
            "season": {"key": self.season, "period_kind": self.period_kind},
            **({"weights_warnings": list(self.warnings)} if self.warnings else {}),
        }


def merge_layers(layers: Sequence[tuple[str, Mapping[str, int]]]) -> tuple[dict[str, int], dict[str, str], dict[str, int]]:
    weights = dict(DEFAULT_WEIGHTS)
    source = {k: "default" for k in DEFAULT_WEIGHTS}
    overrides: dict[str, int] = {}
    for name, layer in layers:
        for k, v in layer.items():
            weights[k] = int(v)
            source[k] = name
            overrides[k] = int(v)
    return weights, source, overrides


async def settings_weights(session: AsyncSession) -> tuple[dict[str, int], list[dict[str, Any]]]:
    from app.services import settings_service as ss

    return clean_weights(await ss.get_value(session, "solver_weights"))


async def effective_weights(
    session: AsyncSession,
    run: ScheduleRun,
    *,
    term: Term | None = None,
    weeks: Sequence[int] | None = None,
    weeks_rows: Sequence[Week] | None = None,
) -> EffectiveWeights:
    """Merged weights of ``run`` (see the module docstring). ``weeks`` = the run's planned horizon (the bridge
    passes its filtered horizon); the dominant period kind of those weeks picks the profile."""
    term = term or await session.get(Term, run.term_id)
    assert term is not None
    if weeks_rows is None:
        weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    kinds = week_kinds(weeks_rows)
    if weeks is None:
        from app.services.solver_bridge import horizon_weeks

        weeks = horizon_weeks(run, term, kinds=kinds)
    segs = list((await session.execute(select(SeasonSegment).where(SeasonSegment.term_id == term.id))).scalars())
    season = season_of(term)
    pkind = dominant_period_kind(run.kind or "COURSE", weeks, kinds, segment_kind_by_week(segs))
    params = run.params or {}
    set_w, warnings = await settings_weights(session)
    override = params.get(PROFILE_PARAM)
    profile = await resolve_profile(session, season, pkind, str(override) if override is not None else None)
    run_w, run_warn = clean_weights(params.get("weights") or {})
    layers: list[tuple[str, Mapping[str, int]]] = [("settings", set_w)]
    if profile is not None:
        layers.append((profile.label, profile.solver_weights))
    layers.append(("run", run_w))
    weights, source, overrides = merge_layers(layers)
    return EffectiveWeights(weights, source, overrides, profile, season, pkind, warnings + run_warn)


__all__ = [
    "BUILTIN_KEYS",
    "BUILTIN_PROFILES",
    "COURSE_SKIP_KINDS",
    "EffectiveWeights",
    "PROFILE_PARAM",
    "PeriodSegment",
    "ResolvedProfile",
    "clean_weights",
    "closed_days",
    "course_weeks",
    "dominant_period_kind",
    "effective_weights",
    "is_summer_term",
    "load_calendar",
    "load_periods",
    "match_score",
    "merge_layers",
    "period_kind_on",
    "periods",
    "resolve_profile",
    "season_of",
    "week_kinds",
    "week_of_date",
    "week_start",
]
