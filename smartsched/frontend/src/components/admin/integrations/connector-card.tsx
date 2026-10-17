"use client";
/**
 * One connector of the integrations gallery: name, what it does (one sentence), status pill (word + glyph, never
 * colour alone), last check, last change (who, when), the primary action ("Kur" / "Düzenle") and the switch.
 * The switch calls the owning area's endpoint (`card.toggle`); switching off asks first (organisation-wide).
 */
import { AlertTriangle, CheckCircle2, CircleDashed, CircleOff, HelpCircle } from "lucide-react";
import { forwardRef, useId } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { CardStatus, ConnectorCard } from "@/lib/api/integrations";
import { intlLocale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { TONE, primaryAction, switchState } from "./integrations-model";

const GLYPH: Record<CardStatus, typeof CheckCircle2> = {
  connected: CheckCircle2,
  error: AlertTriangle,
  not_configured: CircleDashed,
  disabled: CircleOff,
  unknown: HelpCircle,
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
  const Icon = GLYPH[status];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 type-caption font-medium", TONE[status], className)} data-testid="connector-status" data-status={status}>
      <Icon aria-hidden className="size-3.5" />
      {t(`integrations.status.${status}` as MessageKey)}
    </span>
  );
}

export function cardName(card: Pick<ConnectorCard, "name_tr" | "name_en">, locale: string) {
  return locale === "tr" ? card.name_tr : card.name_en;
}

interface Props {
  card: ConnectorCard;
  busy?: boolean;
  onPrimary: (card: ConnectorCard) => void;
  onSwitch: (card: ConnectorCard, next: boolean) => void;
}

export const ConnectorCardView = forwardRef<HTMLButtonElement, Props>(function ConnectorCardView({ card, busy, onPrimary, onSwitch }, ref) {
  const { t, locale } = useI18n();
  const when = useWhen();
  const tr = locale === "tr";
  const name = cardName(card, locale);
  const summary = tr ? card.summary_tr : card.summary_en;
  const detail = tr ? card.detail_tr : card.detail_en;
  const sw = switchState(card);
  const action = card.setup_href.startsWith("/admin/integrations") ? primaryAction(card) : "open";
  const headingId = useId();
  const switchHint = useId();
  const check = card.last_check_at
    ? t("integrations.card.lastCheck", { when: when(card.last_check_at), result: t(card.last_check_ok === false ? "integrations.card.lastCheckFail" : "integrations.card.lastCheckOk") })
    : t("integrations.card.neverChecked");
  const change = card.changed_at
    ? card.changed_by
      ? t("integrations.card.lastChange", { who: card.changed_by, when: when(card.changed_at) })
      : t("integrations.card.lastChangeWhen", { when: when(card.changed_at) })
    : t("integrations.card.noChange");
  const reason = sw.reason ? t(`integrations.switch.${sw.reason}` as MessageKey) : card.toggle?.enable_in_setup && !sw.checked ? t("integrations.switch.enableInSetup") : null;
  return (
    <Card className="h-full gap-2 px-4 py-4" data-testid={`connector-${card.key}`} data-status={card.status} aria-labelledby={headingId} role="group">
      <div className="flex items-start justify-between gap-2">
        <h3 id={headingId} className="type-headline text-label-1">
          {name}
        </h3>
        <StatusPill status={card.status} />
      </div>
      <p className="type-callout text-label-1">{summary}</p>
      {detail ? <p className={cn("type-footnote", card.status === "error" ? "text-status-infeasible-fg" : "text-label-2")}>{detail}</p> : null}
      <div className="mt-auto grid gap-0.5 type-footnote text-label-2">
        <p data-testid="connector-check">{check}</p>
        <p data-testid="connector-change">{change}</p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <Button ref={ref} size="md" variant={action === "setup" ? "default" : "outline"} onClick={() => onPrimary(card)} aria-label={t(action === "setup" ? "integrations.card.setupFor" : action === "edit" ? "integrations.card.editFor" : "integrations.card.openFor", { name })} className="pointer-coarse:min-h-11" data-testid="connector-primary">
          {t(action === "setup" ? "integrations.card.setup" : action === "edit" ? "integrations.card.edit" : "integrations.card.open")}
        </Button>
        <label className={cn("flex items-center gap-2 type-footnote text-label-2 pointer-coarse:min-h-11", sw.disabled && "opacity-70")}>
          <span aria-hidden>{t(sw.checked ? "integrations.card.on" : "integrations.card.off")}</span>
          <Switch
            checked={sw.checked}
            disabled={sw.disabled || busy}
            onCheckedChange={(next) => onSwitch(card, next)}
            aria-label={t("integrations.card.switchLabel", { name })}
            aria-describedby={reason ? switchHint : undefined}
            data-testid="connector-switch"
          />
        </label>
      </div>
      {reason ? (
        <p id={switchHint} className="type-caption text-label-3">
          {reason}
        </p>
      ) : null}
    </Card>
  );
});
