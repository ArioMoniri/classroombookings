"""Read actions 1-2: ``open_feature`` (a "Nerede?" card) and ``search_site`` (pages + data in one list)."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.registry import Args, Ctx, action, permitted_names
from app.ai.helper.index import get_index, visible


class OpenFeatureArgs(Args):
    feature_id: Annotated[str, Field(max_length=64, description="an id from the feature index hits")] = ""


@action(
    name="open_feature",
    kind="read",
    args=OpenFeatureArgs,
    summary_tr="Sayfayı göster",
    summary_en="Show the page",
    description="Show where a SmartSched page or control is and how to get there (a 'where' card). Use the "
    "feature_id of an index hit; never invent one.",
    route="GET /helper/search",
    card="nav",
    resolved=("feature_id",),
)
async def open_feature(ctx: Ctx, args: OpenFeatureArgs) -> s.CardBase:
    idx = get_index()
    entry = idx.by_id.get(args.feature_id)
    if entry is None or not visible(entry, ctx.access.perms):
        # helper.md §3.3 "not allowed": the same answer for a missing and a forbidden page (no hint of who may)
        near = idx.search(args.feature_id.replace(".", " ").replace("_", " "), ctx.access.perms, limit=3)
        return cards.status(
            "refusal",
            "not_allowed",
            "Bu işlem hesabınızda yok. Yapabildikleriniz:",
            "This isn't available on your account. What you can do:",
            cards.nav_hits(near, permitted_names(ctx.access)),
        )
    return cards.nav(entry, permitted_names(ctx.access))


class SearchSiteArgs(Args):
    q: Annotated[str, Field(max_length=200, description="what to look for, in the user's words")] = ""


@action(
    name="search_site",
    kind="read",
    args=SearchSiteArgs,
    summary_tr="Sitede ara",
    summary_en="Search the site",
    description="Search SmartSched pages, settings, rooms, courses, instructors and programmes the user may see.",
    route="GET /helper/search",
    card="list",
    route_args={"q": "q"},
)
async def search_site(ctx: Ctx, args: SearchSiteArgs) -> s.CardBase:
    from app.ai.helper.search import search

    found = await search(ctx.session, ctx.access, args.q, limit=cards.LIST_ROWS)
    rows: list[s.Row] = []
    for n in [*found["pages"], *found["where"]]:
        rows.append(
            s.Row(
                id=f"feature:{n['feature_id']}",
                cells={
                    "title": s.Txt(**n["title"]),
                    "where": s.Txt(tr=" › ".join(n["path"]["tr"]), en=" › ".join(n["path"]["en"])),
                },
                actions=[
                    s.RowAction(
                        action="open_feature",
                        label=cards.txt("Göster", "Show me"),
                        args={"feature_id": n["feature_id"]},
                    )
                ],
            )
        )
    for items in found["data"].values():
        for d in items:
            sub = d.get("sub")
            rows.append(
                s.Row(
                    id=f"{d['kind']}:{d['id']}",
                    cells={"title": d["label"], "where": s.Txt(**sub) if sub else cards.txt(d["kind"])},
                )
            )
    return s.ListCard(
        id=cards.new_id(),
        action="search_site",
        title=cards.txt(f"“{args.q}” için sonuçlar", f"Results for “{args.q}”"),
        columns=[
            s.Column(key="title", label=cards.txt("Ad", "Name"), kind="text"),
            s.Column(key="where", label=cards.txt("Nerede", "Where"), kind="text"),
        ],
        rows=rows[: cards.LIST_ROWS],
        total=len(rows),
        empty=cards.txt(f"“{args.q}” için sonuç yok.", f"No results for “{args.q}”."),
    )
