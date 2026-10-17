"""Planning analytics (docs/features.yml "Scenario comparison ..., utilisation heatmaps ..."): read-only views.

* ``GET /analytics/compare?a=&b=`` - two runs of one term and kind side by side (``app/services/scenario_compare``);
* ``GET /analytics/heatmap/rooms`` - room x day x period occupancy of a run or the live board
  (``app/services/utilisation``);
* ``GET /analytics/heatmap/instructors`` - instructor load of a course run or the published course run.

Every view answers JSON, or CSV with ``format=csv`` (a download with a file name).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import DB, Viewer
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
