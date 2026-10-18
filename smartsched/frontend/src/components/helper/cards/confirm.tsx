"use client";
/**
 * HX-04 / HX-05 (helper.md §4.1 rules 4–7, §4.6): the `confirm` card — the server's preview of one write. The card is
 * the confirmation: one primary button names the effect and the object ("Rezerve et: A 204 · yarın 10:00"); only a
 * trusted click or key on it sends the token. R2 names who is affected. "Değiştir" turns a booking into its form;
 * "Vazgeç" drops it. An expired token reads "Bu öneri eskidi." with "Yenile"; an older pending card is parked as one
 * line ("Rezervasyon · bekliyor", "· eskidi" once its token timed out). While the token is sent the button is
 * `aria-disabled` (it keeps the focus); after "Vazgeç" the focus goes to the "Vazgeçildi." line (HX-18 M2, M6).
 */
import { AlertTriangle, Clock } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { useHelperStore, type CardEntry } from "../helper-store";
import type { ConfirmCard } from "../schema.gen";
import { focusEntry } from "../use-helper-runner";
import { pickText, useCardHost } from "./context";
import { formFromConfirm } from "./form";
import { CancelledLine, CardLine, HelperCardFrame } from "./frame";

function useExpired(expiresAt: string): boolean {
  const at = Date.parse(expiresAt);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!Number.isFinite(at) || at <= now) return;
    const id = window.setTimeout(() => setNow(Date.now()), Math.min(at - now + 50, 2 ** 31 - 1));
    return () => window.clearTimeout(id);
  }, [at, now]);
  return Number.isFinite(at) && at <= now;
}

export function ConfirmView({ card, entry }: { card: ConfirmCard; entry: CardEntry }) {
  const { t } = useI18n();
  const host = useCardHost();
  const timedOut = useExpired(card.expires_at);
  // HX-18 M6: a parked card that timed out stays one line; only the card in focus offers "Yenile"
  const expired = entry.phase === "expired" || (timedOut && entry.phase === "pending");
  const title = card.title ? pickText(card.title, host.locale) : host.actionVerb(card.action) ?? t("helper.card.proposal");
  const testId = `helper-card-confirm-${card.action}`;

  if (entry.phase === "parked" && !expired) {
    return (
      <p data-testid={testId} data-phase="parked" className="flex items-center gap-2 rounded-(--radius-md) bg-fill-3 px-4 py-2 type-callout text-label-2 edge-hairline">
        <Clock aria-hidden className="size-4 shrink-0" />
        {t("helper.card.pending", { title })}
        {timedOut ? ` · ${t("helper.card.stale")}` : null}
      </p>
    );
  }
  const form = formFromConfirm(card);
  const open = entry.phase === "pending" && !expired;
  const busy = entry.phase === "busy";
  return (
    <HelperCardFrame
      testId={testId}
      title={title}
      tone={entry.phase === "cancelled" ? "muted" : "default"}
      actions={
        expired ? (
          <Button size="md" onClick={() => void host.runner.refresh(entry)} data-testid="helper-card-refresh">
            {t("helper.card.refresh")}
          </Button>
        ) : open || busy ? (
          <>
            <Button
              size="md"
              variant={card.danger ? "destructive" : "default"}
              className="max-sm:h-12 whitespace-normal"
              aria-busy={busy || undefined}
              // HX-18 M2: aria-disabled, not disabled, so the focus stays on the button while the result comes
              aria-disabled={busy || undefined}
              onClick={(e) => {
                if (busy) return;
                void host.runner.confirm(entry, e);
              }}
              data-testid="helper-card-confirm"
            >
              {busy ? t("busy.saving") : pickText(card.button, host.locale)}
            </Button>
            {form && !busy ? (
              <Button size="md" variant="secondary" onClick={() => focusEntry(useHelperStore.getState().pushCard(form, { hints: entry.hints }))} data-testid="helper-card-change">
                {t("helper.card.change")}
              </Button>
            ) : null}
            {!busy ? (
              <Button size="md" variant="ghost" onClick={() => host.runner.cancel(entry)} data-testid="helper-card-cancel">
                {t("helper.card.cancel")}
              </Button>
            ) : null}
          </>
        ) : undefined
      }
    >
      <dl className="flex flex-col gap-1.5">
        {card.preview.map((p, i) => (
          <CardLine key={i} label={pickText(p.label, host.locale)} value={pickText(p.value, host.locale)} />
        ))}
      </dl>
      {card.affected ? (
        <p className="flex items-start gap-2 type-callout text-label-1" data-testid="helper-card-affected">
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-status-warning-fg" />
          <span>
            <span className="font-medium">{t("helper.card.affected")}</span> {pickText(card.affected, host.locale)}
          </span>
        </p>
      ) : null}
      {card.warnings?.length ? (
        <ul className="flex flex-col gap-1 type-footnote text-status-warning-fg">
          {card.warnings.map((w, i) => (
            <li key={i}>{pickText(w, host.locale)}</li>
          ))}
        </ul>
      ) : null}
      {expired ? <p className="type-callout text-label-2" data-testid="helper-card-expired">{t("helper.card.expired")}</p> : null}
      {entry.phase === "cancelled" ? <CancelledLine /> : null}
      {entry.phase === "done" ? <p className="type-footnote text-label-3">{t("helper.card.done")}</p> : null}
      {entry.notice ? (
        <Alert tone="warning" data-testid="helper-card-error">
          {pickText(entry.notice, host.locale)}
        </Alert>
      ) : null}
    </HelperCardFrame>
  );
}
