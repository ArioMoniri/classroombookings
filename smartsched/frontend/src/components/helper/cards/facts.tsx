"use client";
/**
 * HX-04 / HX-05 (helper.md §4.2): the `facts` card (run_status, requests_needing_review, my_ai_usage). Label / value
 * rows; the value is the server's sentence with its unit (simplicity rule 5: never a bare number). A status adds a
 * word-bearing tint, never colour alone. `nav` opens the page the facts come from.
 */
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { featureHref } from "../feature-links";
import type { FactsCard } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { CardLine, HelperCardFrame } from "./frame";

export function FactsView({ card }: { card: FactsCard }) {
  const { t } = useI18n();
  const host = useCardHost();
  const href = card.nav ? featureHref(card.nav) : null;
  return (
    <HelperCardFrame
      testId={`helper-card-facts${card.action ? `-${card.action}` : ""}`}
      title={card.title ? pickText(card.title, host.locale) : undefined}
      actions={
        href ? (
          <Button variant="secondary" size="md" onClick={() => host.go(href)} data-testid="helper-card-secondary">
            {t("helper.where.open")}
          </Button>
        ) : undefined
      }
    >
      <dl className="flex flex-col gap-1.5">
        {card.items.map((f, i) => (
          <CardLine key={i} label={pickText(f.label, host.locale)} value={pickText(f.value, host.locale)} tone={f.status === "info" ? undefined : f.status} />
        ))}
      </dl>
    </HelperCardFrame>
  );
}
