"""Read actions 8-9 for planners: ``run_status`` (GET /runs) and ``requests_needing_review`` (GET /requests/stats).

Both call the route functions themselves (the planning routes keep their queries inline), after the registry checked
the same ``planning.view`` guard. ``GET /runs/{id}/summary`` is not used: it stores the recomputed verdict, and read
actions write nothing."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from sqlalchemy import select

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.registry import ActionRefused, Args, Ctx, action
from app.models import ScheduleRun, Term

RUN_STATUS_TEXT = {
    "QUEUED": ("Sırada", "Queued"),
    "RUNNING": ("Çalışıyor", "Running"),
    "FEASIBLE": ("Uygun çözüm bulundu", "Feasible"),
    "FEASIBLE_PARTIAL": ("Kısmi çözüm", "Partly placed"),
    "OPTIMAL": ("En iyi çözüm bulundu", "Optimal"),
    "INFEASIBLE": ("Çözüm yok", "Infeasible"),
    "FAILED": ("Hata", "Failed"),
    "CANCELLED": ("İptal edildi", "Cancelled"),
    "TIMEOUT": ("Süre doldu", "Timed out"),
    "ERROR": ("Hata", "Error"),
}


class TermArgs(Args):
    term: Annotated[str, Field(max_length=32, description="term code such as '2026-BAHAR'; '' = the current term")] = ""


async def _term(ctx: Ctx, code: str) -> Term | None:
    if code:
        t = (await ctx.session.execute(select(Term).where(Term.code == code.strip().upper()))).scalar_one_or_none()
        if t is None:
            raise ActionRefused(404, "term_not_found", f"{code} dönemi bulunamadı.", f"Term {code} was not found.")
        return t
    active_run = (
        (
            await ctx.session.execute(
                select(ScheduleRun).where(ScheduleRun.is_active.is_(True)).order_by(ScheduleRun.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if active_run is not None:
        return await ctx.session.get(Term, active_run.term_id)
    return (await ctx.session.execute(select(Term).order_by(Term.is_active.desc(), Term.id.desc()))).scalars().first()


def _run_fact(label: tuple[str, str], run: Any) -> s.Fact:
    st_tr, st_en = RUN_STATUS_TEXT.get(run.status, (run.status, run.status))
    placed = (
        (f" · {run.placed}/{run.events_total} ders yerleşti", f" · {run.placed}/{run.events_total} classes placed")
        if run.events_total
        else ("", "")
    )
    name = cards.clean(run.label or "", 60)
    status = (
        "ok"
        if run.status in ("FEASIBLE", "OPTIMAL") and not run.partial
        else ("warn" if run.status in ("FEASIBLE_PARTIAL", "QUEUED", "RUNNING") else "bad")
    )
    return s.Fact(
        label=cards.txt(*label),
        value=cards.txt(f"#{run.id} {name} · {st_tr}{placed[0]}".strip(), f"#{run.id} {name} · {st_en}{placed[1]}"),
        status=status,  # type: ignore[arg-type]
    )


@action(
    name="run_status",
    kind="read",
    permission=("planning.view",),
    args=TermArgs,
    summary_tr="Çalıştırma durumu",
    summary_en="Run status",
    description="Show the published timetable run and the latest solver run of a term.",
    route="GET /runs",
    card="facts",
    resolved=("term",),
)
async def run_status(ctx: Ctx, args: TermArgs) -> s.CardBase:
    from app.api.v1.runs import list_runs

    term = await _term(ctx, args.term)
    runs = await list_runs(
        ctx.session, ctx.access.user, term_id=term.id if term else None, kind=None, status=None, limit=20
    )
    if not runs:
        return s.FactsCard(
            id=cards.new_id(),
            action="run_status",
            title=cards.txt("Çalıştırma durumu", "Run status"),
            items=[
                s.Fact(
                    label=cards.txt("Çalıştırma", "Runs"),
                    value=cards.txt("Bu dönem için henüz çalıştırma yok.", "No run for this term yet."),
                )
            ],
            nav="generate",
        )
    items = []
    active = next((r for r in runs if r.is_active), None)
    if active is not None:
        items.append(_run_fact(("Yayındaki plan", "Published plan"), active))
    else:
        items.append(
            s.Fact(
                label=cards.txt("Yayındaki plan", "Published plan"),
                value=cards.txt("Henüz yayınlanmış plan yok.", "No plan is published yet."),
                status="warn",
            )
        )
    latest = runs[0]
    if active is None or latest.id != active.id:
        items.append(_run_fact(("Son çalıştırma", "Latest run"), latest))
    running = sum(1 for r in runs if r.status in ("QUEUED", "RUNNING"))
    if running:
        items.append(
            s.Fact(
                label=cards.txt("Sürenler", "In progress"),
                value=cards.txt(f"{running} çalıştırma sürüyor", f"{running} run(s) in progress"),
                status="info",
            )
        )
    term_name = cards.clean(term.name if term else "", 60)
    return s.FactsCard(
        id=cards.new_id(),
        action="run_status",
        title=cards.txt(f"Çalıştırma durumu · {term_name}", f"Run status · {term_name}"),
        items=items,
        nav="runs",
    )


REVIEW_STATUSES = ("NEW", "PARSED", "NEEDS_REVIEW")


@action(
    name="requests_needing_review",
    kind="read",
    permission=("planning.view",),
    args=TermArgs,
    summary_tr="İncelenecek talepler",
    summary_en="Requests to review",
    description="Count the meeting and exam requests of a term that still need review.",
    route="GET /requests/stats",
    card="facts",
    resolved=("term",),
)
async def requests_needing_review(ctx: Ctx, args: TermArgs) -> s.CardBase:
    from app.api.v1.requests import request_stats

    term = await _term(ctx, args.term)
    if term is None:
        raise ActionRefused(404, "term_not_found", "Henüz dönem yok.", "There is no term yet.")
    st = await request_stats(ctx.session, ctx.access.user, term_id=term.id)
    meetings: dict[str, int] = st["meetings"]
    exams: dict[str, int] = st["exams"]
    review = meetings.get("NEEDS_REVIEW", 0) + exams.get("NEEDS_REVIEW", 0)
    open_ = sum(meetings.get(k, 0) + exams.get(k, 0) for k in REVIEW_STATUSES)
    done = meetings.get("LOCKED", 0) + exams.get("LOCKED", 0)
    term_name = cards.clean(term.name, 60)
    return s.FactsCard(
        id=cards.new_id(),
        action="requests_needing_review",
        title=cards.txt(f"Talepler · {term_name}", f"Requests · {term_name}"),
        items=[
            s.Fact(
                label=cards.txt("İncelenecek", "Needs review"),
                value=cards.txt(f"{review} talep sizin kararınızı bekliyor", f"{review} request(s) wait for you"),
                status="warn" if review else "ok",
            ),
            s.Fact(
                label=cards.txt("Henüz kesinleşmemiş", "Not final yet"),
                value=cards.txt(f"{open_} talep", f"{open_} request(s)"),
                status="info",
            ),
            s.Fact(
                label=cards.txt("Kesinleşmiş", "Final"),
                value=cards.txt(f"{done} talep", f"{done} request(s)"),
                status="ok",
            ),
        ],
        nav="requests",
    )
