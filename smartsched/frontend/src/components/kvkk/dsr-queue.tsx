"use client";
/**
 * Yönetim › KVKK › Talepler (`setup.users`): the data-subject requests (erase, rectify, info; exports are
 * self-service) with their legal deadline — overdue in red, the last week in amber, days left on every open request.
 * Filters: open (default), done, refused, all (`status=all`). Complete (with an optional note) or refuse (a written reason is required). Completing an erasure anonymises the
 * person across the system; the answer's counts are shown, with why it is "partial" (audit records are kept,
 * pseudonymised, for the legal retention). 409 `own_request | last_admin | closed | gone` is shown in the dialog.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Textarea } from "@/components/ui/textarea";
import { dueTone, erasureCounts, useDecideDsr, useDsrQueue, type Dsr, type QueueFilter } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { STATUS_TONE, useDateTime } from "@/components/privacy/privacy-section";

/** the queue's filters → `GET /admin/dsr?status=` (`open` = OPEN + IN_PROGRESS, `all` = every queued request) */
const FILTERS = ["open", "done", "refused", "all"] as const;
type Filter = (typeof FILTERS)[number];
const STATUS_PARAM: Record<Filter, QueueFilter> = { open: "open", done: "DONE", refused: "REFUSED", all: "all" };

/** erasure count keys the backend returns → words; anything else shows the table name */
const COUNT_KEYS: Record<string, MessageKey> = {
  bookings_cancelled: "kvkk.dsr.count.bookings_cancelled",
  bookings_anonymised: "kvkk.dsr.count.bookings_anonymised",
  series_anonymised: "kvkk.dsr.count.series_anonymised",
  inapp_notifications: "kvkk.dsr.count.inapp_notifications",
  notification_deliveries: "kvkk.dsr.count.notification_deliveries",
  notification_outbox: "kvkk.dsr.count.notification_outbox",
  user_channels: "kvkk.dsr.count.user_channels",
  user_identities: "kvkk.dsr.count.user_identities",
  calendar_feed_tokens: "kvkk.dsr.count.calendar_feed_tokens",
  calendar_connections: "kvkk.dsr.count.calendar_connections",
  consents: "kvkk.dsr.count.consents",
  learning: "kvkk.dsr.count.learning",
  audit_pseudonymised: "kvkk.dsr.count.audit_pseudonymised",
  audit_account_rows: "kvkk.dsr.count.audit_account_rows",
  audit_booking_rows: "kvkk.dsr.count.audit_booking_rows",
};

export function DsrQueue() {
  const { t, locale } = useI18n();
  const [filter, setFilter] = useState<Filter>("open");
  const q = useDsrQueue(STATUS_PARAM[filter]);
  const decide = useDecideDsr();
  const when = useDateTime();
  const [acting, setActing] = useState<{ r: Dsr; refuse: boolean } | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Dsr | null>(null);
  const rows = q.data ?? [];

  const start = (r: Dsr, refuse: boolean) => {
    setText("");
    setError(null);
    setActing({ r, refuse });
  };
  const submit = () => {
    if (!acting) return;
    if (acting.refuse && text.trim().length < 3) return setError(t("kvkk.dsr.reasonRequired"));
    decide.mutate(
      { id: acting.r.id, refuse: acting.refuse, text: text.trim() || null },
      {
        onSuccess: (res) => {
          setActing(null);
          setDone(res.kind === "erase" && res.status === "DONE" ? res : null);
          toast.success(acting.refuse ? t("kvkk.dsr.refused") : t("kvkk.dsr.completed"));
        },
        onError: (e) => setError(errorText(wave1Error(e), locale)),
      },
    );
  };

  return (
    <div className="flex flex-col gap-4" data-testid="dsr-queue">
      <p className="type-callout text-label-2">{t("kvkk.dsr.lead")}</p>
      <SegmentedControl aria-label={t("kvkk.dsr.filter")} value={filter} onValueChange={(v) => setFilter(v as Filter)} options={FILTERS.map((f) => ({ value: f, label: t(`kvkk.dsr.filters.${f}` as MessageKey), testId: `dsr-filter-${f}` }))} />
      {done ? <ErasureResult r={done} onClose={() => setDone(null)} /> : null}
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {q.isSuccess && !rows.length ? <p className="rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="dsr-empty">{t(`kvkk.dsr.empty.${filter}` as MessageKey)}</p> : null}
      <ul className="flex flex-col gap-2">
        {rows.map((r) => {
          const tone = dueTone(r);
          return (
            <li key={r.id}>
              <Card className={cn("gap-2 px-4 py-3", tone === "overdue" && "edge-control")} data-testid={`dsr-${r.id}`} data-due={tone}>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="type-headline text-label-1">{t(`privacy.request.kinds.${r.kind}` as MessageKey)}</p>
                  <span className={cn("rounded-full px-2 type-caption", STATUS_TONE[r.status] ?? "bg-fill-2 text-label-2")}>{t(`privacy.status.${r.status}` as MessageKey)}</span>
                  {tone !== "closed" ? (
                    <span className={cn("rounded-full px-2 type-caption font-medium", tone === "overdue" ? "bg-status-infeasible text-status-infeasible-fg" : tone === "soon" ? "bg-status-warning text-status-warning-fg" : "bg-fill-2 text-label-2")} data-testid={`dsr-days-${r.id}`}>
                      {tone === "overdue" ? t("kvkk.dsr.overdue", { n: Math.abs(r.days_left ?? 0) }) : t("kvkk.dsr.daysLeft", { n: r.days_left ?? 0 })}
                    </span>
                  ) : null}
                </div>
                <p className="type-callout text-label-1">{r.subject ?? t("kvkk.dsr.unknownSubject")}</p>
                <p className="type-footnote text-label-2">
                  {t("privacy.request.created", { date: when(r.created_at) })}
                  {r.due_at ? ` · ${t("kvkk.dsr.dueOn", { date: when(r.due_at) })}` : ""}
                  {r.handled_at ? ` · ${t("kvkk.dsr.handledOn", { date: when(r.handled_at) })}` : ""}
                </p>
                {r.note ? <p className="rounded-md bg-fill-3 px-2.5 py-1.5 type-callout text-label-1">{r.note}</p> : null}
                {r.refusal_reason ? <p className="type-footnote text-label-1">{t("privacy.request.refusal", { reason: r.refusal_reason })}</p> : null}
                {r.status === "DONE" && r.kind === "erase" && erasureCounts(r.result).length ? (
                  <Button variant="link" size="sm" className="self-start" onClick={() => setDone(r)}>
                    {t("kvkk.dsr.showResult")}
                  </Button>
                ) : null}
                {r.status === "OPEN" || r.status === "IN_PROGRESS" ? (
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" className="pointer-coarse:min-h-11" onClick={() => start(r, false)} data-testid={`dsr-complete-${r.id}`}>
                      {r.kind === "erase" ? t("kvkk.dsr.erase") : t("kvkk.dsr.complete")}
                    </Button>
                    <Button size="sm" variant="outline" className="pointer-coarse:min-h-11" onClick={() => start(r, true)} data-testid={`dsr-refuse-${r.id}`}>
                      {t("kvkk.dsr.refuse")}
                    </Button>
                  </div>
                ) : null}
              </Card>
            </li>
          );
        })}
      </ul>

      <ResponsiveDialog
        open={!!acting}
        onOpenChange={(o) => !o && !decide.isPending && setActing(null)}
        title={acting ? (acting.refuse ? t("kvkk.dsr.refuseTitle") : acting.r.kind === "erase" ? t("kvkk.dsr.eraseTitle", { who: acting.r.subject ?? "" }) : t("kvkk.dsr.completeTitle")) : ""}
        description={acting ? (acting.refuse ? t("kvkk.dsr.refuseLead") : acting.r.kind === "erase" ? t("kvkk.dsr.eraseLead") : t("kvkk.dsr.completeLead")) : undefined}
        role="alertdialog"
        testId="dsr-dialog"
        footer={
          <>
            <Button variant="ghost" onClick={() => setActing(null)} disabled={decide.isPending}>
              {t("crbs.common.cancel")}
            </Button>
            <Button variant={acting?.r.kind === "erase" && !acting.refuse ? "destructive" : "default"} onClick={submit} {...busyProps(decide.isPending)} data-testid="dsr-confirm">
              <BusyLabel busy={decide.isPending} label={t("busy.saving")}>
                {acting?.refuse ? t("kvkk.dsr.refuse") : acting?.r.kind === "erase" ? t("kvkk.dsr.eraseConfirm") : t("kvkk.dsr.complete")}
              </BusyLabel>
            </Button>
          </>
        }
      >
        {acting?.r.note ? <p className="rounded-md bg-fill-3 px-2.5 py-1.5 type-callout text-label-1">{acting.r.note}</p> : null}
        <Field label={acting?.refuse ? t("kvkk.dsr.reason") : t("kvkk.dsr.note")} htmlFor="dsr-text" hint={acting?.refuse ? t("kvkk.dsr.reasonHint") : t("kvkk.dsr.noteHint")}>
          <Textarea id="dsr-text" rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} data-testid="dsr-text" />
        </Field>
        {error ? <Alert tone="error" testId="dsr-error">{error}</Alert> : null}
      </ResponsiveDialog>
    </div>
  );
}

function ErasureResult({ r, onClose }: { r: Dsr; onClose: () => void }) {
  const { t } = useI18n();
  const counts = erasureCounts(r.result).filter((c) => c.n > 0);
  return (
    <Alert tone="success" title={t("kvkk.dsr.resultTitle", { who: r.subject ?? "" })} testId="dsr-result" action={<Button size="sm" variant="ghost" onClick={onClose}>{t("common.close")}</Button>}>
      {counts.length ? (
        <ul className="mt-1 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
          {counts.map((c) => (
            <li key={c.key}>
              <span className="font-semibold tabular-nums">{c.n}</span> {COUNT_KEYS[c.key] ? t(COUNT_KEYS[c.key]!) : <span className="font-mono">{c.key}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("kvkk.dsr.nothingStored")}</p>
      )}
      <p className="mt-2 type-footnote" data-testid="dsr-partial">{t("kvkk.dsr.partial")}</p>
    </Alert>
  );
}
