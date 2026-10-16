"""Invigilator assignment API (``app/services/invigilation.py``): the pool, plans (run, view, lock, reassign, re-run,
publish, delete), candidates of a post, roster and load exports. Writes need ``PLANNER``; reads ``VIEWER``."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, Planner, Viewer
from app.services import invigilation as svc

router = APIRouter(prefix="/invigilation", tags=["invigilation"])


def _err(exc: svc.PlanError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


def _csv(body: str, name: str) -> Response:
    return Response(
        content="﻿" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class UnavailableIn(BaseModel):
    date: str | None = None
    day: int | None = Field(None, ge=1, le=7)
    start_period: int | None = Field(None, ge=1, le=18)
    end_period: int | None = Field(None, ge=1, le=18)
    note: str | None = Field(None, max_length=200)


class PoolIn(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    instructor_id: int | None = None
    term_id: int | None = None
    kind: Literal["STAFF", "ASSISTANT", "INSTRUCTOR", "OTHER"] | None = None
    max_duties: int | None = Field(None, ge=0, le=200)
    max_per_day: int | None = Field(None, ge=0, le=200)
    load_factor: int | None = Field(None, ge=10, le=500)
    unavailable: list[UnavailableIn] | None = None
    active: bool | None = None
    notes: str | None = Field(None, max_length=2000)


class PlanParams(BaseModel):
    students_per_invigilator: int | None = Field(None, ge=1, le=1000)
    min_per_room: int | None = Field(None, ge=0, le=20)
    max_per_room: int | None = Field(None, ge=1, le=50)
    own_exam: Literal["prefer", "allow", "forbid"] | None = None
    instructor_pool: Literal["exam_instructors", "all", "none"] | None = None
    max_per_day: int | None = Field(None, ge=1, le=12)
    min_rest: int | None = Field(None, ge=0, le=6)
    time_limit_s: float | None = Field(None, ge=1, le=600)
    seed: int | None = Field(None, ge=0)
    weights: dict[str, int] | None = None


class PlanIn(BaseModel):
    exam_run_id: int
    label: str | None = Field(None, max_length=255)
    params: PlanParams = Field(default_factory=PlanParams)


class RerunIn(BaseModel):
    label: str | None = Field(None, max_length=255)
    params: PlanParams = Field(default_factory=PlanParams)


class ReassignIn(BaseModel):
    person_key: str = Field(..., max_length=32)
    reason: str | None = Field(None, max_length=500)


def _params(p: PlanParams) -> dict[str, Any]:
    return p.model_dump(exclude_none=True)


# ------------------------------------------------------------------------------------------- pool


@router.get("/pool")
async def list_pool(db: DB, _: Viewer, term_id: int | None = None) -> list[dict[str, Any]]:
    return await svc.list_pool(db, term_id)


@router.post("/pool", status_code=201)
async def create_pool_member(body: PoolIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        return await svc.save_pool_member(db, body.model_dump(exclude_unset=True), user)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.put("/pool/{member_id}")
async def update_pool_member(member_id: int, body: PoolIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        return await svc.save_pool_member(db, body.model_dump(exclude_unset=True), user, member_id)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.delete("/pool/{member_id}", status_code=204)
async def delete_pool_member(member_id: int, db: DB, user: Planner) -> None:
    try:
        await svc.delete_pool_member(db, member_id, user)
    except svc.PlanError as exc:
        raise _err(exc) from exc


# ------------------------------------------------------------------------------------------- plans


@router.post("/plans", status_code=202)
async def create_plan(body: PlanIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        plan = await svc.create_plan(db, body.exam_run_id, _params(body.params), user, label=body.label)
    except svc.PlanError as exc:
        raise _err(exc) from exc
    svc.enqueue_plan(plan.id)
    return {"plan_id": plan.id, "status": plan.status}


@router.get("/plans")
async def list_plans(
    db: DB, _: Viewer, exam_run_id: int | None = None, term_id: int | None = None
) -> list[dict[str, Any]]:
    return await svc.list_plans(db, exam_run_id=exam_run_id, term_id=term_id)


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int, db: DB, _: Viewer, person: str | None = Query(None, max_length=32)) -> dict[str, Any]:
    try:
        return await svc.plan_detail(db, plan_id, person=person)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.post("/plans/{plan_id}/rerun", status_code=202)
async def rerun_plan(plan_id: int, body: RerunIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        plan = await svc.rerun(db, plan_id, _params(body.params), user, label=body.label)
    except svc.PlanError as exc:
        raise _err(exc) from exc
    svc.enqueue_plan(plan.id)
    return {"plan_id": plan.id, "parent_plan_id": plan_id, "status": plan.status}


@router.post("/plans/{plan_id}/activate")
async def activate_plan(plan_id: int, db: DB, user: Planner) -> dict[str, Any]:
    try:
        return await svc.activate(db, plan_id, user)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, db: DB, user: Planner) -> None:
    try:
        await svc.delete_plan(db, plan_id, user)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.post("/plans/{plan_id}/duties/{duty_id}/lock")
async def lock_duty(plan_id: int, duty_id: int, db: DB, user: Planner, locked: bool = True) -> dict[str, Any]:
    try:
        return await svc.lock_duty(db, plan_id, duty_id, locked, user)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.put("/plans/{plan_id}/duties/{duty_id}")
async def reassign_duty(plan_id: int, duty_id: int, body: ReassignIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        return await svc.reassign_duty(db, plan_id, duty_id, body.person_key, user, body.reason)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.get("/plans/{plan_id}/candidates")
async def post_candidates(plan_id: int, db: DB, _: Viewer, post_key: str = Query(..., max_length=64)) -> dict[str, Any]:
    try:
        return await svc.candidates(db, plan_id, post_key)
    except svc.PlanError as exc:
        raise _err(exc) from exc


@router.get("/plans/{plan_id}/export", response_model=None)
async def export_roster(plan_id: int, db: DB, _: Viewer) -> Response:
    try:
        body = await svc.roster_csv(db, plan_id)
    except svc.PlanError as exc:
        raise _err(exc) from exc
    return _csv(body, f"gozetmen-plani-{plan_id}.csv")


@router.get("/plans/{plan_id}/load", response_model=None)
async def plan_load(
    plan_id: int,
    db: DB,
    _: Viewer,
    format: Literal["json", "csv"] = "json",  # noqa: A002 - the public query parameter name
) -> dict[str, Any] | Response:
    try:
        data = await svc.load_heatmap(db, plan_id)
    except svc.PlanError as exc:
        raise _err(exc) from exc
    if format == "csv":
        return _csv(svc.load_heatmap_csv(data), f"gozetmen-yuku-{plan_id}.csv")
    return data
