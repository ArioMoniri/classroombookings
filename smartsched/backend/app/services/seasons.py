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
        if run and (
            (w.kind or "LECTURE").upper() != (run[-1].kind or "LECTURE").upper()
            or int(w.index) != int(run[-1].index) + 1
        ):
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
        wk_to = sg.week_to or sg.week_from
        wt_mon = week_start(term, wk_to, rows) if wk_to else None
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
            await session.execute(
                select(SeasonProfile).where(SeasonProfile.status == "active").order_by(SeasonProfile.id)
            )
        ).scalars()
    )


async def resolve_profile(
    session: AsyncSession, season: str, period_kind: str, override: str | None = None
) -> ResolvedProfile | None:
    """The profile for (season, period kind): ``override`` (a key; ``"none"`` = no profile) else the most specific
    active profile (an admin's beats a built-in at equal specificity; the latest approved wins a tie)."""
    if override is not None and str(override).lower() == "none":
        return None
    return pick_profile(await active_profiles(session), season, period_kind, override)


def pick_profile(
    rows: Sequence[SeasonProfile], season: str, period_kind: str, override: str | None = None
) -> ResolvedProfile | None:
    """:func:`resolve_profile` on already loaded active rows (no SQL: the booking-policy index calls it per date)."""
    if override is not None and str(override).lower() == "none":
        return None
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


def merge_layers(
    layers: Sequence[tuple[str, Mapping[str, int]]],
) -> tuple[dict[str, int], dict[str, str], dict[str, int]]:
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


#: the admin's default solver seed (Ayarlar › Çözücü; stored through ``PUT /settings`` ``extra``, audit RF-02)
SEED_SETTING = "solver_default_seed"


async def effective_seed(session: AsyncSession, run: ScheduleRun) -> tuple[int, str]:
    """(seed, source) of a run: ``params.seed`` (``run``) > the admin's ``solver_default_seed`` (``settings``) >
    0 (``default``). Read on the server, so every run path (POST /runs, Studio, moderation re-solves, fix and chat
    child runs) uses the admin's seed."""
    params = run.params or {}
    if params.get("seed") is not None:
        try:
            return int(params["seed"]), "run"
        except (TypeError, ValueError):
            pass
    from app.models import Setting

    row = await session.get(Setting, SEED_SETTING)
    raw = row.value if row is not None and not row.is_secret else None
    try:
        value = int(float(str(raw).strip())) if raw not in (None, "") else None
    except ValueError:
        value = None
    if value is not None and 0 <= value <= 2**31 - 1:
        return value, "settings"
    return 0, "default"


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


# ------------------------------------------------------------------------------------------------ profile admin

#: overlay keys (AS-04): limits reuse the booking-policy columns; ``exam_hold`` overrides the exam-period mode
OVERLAY_LIMITS = (
    ("max_active_bookings", 0, 10_000),
    ("min_notice_workdays", 0, 365),
    ("max_advance_days", 0, 3650),
    ("max_duration_minutes", 10, 24 * 60),
    ("buffer_minutes", 0, 240),
)
EXAM_HOLD_MODES = ("off", "request", "closed", "slots")
OVERLAY_EFFECTS = ("refuse", "request")
#: weight names a profile may set: the solver's defaults plus the opt-in peak smoothing of AS-08
EXTRA_WEIGHT_KEYS = frozenset({"peak_smoothing"})


class SeasonError(Exception):
    """A refused profile / segment change (``status`` 404 / 409 / 422), Turkish and English."""

    def __init__(self, status: int, code: str, message_en: str, message_tr: str, **extra: Any) -> None:
        super().__init__(message_en)
        self.status, self.code, self.message_en, self.message_tr, self.extra = (
            status,
            code,
            message_en,
            message_tr,
            extra,
        )

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message_en,
            "message_en": self.message_en,
            "message_tr": self.message_tr,
            **self.extra,
        }


def weight_keys() -> list[str]:
    return sorted(set(DEFAULT_WEIGHTS) | EXTRA_WEIGHT_KEYS)


def _invalid(message_en: str, message_tr: str, **extra: Any) -> SeasonError:
    return SeasonError(422, "profile_invalid", message_en, message_tr, **extra)


def validate_weights(raw: Any) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > MAX_WEIGHT_KEYS:
        raise _invalid(
            f"solver_weights must be an object with at most {MAX_WEIGHT_KEYS} entries",
            f"solver_weights en çok {MAX_WEIGHT_KEYS} girdili bir nesne olmalı",
        )
    known = set(weight_keys())
    out: dict[str, int] = {}
    for k, v in raw.items():
        if k not in known:
            raise _invalid(f"unknown weight {k!r}", f"bilinmeyen ağırlık: {k}", field="solver_weights", key=k)
        ok = isinstance(v, int | float) and not isinstance(v, bool) and float(v).is_integer()
        if not ok or not 0 <= int(v) <= MAX_WEIGHT:
            raise _invalid(
                f"weight {k} must be a whole number 0..{MAX_WEIGHT}",
                f"{k} ağırlığı 0 ile {MAX_WEIGHT} arasında bir tam sayı olmalı",
                field="solver_weights",
                key=k,
            )
        out[str(k)] = int(v)
    return out


def validate_applies_to(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw or len(raw) > 20:
        raise _invalid(
            "applies_to must be a list of 1..20 {season, period_kind} entries",
            "applies_to 1-20 adet {season, period_kind} girdisinden oluşan bir liste olmalı",
        )
    out: list[dict[str, str]] = []
    from app.models.seasons import SEASONS

    for a in raw:
        if not isinstance(a, Mapping):
            raise _invalid("applies_to entries are objects", "applies_to girdileri nesne olmalı")
        season = n.fold(str(a.get("season") or "*")).upper()
        kind = str(a.get("period_kind") or "*").upper()
        if season not in (*SEASONS, "*"):
            raise _invalid(
                f"season {a.get('season')!r}: one of {', '.join(SEASONS)} or *",
                f"dönem {a.get('season')}: {', '.join(SEASONS)} ya da * olmalı",
                field="applies_to",
            )
        if kind not in (*PERIOD_KINDS, "*"):
            raise _invalid(
                f"period_kind {a.get('period_kind')!r}: one of {', '.join(PERIOD_KINDS)} or *",
                f"dönem türü {a.get('period_kind')}: {', '.join(PERIOD_KINDS)} ya da * olmalı",
                field="applies_to",
            )
        out.append({"season": season, "period_kind": kind})
    return out


def validate_overlays(raw: Any) -> list[dict[str, Any]]:
    """Booking overlays (AS-04): ``{"scope": "all" | "tag:PC" | "building:A" | "room:A101", "period_kinds": [...],
    "effect": "refuse" | "request", <limit>: n, "exam_hold": off|request|closed|slots, "buffer_periods": 0..4}``."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 20:
        raise _invalid(
            "booking_overlays must be a list of at most 20", "booking_overlays en çok 20 girdili liste olmalı"
        )
    out: list[dict[str, Any]] = []
    for o in raw:
        if not isinstance(o, Mapping):
            raise _invalid("booking_overlays entries are objects", "booking_overlays girdileri nesne olmalı")
        scope = n.clean_text(str(o.get("scope") or "all")) or "all"
        kind, _sep, value = scope.partition(":")
        kind = kind.strip().lower()
        if kind not in ("all", "tag", "building", "room") or (kind != "all" and not value.strip()):
            raise _invalid(
                f"overlay scope {scope!r}: all, tag:<TAG>, building:<code> or room:<code>",
                f"kapsam {scope}: all, tag:<ETİKET>, building:<bina> ya da room:<oda> olmalı",
                field="booking_overlays",
            )
        item: dict[str, Any] = {"scope": "all" if kind == "all" else f"{kind}:{n.tr_upper(value.strip())}"}
        if kind == "room":
            item["scope"] = f"room:{n.tr_upper(value.strip()).replace(' ', '')}"
        kinds = o.get("period_kinds")
        if kinds is not None:
            if not isinstance(kinds, list) or any(str(k).upper() not in PERIOD_KINDS for k in kinds):
                raise _invalid(
                    f"period_kinds: a list of {', '.join(PERIOD_KINDS)}",
                    f"period_kinds: {', '.join(PERIOD_KINDS)} değerlerinden oluşan bir liste olmalı",
                    field="booking_overlays",
                )
            item["period_kinds"] = sorted({str(k).upper() for k in kinds})
        effect = str(o.get("effect") or "refuse")
        if effect not in OVERLAY_EFFECTS:
            raise _invalid("overlay effect: refuse or request", "etki: refuse ya da request", field="booking_overlays")
        item["effect"] = effect
        has = False
        for key, lo, hi in OVERLAY_LIMITS:
            v = o.get(key)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise _invalid(f"{key} must be {lo}..{hi}", f"{key} {lo} ile {hi} arasında olmalı", field=key)
            item[key], has = int(v), True
        hold = o.get("exam_hold")
        if hold is not None:
            if hold not in EXAM_HOLD_MODES:
                raise _invalid(
                    f"exam_hold: one of {', '.join(EXAM_HOLD_MODES)}",
                    f"sınav tutma kipi: {', '.join(EXAM_HOLD_MODES)}",
                    field="exam_hold",
                )
            item["exam_hold"], has = hold, True
            bp = o.get("buffer_periods", 1)
            if isinstance(bp, bool) or not isinstance(bp, int) or not 0 <= bp <= 4:
                raise _invalid("buffer_periods must be 0..4", "buffer_periods 0 ile 4 arasında olmalı")
            item["buffer_periods"] = int(bp)
        if not has:
            raise _invalid("an overlay needs a limit or exam_hold", "bir ek kural en az bir sınır içermeli")
        out.append(item)
    return out


def _text(raw: Any, field_name: str, max_len: int = 128) -> str:
    text = n.clean_text(str(raw)) if raw is not None else None
    if not text:
        raise _invalid(f"{field_name} is required", f"{field_name} gerekli", field=field_name)
    return text[:max_len]


def _explanation(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise _invalid("explanation is {tr, en}", "explanation {tr, en} olmalı")
    return {k: (n.clean_text(str(raw.get(k))) or "")[:2000] for k in ("tr", "en") if raw.get(k)}


def profile_out(row: SeasonProfile | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row, Mapping):  # a built-in
        return {
            "id": None,
            "key": row["key"],
            "version": row["version"],
            "name": _t(row["name_tr"], row["name_en"]),
            "name_tr": row["name_tr"],
            "name_en": row["name_en"],
            "applies_to": list(row["applies_to"]),
            "solver_weights": dict(row["solver_weights"]),
            "booking_overlays": list(row["booking_overlays"]),
            "peak_threshold_pct": row["peak_threshold_pct"],
            "status": "active",
            "builtin": True,
            "origin": "builtin",
            "parent_id": None,
            "created_by": None,
            "approved_by": None,
            "approved_at": None,
            "explanation": dict(row["explanation"]),
            "evidence": {},
            "source": f"profile:{row['key']}@{row['version']}",
            "weights_diff": [],
        }
    return {
        "id": row.id,
        "key": row.key,
        "version": row.version,
        "name": _t(row.name_tr, row.name_en),
        "name_tr": row.name_tr,
        "name_en": row.name_en,
        "applies_to": list(row.applies_to or []),
        "solver_weights": dict(row.solver_weights or {}),
        "booking_overlays": list(row.booking_overlays or []),
        "peak_threshold_pct": row.peak_threshold_pct,
        "status": row.status,
        "builtin": False,
        "origin": row.origin,
        "parent_id": row.parent_id,
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "explanation": dict(row.explanation or {}),
        "evidence": dict(row.evidence or {}),
        "source": f"profile:{row.key}@{row.version}",
        # what differs from the standard (default) weights: the "ağırlıklar" diff of the admin page
        "weights_diff": [
            {"key": k, "default": DEFAULT_WEIGHTS.get(k), "value": int(v)}
            for k, v in sorted((row.solver_weights or {}).items())
            if DEFAULT_WEIGHTS.get(k) != v
        ],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def list_profiles(session: AsyncSession) -> dict[str, Any]:
    rows = list(
        (await session.execute(select(SeasonProfile).order_by(SeasonProfile.key, SeasonProfile.version))).scalars()
    )
    return {
        "profiles": [profile_out(p) for p in BUILTIN_PROFILES] + [profile_out(r) for r in rows],
        "weight_keys": weight_keys(),
        "defaults": dict(DEFAULT_WEIGHTS),
        "seasons": [{"key": k, "label": _t(*v)} for k, v in SEASON_LABEL.items()],
        "period_kinds": [{"key": k, "label": _t(*KIND_LABEL[k])} for k in PERIOD_KINDS],
    }


async def get_profile(session: AsyncSession, profile_id: int) -> SeasonProfile:
    row = await session.get(SeasonProfile, profile_id)
    if row is None:
        raise SeasonError(404, "profile_not_found", "season profile not found", "dönem profili bulunamadı")
    return row


def _clean_key(raw: Any) -> str:
    import re

    key = n.fold(str(raw or "")).lower().strip().replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]{0,63}", key):
        raise _invalid(
            "key: 1-64 characters a-z, 0-9, - and _", "anahtar: 1-64 karakter (a-z, 0-9, - ve _)", field="key"
        )
    if key in BUILTIN_KEYS or key == "none":
        raise SeasonError(409, "profile_builtin", f"{key!r} is a built-in profile", f"{key} yerleşik bir profil")
    return key


def _fields(data: Mapping[str, Any], base: SeasonProfile | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if base is None or "name_tr" in data:
        out["name_tr"] = _text(data.get("name_tr"), "name_tr")
    if base is None or "name_en" in data:
        out["name_en"] = _text(data.get("name_en"), "name_en")
    if base is None or "applies_to" in data:
        out["applies_to"] = validate_applies_to(data.get("applies_to"))
    if base is None or "solver_weights" in data:
        out["solver_weights"] = validate_weights(data.get("solver_weights"))
    if base is None or "booking_overlays" in data:
        out["booking_overlays"] = validate_overlays(data.get("booking_overlays"))
    if base is None or "peak_threshold_pct" in data:
        pt = data.get("peak_threshold_pct", DEFAULT_PEAK_THRESHOLD)
        if isinstance(pt, bool) or not isinstance(pt, int) or not 50 <= pt <= 100:
            raise _invalid("peak_threshold_pct must be 50..100", "yoğunluk eşiği %50 ile %100 arasında olmalı")
        out["peak_threshold_pct"] = int(pt)
    if base is None or "explanation" in data:
        out["explanation"] = _explanation(data.get("explanation"))
    if "evidence" in data:
        ev = data.get("evidence")
        if ev is not None and not isinstance(ev, Mapping):
            raise _invalid("evidence is an object", "evidence bir nesne olmalı")
        out["evidence"] = dict(ev or {})
    return out


async def _next_version(session: AsyncSession, key: str) -> int:
    from sqlalchemy import func

    cur = (await session.execute(select(func.max(SeasonProfile.version)).where(SeasonProfile.key == key))).scalar()
    return int(cur or 0) + 1


async def create_profile(
    session: AsyncSession, data: Mapping[str, Any], *, actor: Any, origin: str = "admin"
) -> SeasonProfile:
    """A new draft (version = the key's next version). Drafts never apply until :func:`activate_profile`."""
    key = _clean_key(data.get("key"))
    fields = _fields(data)
    row = SeasonProfile(
        key=key,
        version=await _next_version(session, key),
        status="draft",
        origin=origin if origin in ("admin", "learned", "proposed") else "admin",
        created_by=getattr(actor, "id", None),
        **fields,
    )
    session.add(row)
    await session.flush()
    await _audit(session, "season_profile.create", row, actor)
    return row


async def update_profile(
    session: AsyncSession, profile_id: int, data: Mapping[str, Any], *, actor: Any
) -> SeasonProfile:
    """A draft is edited in place; an active profile gets a new draft version (``parent_id`` = the active one);
    a retired version is read-only (409)."""
    row = await get_profile(session, profile_id)
    fields = _fields(data, base=row)
    if row.status == "draft":
        before = profile_out(row)
        for k, v in fields.items():
            setattr(row, k, v)
        await session.flush()
        await _audit(session, "season_profile.update", row, actor, before=before)
        return row
    if row.status != "active":
        raise SeasonError(
            409,
            "profile_retired",
            "a retired version is read-only; edit the active version",
            "emekliye ayrılmış sürüm değiştirilemez; etkin sürümü düzenleyin",
        )
    child = SeasonProfile(
        key=row.key,
        version=await _next_version(session, row.key),
        status="draft",
        origin=row.origin,
        parent_id=row.id,
        created_by=getattr(actor, "id", None),
        name_tr=row.name_tr,
        name_en=row.name_en,
        applies_to=list(row.applies_to or []),
        solver_weights=dict(row.solver_weights or {}),
        booking_overlays=list(row.booking_overlays or []),
        peak_threshold_pct=row.peak_threshold_pct,
        explanation=dict(row.explanation or {}),
        evidence=dict(row.evidence or {}),
    )
    for k, v in fields.items():
        setattr(child, k, v)
    session.add(child)
    await session.flush()
    await _audit(session, "season_profile.update", child, actor, before=profile_out(row))
    return child


async def activate_profile(session: AsyncSession, profile_id: int, *, actor: Any) -> SeasonProfile:
    """Approve a draft (or bring back a retired version): it becomes the key's only active version."""
    from app.models.base import utcnow

    row = await get_profile(session, profile_id)
    if row.status == "active":
        return row
    for other in (
        await session.execute(
            select(SeasonProfile).where(SeasonProfile.key == row.key, SeasonProfile.status == "active")
        )
    ).scalars():
        other.status = "retired"
    row.status = "active"
    row.approved_by = getattr(actor, "id", None)
    row.approved_at = utcnow()
    await session.flush()
    await _audit(session, "season_profile.activate", row, actor)
    return row


async def revert_profile(session: AsyncSession, profile_id: int, *, actor: Any) -> SeasonProfile:
    """ "Geri al": the active version ``profile_id`` is retired and its parent becomes active again."""
    from app.models.base import utcnow

    row = await get_profile(session, profile_id)
    if row.status != "active":
        raise SeasonError(
            409, "profile_not_active", "only the active version can be reverted", "yalnız etkin sürüm geri alınabilir"
        )
    if row.parent_id is None:
        raise SeasonError(
            409,
            "profile_no_parent",
            "this is the first version: nothing to revert to",
            "ilk sürüm: dönülecek önceki sürüm yok",
        )
    parent = await get_profile(session, row.parent_id)
    row.status = "retired"
    parent.status = "active"
    parent.approved_by = getattr(actor, "id", None)
    parent.approved_at = utcnow()
    await session.flush()
    await _audit(session, "season_profile.revert", parent, actor, before=profile_out(row))
    return parent


async def retire_profile(session: AsyncSession, profile_id: int, *, actor: Any) -> SeasonProfile:
    row = await get_profile(session, profile_id)
    before = profile_out(row)
    if row.status == "draft":
        await session.delete(row)
        await session.flush()
        await _audit(session, "season_profile.delete", None, actor, before=before, entity_id=profile_id)
        return row
    row.status = "retired"
    await session.flush()
    await _audit(session, "season_profile.retire", row, actor, before=before)
    return row


async def _audit(
    session: AsyncSession,
    action: str,
    row: SeasonProfile | None,
    actor: Any,
    *,
    before: dict[str, Any] | None = None,
    entity_id: int | None = None,
) -> None:
    from app.services.audit import jsonable
    from app.services.events import publish_event

    await publish_event(
        session,
        action,
        "season_profile",
        row.id if row is not None else entity_id,
        before=jsonable(before) if before else None,
        after=jsonable(profile_out(row)) if row is not None else None,
        actor=actor,
    )


# ------------------------------------------------------------------------------------------------ segments


def validate_segment(data: Mapping[str, Any], base: SeasonSegment | None = None) -> dict[str, Any]:
    from app.services.booking_policies import _parse_date

    out: dict[str, Any] = {}
    if base is None or "kind" in data:
        kind = str(data.get("kind") or "").upper()
        if kind not in PERIOD_KINDS:
            raise SeasonError(
                422,
                "segment_invalid",
                f"kind: one of {', '.join(PERIOD_KINDS)}",
                f"tür: {', '.join(PERIOD_KINDS)} olmalı",
            )
        out["kind"] = kind
    for k in ("week_from", "week_to"):
        if k in data:
            v = data.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 60):
                raise SeasonError(422, "segment_invalid", f"{k} must be 1..60", f"{k} 1 ile 60 arasında olmalı")
            out[k] = v
    for k in ("date_from", "date_to"):
        if k in data:
            v = data.get(k)
            try:
                out[k] = _parse_date(v) if v not in (None, "") else None
            except ValueError as exc:
                raise SeasonError(422, "segment_invalid", f"{k}: YYYY-MM-DD", f"{k}: GG.AA.YYYY") from exc
    wf = out.get("week_from", base.week_from if base else None)
    wt = out.get("week_to", base.week_to if base else None)
    df = out.get("date_from", base.date_from if base else None)
    dt = out.get("date_to", base.date_to if base else None)
    if wf is None and df is None:
        raise SeasonError(
            422,
            "segment_invalid",
            "a segment needs week_from or date_from",
            "bir dönem parçası hafta ya da tarih ister",
        )
    if wf is not None and wt is not None and wt < wf:
        raise SeasonError(422, "segment_invalid", "week_to is before week_from", "bitiş haftası başlangıçtan önce")
    if df is not None and dt is not None and dt < df:
        raise SeasonError(422, "segment_invalid", "date_to is before date_from", "bitiş tarihi başlangıçtan önce")
    kind = out.get("kind", base.kind if base else "LECTURE")
    tr_default, en_default = KIND_LABEL.get(kind, (kind, kind))
    if base is None or "label_tr" in data:
        out["label_tr"] = (n.clean_text(str(data.get("label_tr") or "")) or tr_default)[:128]
    if base is None or "label_en" in data:
        out["label_en"] = (n.clean_text(str(data.get("label_en") or "")) or en_default)[:128]
    if "status" in data:
        st = str(data.get("status") or "active")
        if st not in ("draft", "active"):
            raise SeasonError(422, "segment_invalid", "status: draft or active", "durum: draft ya da active")
        out["status"] = st
    return out


def segment_out(sg: SeasonSegment) -> dict[str, Any]:
    return {
        "id": sg.id,
        "term_id": sg.term_id,
        "kind": sg.kind,
        "kind_label": _t(*KIND_LABEL.get(sg.kind, (sg.kind, sg.kind))),
        "week_from": sg.week_from,
        "week_to": sg.week_to,
        "date_from": sg.date_from.isoformat() if sg.date_from else None,
        "date_to": sg.date_to.isoformat() if sg.date_to else None,
        "label": _t(sg.label_tr, sg.label_en),
        "status": sg.status,
    }


async def term_periods(session: AsyncSession, term_id: int) -> dict[str, Any]:
    term = await session.get(Term, term_id)
    if term is None:
        raise SeasonError(404, "term_not_found", "term not found", "dönem bulunamadı")
    weeks_rows, holidays, segs = await load_calendar(session, term)
    season = season_of(term)
    label = SEASON_LABEL.get(season, (season, season))
    out_periods = [p.as_dict() for p in periods(term, weeks_rows, holidays, segs)]
    return {
        "term_id": term.id,
        "term_code": term.code,
        "season": {"key": season, "label": _t(*label)},
        "periods": out_periods,
        "segments": [segment_out(sg) for sg in segs],
        "empty": not out_periods,
        "needs": None
        if out_periods
        else _t(
            "Dönemin hafta türleri yok: haftalık çizelgeyi içe aktarın ya da Haftalar sayfasında işaretleyin",
            "The term has no week kinds: import the weekly grid or mark them on the Weeks page",
        ),
    }


__all__ = [
    "BUILTIN_KEYS",
    "SEED_SETTING",
    "effective_seed",
    "SeasonError",
    "activate_profile",
    "create_profile",
    "list_profiles",
    "profile_out",
    "revert_profile",
    "term_periods",
    "update_profile",
    "validate_overlays",
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
