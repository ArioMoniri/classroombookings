"use client";
/**
 * HX-04 / HX-06 (helper.md §3.3, §4.2): the `nav` ("where") card. The path line and the steps are the server's text;
 * the route, the anchor and the permission come from the client's link map, so an id the client cannot map, or one
 * this person may not open, renders nothing (double filter). Buttons: "Göster" (an anchor exists), "Sayfayı aç",
 * and "Burada yap" when the entry has an action this person may run here. Hand-overs keep the page's own dialog:
 * the calendar entry reads "Takvimime ekle", the invite entry "Davet penceresini aç".
 */
import { ChevronDown, MapPin } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { canOpenFeature, featureById, featureHref, pathLine } from "../feature-links";
import type { NavCard } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { HelperCardFrame } from "./frame";

/** Actions that make sense as "Burada yap" with no arguments (a read, or a write that answers its form). */
const DO_HERE = ["find_free_rooms", "create_booking", "my_bookings", "my_requests_status", "approvals_inbox", "run_status", "requests_needing_review", "my_ai_usage"];

const HANDOVER_LABEL: Record<string, "helper.where.calendar" | "helper.where.invite"> = {
  "profile.calendar": "helper.where.calendar",
  "admin.users.invite": "helper.where.invite",
};

export function NavView({ card, compact = false }: { card: NavCard; compact?: boolean }) {
  const { t } = useI18n();
  const host = useCardHost();
  const [steps, setSteps] = useState(false);
  const entry = featureById(card.feature_id);
  const href = featureHref(card.feature_id);
  if (!entry || !href || !canOpenFeature(entry, host.can)) return null;
  const title = pickText(card.title, host.locale) || pickText(entry.title, host.locale);
  const path = pathLine(card.path, host.locale) || pathLine(entry.path, host.locale);
  const stepList = (host.locale === "en" ? card.steps?.en : card.steps?.tr) ?? [];
  const anchor = card.anchor ?? entry.anchor;
  const doHere = (card.actions ?? []).find((a) => DO_HERE.includes(a) && (!host.actions || host.actions.has(a)));
  const openLabel = HANDOVER_LABEL[card.feature_id] ? t(HANDOVER_LABEL[card.feature_id]!) : t("helper.where.open");
  return (
    <HelperCardFrame
      testId={`helper-card-nav${card.action ? `-${card.action}` : ""}`}
      title={
        <span className="inline-flex items-center gap-2">
          <MapPin aria-hidden className="size-4 shrink-0 text-label-2" />
          {title}
        </span>
      }
      className={cn(compact && "p-3")}
      actions={
        <>
          {anchor ? (
            <Button size="md" onClick={() => host.showMe(card.feature_id)} data-testid="helper-show" aria-label={`${t("helper.where.show")}: ${title}`}>
              {t("helper.where.show")}
            </Button>
          ) : null}
          <Button size="md" variant={anchor ? "secondary" : "default"} onClick={() => host.go(href)} data-testid="helper-card-secondary">
            {openLabel}
          </Button>
          {doHere ? (
            <Button size="md" variant="secondary" onClick={() => void host.runner.runAction(doHere, {})} data-testid="helper-do-here">
              {t("helper.where.doHere")}
            </Button>
          ) : null}
        </>
      }
    >
      {path ? <p className="type-callout text-label-2" data-testid="helper-where-path">{path}</p> : null}
      {stepList.length ? (
        <div>
          <Button variant="ghost" size="sm" aria-expanded={steps} onClick={() => setSteps((v) => !v)} className="-ml-2 gap-1 text-label-2">
            <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast)", steps && "rotate-180")} />
            {t("helper.where.steps")}
          </Button>
          {steps ? (
            <ol className="mt-1 list-decimal space-y-1 pl-5 type-callout text-label-1">
              {stepList.slice(0, 3).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}
    </HelperCardFrame>
  );
}
