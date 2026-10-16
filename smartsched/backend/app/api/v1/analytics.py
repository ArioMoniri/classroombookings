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

from app.api.deps import DB, Viewer
from app.services import scenario_compare as sc
from app.services import utilisation as util

router = APIRouter(prefix="/analytics", tags=["analytics"])

Fmt = Literal["json", "csv"]


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
    except (sc.CompareError, util.UtilisationError) as exc:
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
