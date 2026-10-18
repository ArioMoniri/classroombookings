"use client";
/**
 * HX-04 / HX-05 (helper.md §4.2, A8): the `list` card (find_room, room_day, my_bookings, my_requests, approvals).
 * At most 5 rows are shown (the wire allows 20); "Tümünü {sayfa} sayfasında aç" opens the rest on the page. Row actions
 * ask the action's card with the row's args (no model call): "Ayır" → confirm, "İptal et" → confirm, R2 rows →
 * confirm with "Etkilenenler". The first column is the row's name; the others form one meta line, which wraps to a
 * second line on phones.
 */
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { featureHref, featureTitle } from "../feature-links";
import type { ListCard, Row } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { HelperCardFrame } from "./frame";

export const LIST_VISIBLE = 5;

function cellText(v: Row["cells"][string] | undefined, locale: "tr" | "en"): string {
  if (v === undefined || v === null) return "";
  return typeof v === "string" ? v : pickText(v, locale);
}

export function ListView({ card }: { card: ListCard }) {
  const { t } = useI18n();
  const host = useCardHost();
  const rows = card.rows.slice(0, LIST_VISIBLE);
  const [first, ...rest] = card.columns;
  const moreHref = card.more ? featureHref(card.more) : null;
  const morePage = card.more ? featureTitle(card.more, host.locale) : null;
  const hidden = Math.max(0, card.total - rows.length);
  return (
    <HelperCardFrame
      testId={`helper-card-list${card.action ? `-${card.action}` : ""}`}
      title={card.title ? pickText(card.title, host.locale) : undefined}
      actions={
        moreHref && (hidden > 0 || card.rows.length > rows.length) ? (
          <Button variant="secondary" size="md" onClick={() => host.go(moreHref)} data-testid="helper-list-more">
            {morePage ? t("helper.card.openAllOn", { page: morePage }) : t("helper.where.open")}
          </Button>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <p className="type-callout text-label-2">{card.empty ? pickText(card.empty, host.locale) : t("helper.card.emptyList")}</p>
      ) : (
        <ul className="flex flex-col" aria-label={card.title ? pickText(card.title, host.locale) : undefined}>
          {rows.map((row) => {
            const name = first ? cellText(row.cells[first.key], host.locale) : row.id;
            const meta = rest.map((c) => cellText(row.cells[c.key], host.locale)).filter(Boolean).join(" · ");
            const actions = (row.actions ?? []).filter((a) => !host.actions || host.actions.has(a.action)).slice(0, 3);
            return (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2 not-last:edge-hairline-b" data-testid={`helper-row-${row.id}`}>
                <div className="min-w-0 flex-1">
                  <p className="truncate type-callout font-medium text-label-1">{name}</p>
                  {meta ? <p className="type-footnote text-label-2">{meta}</p> : null}
                </div>
                {actions.length ? (
                  <div className="flex shrink-0 flex-wrap gap-1">
                    {actions.map((a) => {
                      const label = pickText(a.label, host.locale);
                      return (
                        <Button
                          key={`${a.action}-${label}`}
                          size="sm"
                          variant={a.danger ? "destructive" : "secondary"}
                          className="min-h-11"
                          aria-label={`${label}: ${name}`}
                          onClick={() => void host.runner.runAction(a.action, a.args ?? {})}
                          data-testid={`helper-row-action-${a.action}`}
                        >
                          {label}
                        </Button>
                      );
                    })}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {hidden > 0 ? <p className="type-footnote text-label-3">{t("helper.card.moreRows", { n: hidden })}</p> : null}
    </HelperCardFrame>
  );
}
