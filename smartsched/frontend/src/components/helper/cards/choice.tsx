"use client";
/**
 * HX-04 (helper.md §4.2, A2): the `choice` card ("Hangi A 204?"). 2–5 options as 44 px rows; a pick asks the action's
 * card again with the other arguments the server already resolved. The server sends one choice at a time, so the
 * counter is the client's: it shows from the second choice of a run on ("2. soru").
 */
import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import type { CardEntry } from "../helper-store";
import type { ChoiceCard } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { CancelledLine, HelperCardFrame } from "./frame";

export function ChoiceView({ card, entry }: { card: ChoiceCard; entry: CardEntry }) {
  const { t } = useI18n();
  const host = useCardHost();
  const step = entry.step ?? 1;
  const open = entry.phase === "pending";
  const pick = (value: string | number) => {
    if (!card.action) return;
    void host.runner.runAction(card.action, { ...(card.args ?? {}), [card.arg]: value }, { hints: entry.hints, step: step + 1, replaces: entry.key });
  };
  return (
    <HelperCardFrame
      testId={`helper-card-choice${card.action ? `-${card.action}` : ""}`}
      title={pickText(card.question, host.locale)}
      actions={
        open ? (
          <Button variant="ghost" size="md" onClick={() => host.runner.cancel(entry)} data-testid="helper-choice-cancel">
            {t("helper.card.cancel")}
          </Button>
        ) : undefined
      }
    >
      {entry.phase === "cancelled" ? <CancelledLine /> : null}
      {step > 1 ? <p className="type-footnote text-label-3">{t("helper.card.step", { n: step })}</p> : null}
      <ul className="flex flex-col gap-1">
        {card.options.map((o) => (
          <li key={String(o.value)}>
            <Button
              variant="secondary"
              disabled={!open}
              onClick={() => pick(o.value)}
              className="h-auto min-h-11 w-full justify-between gap-3 px-3 py-2 text-left whitespace-normal"
              shape="rect"
              data-testid={`helper-choice-${o.value}`}
            >
              <span className="flex min-w-0 flex-col">
                <span className="font-medium text-label-1">{pickText(o.label, host.locale)}</span>
                {o.hint ? <span className="type-footnote text-label-2">{pickText(o.hint, host.locale)}</span> : null}
              </span>
              <ChevronRight aria-hidden />
            </Button>
          </li>
        ))}
      </ul>
    </HelperCardFrame>
  );
}
