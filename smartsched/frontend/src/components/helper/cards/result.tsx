"use client";
/**
 * HX-04 (helper.md §4.1 rule 6, §4.4, A7): the `result` card. A check, one line (the focus moves to it after the
 * button, and the log's polite live region reads it), "Aç" for the object, "Geri al" while the undo token is valid,
 * and at most 2 follow-up chips (an action with partial args, or a page). The disc's glyph is `--mat-thick-solid`
 * (white in light, the sheet's dark in dark): white on the dark theme's light green / red was 1.7–2.0:1 (HX-18 M3).
 */
import { Check, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { featureHref } from "../feature-links";
import type { CardEntry } from "../helper-store";
import type { ResultCard } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { HelperCardFrame } from "./frame";

export function ResultView({ card, entry }: { card: ResultCard; entry: CardEntry }) {
  const { t } = useI18n();
  const host = useCardHost();
  const open = card.entity?.feature_id ? featureHref(card.entity.feature_id) : null;
  // the window is read when the card appears; the server refuses a late undo with its own message anyway
  const [shownAt] = useState(() => Date.now());
  const undoOpen = !!card.undo_token && !entry.undone && (!card.undo_expires_at || Date.parse(card.undo_expires_at) > shownAt);
  const busy = entry.phase === "busy";
  return (
    <HelperCardFrame
      testId={`helper-card-result-${card.action}`}
      tone="done"
      actions={
        open || undoOpen ? (
          <>
            {open ? (
              <Button size="md" variant="secondary" onClick={() => host.go(open)} data-testid="helper-card-open">
                {t("helper.card.open")}
              </Button>
            ) : null}
            {undoOpen ? (
              <Button
                size="md"
                variant="ghost"
                aria-disabled={busy || undefined}
                aria-busy={busy || undefined}
                onClick={(e) => {
                  if (!busy) void host.runner.undo(entry, e);
                }}
                data-testid="helper-card-undo"
              >
                {busy ? t("busy.working") : t("helper.card.undo")}
              </Button>
            ) : null}
          </>
        ) : undefined
      }
    >
      <p tabIndex={-1} data-focus-target="" data-testid="helper-card-result" className="flex items-start gap-2 type-body text-label-1 outline-hidden focus-visible:outline-2 focus-visible:outline-(--focus) rounded-sm">
        <span aria-hidden className={cn("mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-(--mat-thick-solid)", card.ok ? "helper-check bg-status-feasible-fg" : "bg-status-infeasible-fg")}>
          {card.ok ? <Check className="size-3.5 stroke-[3]" /> : <X className="size-3.5 stroke-[3]" />}
        </span>
        <span>
          <span className="sr-only">{card.ok ? t("helper.card.done") : t("helper.card.notDone")}: </span>
          {pickText(card.message, host.locale)}
        </span>
      </p>
      {entry.undone && card.undo_token ? <p className="type-callout text-label-2" data-testid="helper-card-undone">{t("helper.card.undone")}</p> : null}
      {entry.notice ? <p className="type-footnote text-status-warning-fg">{pickText(entry.notice, host.locale)}</p> : null}
      {card.follow_ups?.length && !entry.undone ? (
        <ul className="flex flex-wrap gap-2" aria-label={t("helper.card.next")}>
          {card.follow_ups.slice(0, 2).map((f, i) => {
            const href = f.feature_id ? featureHref(f.feature_id) : null;
            const go = f.action ? () => void host.runner.runAction(f.action!, f.args ?? {}) : href ? () => host.go(href) : null;
            if (!go) return null;
            return (
              <li key={i}>
                <Chip onClick={go} className="min-h-11" data-testid={`helper-follow-up-${i}`}>
                  {pickText(f.label, host.locale)}
                </Chip>
              </li>
            );
          })}
        </ul>
      ) : null}
    </HelperCardFrame>
  );
}
