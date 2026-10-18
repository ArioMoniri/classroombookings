"""Read action 10: ``my_ai_usage`` (GET /ai/me/usage): the person's own AI use today and this month, as sentences."""

from __future__ import annotations

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.ai.helper.actions.registry import Args, Ctx, action

STATE_TEXT = {
    "ok": ("Sınırın altındasınız.", "You are within your limit.", "ok"),
    "soft": ("Sınırınıza yaklaştınız.", "You are close to your limit.", "warn"),
    "hard": (
        "Sınırınıza ulaştınız; arama ve kısayollar çalışmaya devam eder.",
        "You reached your limit; search and shortcuts still work.",
        "bad",
    ),
    "org_soft": ("Kurumun bu ayki payı azaldı.", "The institution's monthly budget is running low.", "warn"),
    "none": ("Sizin için bir sınır tanımlı değil.", "No limit is set for you.", "info"),
}


def _tokens(n: int | None, limit: int | None) -> tuple[str, str]:
    used = f"{int(n or 0):,}".replace(",", ".")
    if not limit:
        return f"{used} belirteç (sınır yok)", f"{int(n or 0):,} tokens (no limit)"
    lim = f"{int(limit):,}".replace(",", ".")
    return f"{used} / {lim} belirteç", f"{int(n or 0):,} / {int(limit):,} tokens"


class NoArgs(Args):
    pass


@action(
    name="my_ai_usage",
    kind="read",
    args=NoArgs,
    summary_tr="Yapay zekâ kullanımım",
    summary_en="My AI usage",
    description="Show how much of their own AI allowance the user used today and this month.",
    route="GET /ai/me/usage",
    card="facts",
)
async def my_ai_usage(ctx: Ctx, _args: NoArgs) -> s.CardBase:
    from app.services import ai_usage as meter

    st = await meter.user_state(ctx.session, ctx.access.user)
    tr, en, status = STATE_TEXT.get(str(st.get("state")), STATE_TEXT["none"])
    return s.FactsCard(
        id=cards.new_id(),
        action="my_ai_usage",
        title=cards.txt("Yapay zekâ kullanımım", "My AI usage"),
        items=[
            s.Fact(
                label=cards.txt("Bugün", "Today"),
                value=cards.txt(*_tokens(st.get("day_tokens"), st.get("daily_limit"))),
            ),
            s.Fact(
                label=cards.txt("Bu ay", "This month"),
                value=cards.txt(*_tokens(st.get("month_tokens"), st.get("monthly_limit"))),
            ),
            s.Fact(label=cards.txt("Durum", "Status"), value=cards.txt(tr, en), status=status),  # type: ignore[arg-type]
        ],
        nav="profile.ai_usage",
    )
