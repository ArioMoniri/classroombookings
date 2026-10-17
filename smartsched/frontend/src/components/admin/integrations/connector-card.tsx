"use client";
/**
 * One connector of the integrations gallery (docs/design/v3/integrations.md §4.1): monogram, name, one-line summary,
 * status dot + word (never colour alone), last check (relative, absolute in the tooltip), "Son değişiklik: <ad>,
 * <zaman>", the primary action (Kur / Yönet / Yönet ↗ for a screen owned elsewhere) and the "Kullanımda" switch once
 * configured. Error cards get a 2 px infeasible edge and their first error line. Planning admins without
 * `setup.settings` see "Yalnız görüntüleme" instead of actions and switches.
 *
 * Phones (§11): a 64 px row (monogram, name, status word, chevron) that opens the setup sheet; the switch lives in
 * the sheet, so a row tap never toggles by accident.
 */
import { ChevronRight } from "lucide-react";
import { forwardRef, useId } from "react";
import { BareButton, Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { CardStatus, ConnectorCard } from "@/lib/api/integrations";
import { intlLocale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { monogram, primaryAction, relativeTime, switchState } from "./integrations-model";

/** dot shape per status: filled, hollow, dashed (spec §4.1 "StatusDot + word") */
const DOT: Record<CardStatus, string> = {
  connected: "bg-status-feasible-solid",
  error: "bg-status-infeasible-solid",
  disabled: "bg-label-3",
  not_configured: "border-[1.5px] border-label-2 bg-transparent",
  unknown: "border-[1.5px] border-dashed border-label-2 bg-transparent",
};

export function useWhen() {
  const { locale } = useI18n();
  return (iso: string | null | undefined) => {
    if (!iso) return "–";
    const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(intlLocale(locale), { dateStyle: "medium", timeStyle: "short" });
  };
}

export function StatusPill({ status, className }: { status: CardStatus; className?: string }) {
  const { t } = useI18n();
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 type-footnote font-medium text-label-1", className)} data-testid="connector-status" data-status={status}>
      <span aria-hidden className={cn("inline-block size-2.5 rounded-full", DOT[status])} />
      {t(`integrations.status.${status}` as MessageKey)}
    </span>
  );
}

export function cardName(card: Pick<ConnectorCard, "name_tr" | "name_en">, locale: string) {
  return locale === "tr" ? card.name_tr : card.name_en;
}

/** A card managed on another screen (only /admin/ai today) opens it instead of the setup sheet. */
export function isExternal(card: Pick<ConnectorCard, "setup_href">): boolean {
  return !card.setup_href.startsWith("/admin/integrations");
}

export function Monogram({ card, className }: { card: Pick<ConnectorCard, "key" | "name_en">; className?: string }) {
  return (
    <span aria-hidden className={cn("grid size-10 shrink-0 place-items-center rounded-xl bg-fill-2 hairline type-caption font-bold text-label-1", className)}>
      {monogram(card)}
    </span>
  );
}

export function useCardLines(card: ConnectorCard) {
  const { t, locale } = useI18n();
  const when = useWhen();
  const tag = intlLocale(locale);
  const check = card.last_check_at
    ? t("integrations.card.lastCheck", { when: relativeTime(card.last_check_at, tag), result: t(card.last_check_ok === false ? "integrations.card.lastCheckFail" : "integrations.card.lastCheckOk") })
    : card.status === "not_configured"
      ? t("integrations.card.neverChecked")
      : t("integrations.card.notTested");
  const change = card.changed_at
    ? card.changed_by
      ? t("integrations.card.lastChange", { who: card.changed_by, when: when(card.changed_at) })
      : t("integrations.card.lastChangeWhen", { when: when(card.changed_at) })
    : t("integrations.card.noChange");
  return { check, checkTitle: card.last_check_at ? when(card.last_check_at) : undefined, change };
}

interface Props {
  card: ConnectorCard;
  busy?: boolean;
  canEdit: boolean;
  /** phone layout: a 64 px row */
  row?: boolean;
  onPrimary: (card: ConnectorCard) => void;
  onSwitch: (card: ConnectorCard, next: boolean) => void;
}

export const ConnectorCardView = forwardRef<HTMLButtonElement, Props>(function ConnectorCardView({ card, busy, canEdit, row, onPrimary, onSwitch }, ref) {
  const { t, locale } = useI18n();
  const tr = locale === "tr";
  const name = cardName(card, locale);
  const summary = tr ? card.summary_tr : card.summary_en;
  const detail = tr ? card.detail_tr : card.detail_en;
  const sw = switchState(card);
  const ext = isExternal(card);
  const action = ext ? "open" : primaryAction(card);
  const headingId = useId();
  const switchHint = useId();
  const lines = useCardLines(card);
  const statusWord = t(`integrations.status.${card.status}` as MessageKey);

  if (row) {
    return (
      <BareButton
        ref={ref}
        onClick={() => onPrimary(card)}
        className={cn("flex min-h-16 w-full items-center gap-3 rounded-2xl bg-(--mat-thick) px-3 py-2 text-left shadow-(--edge-control)", card.status === "error" && "ring-2 ring-status-infeasible-solid")}
        data-status={card.status}
        data-testid={`connector-${card.key}`}
        aria-label={t("integrations.card.rowName", { name, status: statusWord })}
      >
        <Monogram card={card} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate type-headline text-label-1">{name}</span>
          <StatusPill status={card.status} />
        </span>
        <ChevronRight aria-hidden className="size-4 shrink-0 text-label-3" />
      </BareButton>
    );
  }

  const reason = !canEdit || !card.toggle ? null : card.toggle.enable_in_setup && !sw.checked ? t("integrations.switch.enableInSetup") : null;
  return (
    <article
      className={cn("flex h-full flex-col gap-2 rounded-2xl bg-(--mat-thick) px-4 py-4 shadow-(--edge-control)", card.status === "error" && "ring-2 ring-status-infeasible-solid")}
      data-testid={`connector-${card.key}`}
      data-status={card.status}
      aria-labelledby={headingId}
    >
      <div className="flex items-start gap-3">
        <Monogram card={card} />
        <div className="min-w-0 flex-1">
          <h3 id={headingId} className="type-headline text-label-1">
            {name}
          </h3>
          <p className="truncate type-footnote text-label-2" title={summary}>
            {summary}
          </p>
        </div>
      </div>
      <StatusPill status={card.status} />
      {detail ? <p className={cn("type-footnote", card.status === "error" ? "text-status-infeasible-fg" : "text-label-2")}>{detail}</p> : null}
      <div className="mt-auto grid gap-0.5 type-footnote text-label-2">
        <p data-testid="connector-check" title={lines.checkTitle}>
          {lines.check}
        </p>
        <p data-testid="connector-change">{lines.change}</p>
      </div>
      {canEdit ? (
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <Button
            ref={ref}
            size="md"
            variant={action === "setup" ? "default" : "outline"}
            onClick={() => onPrimary(card)}
            aria-label={action === "open" ? t("integrations.card.openFor", { name, screen: t("integrations.screen.ai") }) : t(action === "setup" ? "integrations.card.setupFor" : "integrations.card.editFor", { name })}
            className="pointer-coarse:min-h-11"
            data-testid="connector-primary"
          >
            {t(action === "setup" ? "integrations.card.setup" : action === "edit" ? "integrations.card.edit" : "integrations.card.open")}
          </Button>
          {card.toggle ? (
            <label className="flex items-center gap-2 type-footnote text-label-2 pointer-coarse:min-h-11">
              <span aria-hidden>{t("integrations.card.inUse")}</span>
              <Switch checked={sw.checked} disabled={busy} onCheckedChange={(next) => onSwitch(card, next)} aria-label={t("integrations.card.switchLabel", { name })} aria-describedby={reason ? switchHint : undefined} data-testid="connector-switch" />
            </label>
          ) : null}
        </div>
      ) : (
        <p className="pt-1 type-footnote text-label-3" data-testid="connector-readonly">
          {t("integrations.readOnly")}
        </p>
      )}
      {reason ? (
        <p id={switchHint} className="type-caption text-label-3">
          {reason}
        </p>
      ) : null}
    </article>
  );
});
