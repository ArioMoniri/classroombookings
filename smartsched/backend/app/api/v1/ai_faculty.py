"""Faculty AI quota managers (HB-11; docs/research/2026-10-17-ai-helper-architecture.md §5.9).

Who: holders of ``ai.usage_faculty`` ("Fakültemin yapay zekâ kullanımını görme ve paylaştırma"), for the faculties
that list them in ``ai.limits.faculties[id].managers``; when no faculty lists them, the faculty of their own
department. Administrators (``planning.admin`` / ``setup.settings``) see every faculty.

* ``GET /ai/faculty/usage?faculty_id=`` — this month's totals, by department, by feature and the daily trend of
  one faculty, from the rows' faculty snapshot (``ai_usage.faculty_id``, HB-10). By person **only** when the admin
  switched ``show_people`` on for that faculty, and then the token total only (KVKK proportionality: no cost, no
  features, no prompts, no times per person).
  ``faculty.share_of_allowance`` and ``by_department[].share_of_allowance`` (0..1, ``null`` without an allowance;
  HB-21) let the UI say "payın %40'ı" instead of token counts.
* ``PUT /ai/faculty/allocations`` — split the faculty's monthly allocation across its departments (the sum may not
  exceed the faculty's allocation); audited ``ai.faculty_allocation``. A manager cannot change the faculty's own
  allocation, the routes, the keys or the guardrails.

Every read is cross-user, so it runs in ``rls.system_scope`` **after** the scope check, with the faculty filter in
SQL (``WHERE faculty_id = :id``), never in Python after the read.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway as gw
from app.ai.context import FEATURE_LABELS
from app.api.deps import DB, require_permission
from app.core import rls
from app.models import Faculty, User
from app.models.ai_usage import AIUsage
from app.models.catalog import Program
from app.services import ai_usage as meter
from app.services import audit

router = APIRouter(tags=["ai-faculty"])
PERMISSION = "ai.usage_faculty"
ADMIN_PERMS = frozenset({"planning.admin", "setup.settings"})
FacultyManager = Annotated[User, Depends(require_permission(PERMISSION, *sorted(ADMIN_PERMS)))]

_TOKENS = AIUsage.input_tokens + AIUsage.output_tokens + AIUsage.cache_read_tokens + AIUsage.cache_write_tokens


def _err(status: int, code: str, tr: str, en: str, **extra: Any) -> HTTPException:
    return HTTPException(status, {"code": code, "message": en, "message_en": en, "message_tr": tr, **extra})


async def _is_admin(session: AsyncSession, user: User) -> bool:
    from app.services.bookings_perms import load_access

    return bool(ADMIN_PERMS & (await load_access(session, user)).perms)


async def faculties_in_scope(session: AsyncSession, user: User, limits: dict[str, Any]) -> list[int]:
    """The faculty ids ``user`` may see: every faculty for an administrator; else those listing them as a manager;
    else the faculty of their own department."""
    if await _is_admin(session, user):
        return list((await session.execute(select(Faculty.id).order_by(Faculty.name))).scalars())
    listed = [
        int(k)
        for k, v in (limits.get("faculties") or {}).items()
        if str(k).isdigit() and isinstance(v, dict) and user.id in {int(i) for i in v.get("managers") or []}
    ]
    if listed:
        return sorted(listed)
    _, own = await meter.units_of(session, user.id)
    return [own] if own is not None else []


async def _scope(session: AsyncSession, user: User, faculty_id: int | None) -> tuple[int, list[int], dict[str, Any]]:
    limits = await gw.get_limits(session)
    allowed = await faculties_in_scope(session, user, limits)
    if not allowed:
        raise _err(
            403,
            "no_faculty",
            "Hesabınız bir fakülteye bağlı değil ve hiçbir fakültenin yöneticisi olarak atanmadınız.",
            "Your account is not in a faculty and no faculty lists you as a manager.",
        )
    chosen = allowed[0] if faculty_id is None else faculty_id
    if chosen not in allowed:  # RA-11: never another faculty's numbers
        raise _err(403, "faculty_not_managed", "Bu fakülteyi göremezsiniz.", "You cannot see this faculty.")
    return chosen, allowed, limits


def _alloc(entry: Any) -> dict[str, Any]:
    entry = entry if isinstance(entry, dict) else {}
    return {
        "monthly_tokens": int(entry.get("monthly_tokens") or 0),
        "monthly_cost_usd": float(entry.get("monthly_cost_usd") or 0),
    }


def share_of_allowance(tokens: int, cost_usd: float, allocation: dict[str, Any]) -> float | None:
    """How much of an allowance is used, 0..1 (HB-21): the larger of the token and cost shares, 1 at or above the
    allowance, ``None`` when neither cap is set."""
    shares = []
    if allocation["monthly_tokens"] > 0:
        shares.append(tokens / allocation["monthly_tokens"])
    if allocation["monthly_cost_usd"] > 0:
        shares.append(cost_usd / allocation["monthly_cost_usd"])
    return round(min(1.0, max(shares)), 4) if shares else None


@router.get("/ai/faculty/usage")
async def faculty_usage(
    db: DB, user: FacultyManager, faculty_id: Annotated[int | None, Query(ge=1)] = None
) -> dict[str, Any]:
    """One faculty's AI usage this month (Europe/Istanbul): totals, by department, by feature, the daily trend, and
    by person (tokens only) when the admin enabled ``show_people``."""
    fid, allowed, limits = await _scope(db, user, faculty_id)
    entry = (limits.get("faculties") or {}).get(str(fid)) or {}
    start, end = meter.period_bounds()["month"]
    in_faculty = (AIUsage.faculty_id == fid, AIUsage.created_at >= start, AIUsage.created_at < end)
    names = {f.id: f.name for f in (await db.execute(select(Faculty).where(Faculty.id.in_(allowed)))).scalars()}
    programs = list(
        (await db.execute(select(Program).where(Program.faculty_id == fid).order_by(Program.name))).scalars()
    )
    async with rls.system_scope(db):  # cross-user, after the scope check; the faculty filter is in SQL
        total = (
            await db.execute(
                select(
                    func.coalesce(func.sum(_TOKENS), 0), func.coalesce(func.sum(AIUsage.cost_usd), 0.0),
                    func.count(AIUsage.id),
                ).where(*in_faculty)
            )
        ).one()  # fmt: skip
        by_dep = {
            r[0]: r
            for r in (
                await db.execute(
                    select(AIUsage.department_id, func.coalesce(func.sum(_TOKENS), 0),
                           func.coalesce(func.sum(AIUsage.cost_usd), 0.0), func.count(AIUsage.id))
                    .where(*in_faculty).group_by(AIUsage.department_id)
                )
            ).all()
        }  # fmt: skip
        by_feature = (
            await db.execute(
                select(AIUsage.feature, func.coalesce(func.sum(_TOKENS), 0), func.count(AIUsage.id))
                .where(*in_faculty).group_by(AIUsage.feature).order_by(func.sum(_TOKENS).desc())
            )
        ).all()  # fmt: skip
        day_rows = (await db.execute(select(AIUsage.created_at, _TOKENS).where(*in_faculty))).all()
        people_rows = (
            (
                await db.execute(
                    select(AIUsage.user_id, AIUsage.department_id, func.coalesce(func.sum(_TOKENS), 0))
                    .where(*in_faculty, AIUsage.user_id.is_not(None))
                    .group_by(AIUsage.user_id, AIUsage.department_id)
                    .order_by(func.sum(_TOKENS).desc()).limit(200)
                )
            ).all()
            if entry.get("show_people")
            else []
        )  # fmt: skip
    dep_alloc = limits.get("departments") or {}
    departments = []
    for p in programs:
        row = by_dep.get(p.id)
        tokens, cost = (int(row[1]), float(row[2])) if row else (0, 0.0)
        alloc = _alloc(dep_alloc.get(str(p.id)))
        departments.append(
            {
                "id": p.id,
                "name": p.name,
                "tokens": tokens,
                "cost_usd": round(cost, 6),
                "calls": int(row[3]) if row else 0,
                "allocation": alloc,
                "share_of_allowance": share_of_allowance(tokens, cost, alloc),
            }
        )
    trend: dict[str, int] = {}
    day = meter._local(start.replace(tzinfo=UTC)).date()
    last = meter._local(end.replace(tzinfo=UTC) - timedelta(seconds=1)).date()
    while day <= last:
        trend[day.isoformat()] = 0
        day += timedelta(days=1)
    for created, tokens in day_rows:
        k = meter._local(created.replace(tzinfo=UTC)).date().isoformat()
        trend[k] = trend.get(k, 0) + int(tokens or 0)
    out: dict[str, Any] = {
        "faculty": {
            "id": fid,
            "name": names.get(fid),
            "share_of_allowance": share_of_allowance(int(total[0]), float(total[1]), _alloc(entry)),
        },
        "faculties": [{"id": f, "name": names.get(f)} for f in allowed],
        "month": meter.month_key(),
        "allocation": _alloc(entry),
        "totals": {"tokens": int(total[0]), "cost_usd": round(float(total[1]), 6), "calls": int(total[2])},
        "by_department": departments,
        "by_feature": [
            {
                "feature": f,
                "label_tr": FEATURE_LABELS.get(f, (f, f))[0],
                "label_en": FEATURE_LABELS.get(f, (f, f))[1],
                "tokens": int(t),
                "calls": int(c),
            }
            for f, t, c in by_feature
        ],
        "trend": [{"day": k, "tokens": v} for k, v in sorted(trend.items())],
        "show_people": bool(entry.get("show_people")),
    }
    if entry.get("show_people"):
        ids = [r[0] for r in people_rows]
        users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()} if ids else {}
        dep_names = {p.id: p.name for p in programs}
        out["people"] = [
            {
                "label": (users[uid].full_name or users[uid].email) if uid in users else None,
                "department": dep_names.get(dep) if dep is not None else None,
                "tokens": int(tokens),
            }
            for uid, dep, tokens in people_rows
        ]
    return out


class DepartmentAllocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_tokens: int = Field(default=0, ge=0)
    monthly_cost_usd: float = Field(default=0.0, ge=0)


class AllocationsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faculty_id: int = Field(ge=1)
    #: programme id -> allocation; the faculty's departments not listed lose their allocation
    departments: dict[str, DepartmentAllocationIn] = Field(max_length=500)


@router.put("/ai/faculty/allocations")
async def put_allocations(body: AllocationsIn, db: DB, user: FacultyManager) -> dict[str, Any]:
    """Split the faculty's monthly allocation across its departments (sum ≤ the faculty's allocation)."""
    fid, _, limits = await _scope(db, user, body.faculty_id)
    faculty_cap = _alloc((limits.get("faculties") or {}).get(str(fid)))
    if not faculty_cap["monthly_tokens"] and not faculty_cap["monthly_cost_usd"]:
        raise _err(
            422,
            "no_faculty_allocation",
            "Bu fakülteye henüz bir aylık pay verilmedi; önce yöneticiniz fakültenin payını belirlemeli.",
            "This faculty has no monthly allocation yet; an administrator sets the faculty's allocation first.",
        )
    own = set((await db.execute(select(Program.id).where(Program.faculty_id == fid))).scalars())
    for k in body.departments:
        if not k.isdigit() or int(k) not in own:
            raise _err(
                422,
                "department_not_in_faculty",
                "Bu bölüm bu fakülteye bağlı değil.",
                "This department is not in this faculty.",
                field=f"departments.{k}",
            )
    stored = await gw.get_json(db, gw.LIMITS_KEY, {})
    current = dict(stored.get("departments") or {})
    before = {k: v for k, v in current.items() if k.isdigit() and int(k) in own}
    kept = {k: v for k, v in current.items() if not (k.isdigit() and int(k) in own)}
    after = {k: v.model_dump() for k, v in body.departments.items() if v.monthly_tokens or v.monthly_cost_usd}
    candidate = {**limits, "departments": {**kept, **after}}
    errors, _ = await meter.check_allocations(db, candidate)
    if errors:
        first = errors[0]
        raise _err(422, first["code"], first["message_tr"], first["message_en"], field=first["field"], errors=errors)
    stored["departments"] = {**kept, **after}
    await gw.put_json(db, gw.LIMITS_KEY, stored)
    await audit.record(
        db,
        "ai.faculty_allocation",
        "faculty",
        str(fid),
        before={"departments": before},
        after={"departments": after},
        actor=user,
    )
    await db.commit()
    return {"faculty_id": fid, "allocation": faculty_cap, "departments": after}


__all__ = ["PERMISSION", "faculties_in_scope", "router"]
