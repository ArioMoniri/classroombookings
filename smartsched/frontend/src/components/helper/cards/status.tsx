"use client";
/**
 * HX-04 (helper.md §4.2, §5.3): `limit` / `refusal` / `error` — the server's message in an alert inside the log, the
 * index hits it sent as one-line `nav` rows (at most 6), and "Menüde ara" (the palette). A refusal never says who holds a permission.
 */
import { Search } from "lucide-react";
import { Alert, type AlertTone } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import type { ErrorCard, LimitCard, RefusalCard } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { NavView } from "./nav";

/** HX-18 M4: the index hits are rows, at most 6 */
const MAX_ROWS = 6;

const TONE: Record<"limit" | "refusal" | "error", AlertTone> = { limit: "warning", refusal: "info", error: "error" };

export function StatusView({ card }: { card: LimitCard | RefusalCard | ErrorCard }) {
  const { t } = useI18n();
  const host = useCardHost();
  return (
    <div className="flex flex-col gap-2" data-testid={`helper-card-${card.type}${card.action ? `-${card.action}` : ""}`} data-code={card.code}>
      <Alert tone={TONE[card.type]} live="polite">
        {pickText(card.message, host.locale)}
      </Alert>
      {card.fallback?.length ? (
        <div className="flex flex-col">
          {card.fallback.slice(0, MAX_ROWS).map((n) => (
            <NavView key={n.id} card={n} compact />
          ))}
        </div>
      ) : null}
      <Button variant="ghost" size="md" className="self-start" onClick={() => host.searchMenu()} data-testid="helper-search-menu">
        <Search aria-hidden />
        {t("helper.card.searchMenu")}
      </Button>
    </div>
  );
}
