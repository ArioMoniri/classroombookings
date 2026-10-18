"use client";
/**
 * HX-04 (helper.md §4.1 rule 2, §4.2): one log entry → our component, chosen by the card's wire `type` (+ `action`).
 * Nothing renders from untyped data: a card the zod rejected arrives as a fallback entry, and a write card for an
 * action this client has no presentation for falls back to a short text + "Menüde ara". "Yalnızca metin" turns
 * `list` / `facts` into one short text line (+ the page); confirm cards stay, as they are the only way to act.
 */
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { featureHref } from "../feature-links";
import type { LogEntry } from "../helper-store";
import type { FactsCard, ListCard } from "../schema.gen";
import { AnswerView } from "./answer";
import { ChoiceView } from "./choice";
import { ConfirmView } from "./confirm";
import { pickText, useCardHost } from "./context";
import { FactsView } from "./facts";
import { FormView } from "./form";
import { ListView } from "./list";
import { NavView } from "./nav";
import { ResultView } from "./result";
import { StatusView } from "./status";

/**
 * The server registry (`GET /helper/schema` → actions), plus HB-D's `remember_note` ("Bunu hatırla", HX-17: not a
 * registry action, its card comes only from a typed "bunu hatırla: …"); a write card for any other name is not rendered.
 */
export const KNOWN_ACTIONS: ReadonlySet<string> = new Set([
  "open_feature", "search_site", "find_free_rooms", "room_day_schedule", "my_bookings", "my_requests_status", "approvals_inbox", "run_status",
  "requests_needing_review", "my_ai_usage", "create_booking", "cancel_my_booking", "withdraw_my_request", "decide_approval", "undo_last_helper_action",
  "remember_note",
]);

export function FallbackView() {
  const { t } = useI18n();
  const host = useCardHost();
  return (
    <div className="flex flex-col gap-2" data-testid="helper-card-fallback">
      <p className="type-body text-label-1">{t("helper.card.unknown")}</p>
      <Button variant="ghost" size="md" className="self-start" onClick={() => host.searchMenu()} data-testid="helper-search-menu">
        <Search aria-hidden />
        {t("helper.card.searchMenu")}
      </Button>
    </div>
  );
}

function TextOnly({ card }: { card: ListCard | FactsCard }) {
  const { t } = useI18n();
  const host = useCardHost();
  const title = card.title ? pickText(card.title, host.locale) : "";
  const text =
    card.type === "list"
      ? card.rows.length
        ? card.rows
            .slice(0, 5)
            .map((r) => {
              const first = card.columns[0];
              const v = first ? r.cells[first.key] : undefined;
              return typeof v === "string" ? v : v ? pickText(v, host.locale) : r.id;
            })
            .join(", ")
        : card.empty
          ? pickText(card.empty, host.locale)
          : t("helper.card.emptyList")
      : card.items.map((f) => `${pickText(f.label, host.locale)}: ${pickText(f.value, host.locale)}`).join(" · ");
  const href = card.type === "list" ? (card.more ? featureHref(card.more) : null) : card.nav ? featureHref(card.nav) : null;
  return (
    <div className="flex flex-col gap-2" data-testid={`helper-card-${card.type}${card.action ? `-${card.action}` : ""}`} data-text-only="">
      <p className="type-body text-label-1">
        {title ? <span className="font-medium">{title}: </span> : null}
        {text}
      </p>
      {href ? (
        <Button variant="secondary" size="md" className="self-start" onClick={() => host.go(href)}>
          {t("helper.where.open")}
        </Button>
      ) : null}
    </div>
  );
}

export function EntryView({ entry }: { entry: LogEntry }) {
  const host = useCardHost();
  if (entry.kind === "user") {
    return (
      <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-tint px-3 py-2 type-body text-tint-foreground whitespace-pre-line" data-testid="helper-user">
        {entry.text}
      </p>
    );
  }
  if (entry.kind === "note") return <p className="type-callout text-label-2" data-testid="helper-note-line">{pickText(entry.text, host.locale)}</p>;
  if (entry.kind === "fallback") return <FallbackView />;
  const card = entry.card;
  const writeLike = card.type === "confirm" || card.type === "form" || card.type === "choice" || card.type === "result";
  if (writeLike && (!card.action || !KNOWN_ACTIONS.has(card.action))) return <FallbackView />;
  switch (card.type) {
    case "answer":
      return <AnswerView card={card} entry={entry} />;
    case "nav":
      return <NavView card={card} />;
    case "list":
      return host.textOnly ? <TextOnly card={card} /> : <ListView card={card} />;
    case "facts":
      return host.textOnly ? <TextOnly card={card} /> : <FactsView card={card} />;
    case "choice":
      return <ChoiceView card={card} entry={entry} />;
    case "form":
      return <FormView card={card} entry={entry} />;
    case "confirm":
      return <ConfirmView card={card} entry={entry} />;
    case "result":
      return <ResultView card={card} entry={entry} />;
    case "limit":
    case "refusal":
    case "error":
      return <StatusView card={card} />;
    default:
      return <FallbackView />;
  }
}
