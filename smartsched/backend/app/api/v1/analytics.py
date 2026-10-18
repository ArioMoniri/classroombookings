"""Planning analytics (docs/features.yml "Scenario comparison ..., utilisation heatmaps ..."): read-only views.

* ``GET /analytics/compare?a=&b=`` - two runs of one term and kind side by side (``app/services/scenario_compare``);
* ``GET /analytics/heatmap/rooms`` - room x day x period occupancy of a run or the live board
  (``app/services/utilisation``);
* ``GET /analytics/heatmap/instructors`` - instructor load of a course run or the published course run.

Every view answers JSON, or CSV with ``format=csv`` (a download with a file name).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Planner, Viewer
from app.models import ScheduleRun, Term
from app.services import scenario_compare as sc
from app.services import utilisation as util

router = APIRouter(prefix="/analytics", tags=["analytics"])

Fmt = Literal["json", "csv"]


def _horizon(run: Any, lang: str) -> str:
    hp = run.horizon_params or {}
    weeks = sorted({int(w) for w in (hp.get("weeks") or []) if str(w).isdigit()})
    if run.horizon == "WEEK" and weeks:
        if lang == "tr":
            return f"{weeks[0]}. hafta" if len(weeks) == 1 else f"{weeks[0]}.–{weeks[-1]}. haftalar"
        return f"week {weeks[0]}" if len(weeks) == 1 else f"weeks {weeks[0]}–{weeks[-1]}"
    if run.horizon == "MONTH":
        start = hp.get("start_week")
        return (
            (f"{start}. haftadan 4 hafta" if lang == "tr" else f"4 weeks from week {start}")
            if start
            else ("ay" if lang == "tr" else "month")
        )
    return "tüm dönem" if lang == "tr" else "whole term"


def compare_refusal(a: Any, b: Any, term_codes: dict[int, str]) -> dict[str, str]:
    """The 422 for two runs that cannot be compared (round-2 T-R2-27, R2-M-21): names the reason (different terms,
    different kinds) and each run's term, kind and horizon, and says that different horizons alone are fine."""
    kind_tr = {"COURSE": "ders", "EXAM": "sınav"}
    kind_en = {"COURSE": "course", "EXAM": "exam"}

    def desc(r: Any, lang: str) -> str:
        code = term_codes.get(r.term_id, f"#{r.term_id}")
        kind = (kind_tr if lang == "tr" else kind_en).get(r.kind, str(r.kind).lower())
        return f"#{r.id} ({code}, {kind}, {_horizon(r, lang)})"

    why_tr = "dönemleri farklı" if a.term_id != b.term_id else "türleri farklı"
    why_en = "different terms" if a.term_id != b.term_id else "different kinds"
    return {
        "code": "compare_scope",
        "tr": (
            f"{desc(a, 'tr')} ile {desc(b, 'tr')} karşılaştırılamaz: {why_tr}. Aynı dönemin aynı türden iki "
            "çalıştırmasını seçin; kapsamları farklı olabilir (dönem ile haftalık çalıştırma yalnız ortak haftalarda "
            "karşılaştırılır)."
        ),
        "en": (
            f"{desc(a, 'en')} and {desc(b, 'en')} cannot be compared: {why_en}. Pick two runs of the same term and "
            "kind; their horizons may differ (a term run and a week run are compared on their common weeks)."
        ),
    }


def _csv(body: str, name: str) -> Response:
    return Response(
        content="﻿" + body,  # BOM: Excel opens UTF-8 (Turkish letters) correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/compare", response_model=None)
async def compare_runs(
    db: DB,
    _: Viewer,
    a: int = Query(..., description="baseline run id (A)"),
    b: int = Query(..., description="scenario run id (B)"),
    week: int | None = Query(None, ge=1, le=60),
    format: Fmt = "json",  # noqa: A002 - the public query parameter name
    part: Literal["classes", "instructors", "rooms", "rules", "metrics"] = "classes",
) -> dict[str, Any] | Response:
    try:
        data = await sc.compare(db, a, b, week=week)
    except sc.CompareError as exc:
        if exc.status == 422 and a != b:
            # round-2 T-R2-27 (R2-M-21): say which of term / kind differs and name each run's horizon, instead of
            # one sentence for every refusal
            ra, rb = await db.get(ScheduleRun, a), await db.get(ScheduleRun, b)
            if ra is not None and rb is not None and (ra.term_id != rb.term_id or ra.kind != rb.kind):
                codes = {
                    t.id: t.code
                    for t in (await db.execute(select(Term).where(Term.id.in_({ra.term_id, rb.term_id})))).scalars()
                }
                raise HTTPException(422, compare_refusal(ra, rb, codes)) from exc
        raise HTTPException(exc.status, exc.detail) from exc
    except util.UtilisationError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    if format == "csv":
        return _csv(sc.compare_csv(data, part), f"karsilastirma-{a}-{b}-{part}.csv")
    return data


@router.get("/heatmap/rooms", response_model=None)
async def room_heatmap(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    run_id: int | None = None,
    group_by: Literal["building", "room_type", "capacity_band", "room"] = "building",
    week: int | None = Query(None, ge=1, le=60),
    scope: Literal["week", "term"] = "week",
    axis: Literal["day", "date"] | None = None,
    bookings: bool = True,
    blocks: bool = True,
    rooms: bool = Query(False, description="add one row per room under each group"),
    format: Fmt = "json",  # noqa: A002
) -> dict[str, Any] | Response:
    try:
        data = await util.room_heatmap(
            db,
            term_id=term_id,
            run_id=run_id,
            group_by=group_by,
            week=week,
            scope=scope,
            axis=axis,
            bookings=bookings,
            blocks=blocks,
            rooms_detail=rooms,
        )
    except util.UtilisationError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    if format == "csv":
        src = f"run-{run_id}" if run_id else f"term-{data['term_id']}"
        return _csv(util.room_heatmap_csv(data), f"doluluk-{src}-{group_by}.csv")
    return data


@router.get("/heatmap/instructors", response_model=None)
async def instructor_heatmap(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    run_id: int | None = None,
    week: int | None = Query(None, ge=1, le=60),
    scope: Literal["week", "term"] = "week",
    q: str | None = Query(None, max_length=100),
    limit: int = Query(500, ge=1, le=5000),
    format: Fmt = "json",  # noqa: A002
) -> dict[str, Any] | Response:
    try:
        data = await util.instructor_heatmap(
            db, term_id=term_id, run_id=run_id, week=week, scope=scope, q=q, limit=limit
        )
    except util.UtilisationError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    if format == "csv":
        src = f"run-{data['run_id']}"
        return _csv(util.instructor_heatmap_csv(data), f"egitmen-yuku-{src}.csv")
    return data


# ------------------------------------------------------------------------------------------- adaptive (AS-05..)
# aggregate demand ledger (AS-05), peak hours (AS-06), forecasts (AS-07, AS-10, AS-11); app/services/{demand,peaks,
# forecast,exam_load}.py. Every view answers on an empty install with ``confidence: "none"`` and a ``needs`` text.


@router.get("/demand", response_model=None)
async def demand_view(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    group_by: Literal[
        "weekday_period", "period", "weekday", "headcount_band", "feature", "building", "period_kind"
    ] = "weekday_period",
) -> dict[str, Any]:
    """Find-room / booking demand cells; counts under 5 come back as ``"<5"`` (KVKK)."""
    from app.services import demand

    return await demand.demand(db, term_id=term_id, group_by=group_by)


@router.get("/peaks", response_model=None)
async def peaks_view(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    group_by: Literal["campus", "building", "room_type", "capacity_band"] = "building",
    period_kind: Literal["LECTURE", "EXAM", "MAKEUP", "SUMMER", "ADD_DROP", "MIDTERM"] = "LECTURE",
    threshold: float | None = Query(None, ge=50, le=100),
    format: Fmt = "json",  # noqa: A002
) -> dict[str, Any] | Response:
    """Peak cells (weekday x period x group) with 80 % ranges; ``confidence: none`` + ``needs`` without data."""
    from app.services import peaks

    data = await peaks.peaks(db, term_id=term_id, group_by=group_by, period_kind=period_kind, threshold=threshold)
    if format == "csv":
        import csv
        import io

        from app.core.export_safety import safe_writer

        buf = io.StringIO()
        w = safe_writer(csv.writer(buf))
        w.writerow(["group_by", "group", "day", "period", "value", "lo80", "hi80", "n_weeks", "seat_fill", "peak"])
        for c in data["cells"]:
            w.writerow(
                [
                    group_by,
                    c["group"],
                    c["day"],
                    c["period"],
                    c["value"],
                    c["lo80"],
                    c["hi80"],
                    c["n_weeks"],
                    c["seat_fill"] if c["seat_fill"] is not None else "",
                    int(c["peak"]),
                ]
            )
        return _csv(buf.getvalue(), f"yogun-saatler-{data['term_id'] or 'yok'}-{group_by}.csv")
    return data


@router.get("/peaks/campus", response_model=None)
async def peaks_campus_view(db: DB, _: CurrentUser, term_id: int | None = None) -> dict[str, Any]:
    """AS20-F03: the campus peak cells for the find-room "Yoğun saat" chip, for anyone signed in (the people who
    book rooms have no planning.view). Aggregate busy shares of the published timetable only: no run ids or
    labels, no groups below the campus."""
    from app.services import peaks

    data = await peaks.peaks(db, term_id=term_id, group_by="campus")
    data.pop("sources", None)
    return data


@router.get("/forecast/demand", response_model=None)
async def forecast_demand(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    group_by: Literal["building", "weekday", "period", "tag", "capacity_band", "cell"] = "building",
) -> dict[str, Any]:
    """Room demand per group: ``requests`` (the term's own list), ``seasonal_naive`` or ``none`` + ``needs``."""
    from app.services import forecast

    return await forecast.demand_forecast(db, term_id, group_by)


@router.get("/forecast/shortfall", response_model=None)
async def forecast_shortfall(db: DB, _: Viewer, term_id: int, peaks_only: bool = False) -> dict[str, Any]:
    """Demand vs suitable supply per (weekday, period, room group) with the competing requests."""
    from app.services import forecast

    try:
        return await forecast.shortfall(db, term_id, peaks_only=peaks_only)
    except LookupError as exc:
        raise HTTPException(
            404, {"code": "term_not_found", "message_tr": "dönem bulunamadı", "message_en": "term not found"}
        ) from exc


class WhatIfIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int
    enrolment_pct: float = Field(0.0, ge=-90, le=200)
    scope: Literal["all", "faculty", "program"] = "all"
    scope_value: str | None = Field(None, max_length=255)
    rooms_closed: list[int] = Field(default_factory=list, max_length=500)
    extra_sections: int = Field(0, ge=0, le=200)
    solve: bool = False


@router.post("/forecast/what-if", response_model=None)
async def forecast_what_if(body: WhatIfIn, db: DB, user: Planner) -> dict[str, Any]:
    """Room fit and shortfall today vs the scenario; ``solve: true`` queues a draft run "Senaryo: ..." (never
    active)."""
    from app.services import forecast

    if body.scope != "all" and not body.scope_value:
        raise HTTPException(
            422,
            {
                "code": "scope_value",
                "message": "a faculty or programme scope needs scope_value",
                "message_en": "a faculty or programme scope needs scope_value",
                "message_tr": "fakülte ya da program kapsamı için scope_value gerekli",
            },
        )
    try:
        return await forecast.what_if(db, body.term_id, body.model_dump(), user)
    except LookupError as exc:
        raise HTTPException(
            404, {"code": "term_not_found", "message_tr": "dönem bulunamadı", "message_en": "term not found"}
        ) from exc


@router.get("/forecast/exams/advice", response_model=None)
async def forecast_exams_advice(db: DB, _: Viewer, term_id: int) -> dict[str, Any]:
    """AS-12 exam date advisor: load cards and ranked date / slot moves for the term's exam requests. Advice only:
    ``changes_nothing`` is always true; a planner applies a move on /exams."""
    from app.services import exam_advisor

    try:
        return await exam_advisor.advise_term(db, term_id)
    except LookupError as exc:
        raise HTTPException(
            404, {"code": "term_not_found", "message_tr": "dönem bulunamadı", "message_en": "term not found"}
        ) from exc


class AdviceApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_id: int
    request_ids: list[int] = Field(min_length=1, max_length=200)
    date: dt.date
    start_period: int = Field(ge=1, le=30)


@router.post("/forecast/exams/advice/apply", response_model=None)
async def forecast_exams_advice_apply(body: AdviceApplyIn, db: DB, user: Planner) -> dict[str, Any]:
    """AS20-F04 "Uygula": move the exam rows of one advisor suggestion (planning.edit; audited per row). The answer
    carries ``undo``, the same body with the old date and start, for the undo toast."""
    from app.services import exam_advisor

    try:
        return await exam_advisor.apply_to_requests(
            db,
            term_id=body.term_id,
            request_ids=body.request_ids,
            new_date=body.date,
            start_period=body.start_period,
            actor=user,
        )
    except exam_advisor.ApplyError as exc:
        raise HTTPException(exc.status, exc.detail()) from exc


@router.get("/forecast/exams", response_model=None)
async def forecast_exams(
    db: DB, _: Viewer, term_id: int, students_per_invigilator: int | None = Query(None, ge=5, le=500)
) -> dict[str, Any]:
    """Exam seats per day and slot vs exam capacity, invigilators vs the pool, exam-week bookings, draft holds."""
    from app.services import exam_load

    try:
        return await exam_load.exam_forecast(db, term_id, students_per_invigilator=students_per_invigilator)
    except LookupError as exc:
        raise HTTPException(
            404, {"code": "term_not_found", "message_tr": "dönem bulunamadı", "message_en": "term not found"}
        ) from exc
