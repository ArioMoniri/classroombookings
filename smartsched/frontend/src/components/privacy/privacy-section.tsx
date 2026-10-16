"use client";
/**
 * Profil › Gizlilik (A4 KVKK; `GET /me/privacy`): the institution's current privacy notice with the acknowledgement,
 * the consents with what withdrawing each one does (it applies at once: SMS deletes the linked phone numbers, photo the
 * stored photo, calendar sync revokes the feed links and disconnects the calendars — each confirmed first —, AI keeps the
 * person's data out of later AI requests; the toast shows the server's `effects[]` sentences), and the
 * data requests (KVKK Art. 11): a self-service export (a zip built at download time, 7 days), and erasure,
 * rectification or information requests that the administrators answer within the legal deadline.
 *
 * The AI consent's text follows the institution's `kvkk.ai_personal_default` and the person's own state
 * (`GET /me/privacy` `ai_personal_default`, `ai_excluded`; consent gates 2026-10-16): it says whether their name and
 * e-mail are kept out of AI requests right now and why (they withdrew; never given while "not granted = excluded";
 * given; or included until withdrawn), see `aiConsentText`.
 *
 * No notice text ships with SmartSched: until an administrator publishes one, the section says so plainly.
 */
import { Download, FileText, ShieldCheck } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog, Field, SectionTitle } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { downloadExport, dueTone, effectSentences, KINDS, useAckNotice, useConsent, useCreateDataRequest, useMyPrivacy, type Consent, type Dsr, type DsrKind, type Purpose } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { intlLocale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Markdown } from "./markdown";

export function useDateTime() {
  const { locale } = useI18n();
  return (iso: string | null | undefined, withTime = false) => {
    if (!iso) return "";
    const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(intlLocale(locale), withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
  };
}

export function PrivacySection() {
  const { t, locale } = useI18n();
  const q = useMyPrivacy();
  return (
    <section aria-labelledby="pf-privacy" id="privacy" className="scroll-mt-20" data-testid="privacy-section">
      <SectionTitle id="pf-privacy">{t("privacy.title")}</SectionTitle>
      <div className="flex flex-col gap-4">
        {q.isLoading ? <Skeleton className="h-32 rounded-xl" /> : null}
        {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
        {q.data ? (
          <>
            <NoticeCard notice={q.data.notice ?? null} needsAck={q.data.needs_ack} />
            <ConsentsCard consents={q.data.consents} aiDefault={q.data.ai_personal_default} aiExcluded={q.data.ai_excluded} />
            <RequestsCard requests={q.data.requests} dueDays={q.data.due_days} />
          </>
        ) : null}
      </div>
    </section>
  );
}

function NoticeCard({ notice, needsAck }: { notice: { id: number; version: number; title: string; body_md: string; published_at?: string | null } | null; needsAck: boolean }) {
  const { t, locale } = useI18n();
  const ack = useAckNotice();
  const when = useDateTime();
  const [open, setOpen] = useState(needsAck);
  if (!notice)
    return (
      <Card variant="glass" className="gap-2 px-4" data-testid="privacy-no-notice">
        <p className="flex items-center gap-2 type-headline text-label-1">
          <FileText className="size-4 text-label-3" aria-hidden />
          {t("privacy.notice.title")}
        </p>
        <p className="type-callout text-label-2">{t("privacy.notice.none")}</p>
      </Card>
    );
  return (
    <Card variant="glass" className="gap-3 px-4" data-testid="privacy-notice">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="type-headline text-label-1">{notice.title}</p>
          <p className="type-footnote text-label-3">{t("privacy.notice.version", { v: notice.version, date: when(notice.published_at) })}</p>
        </div>
        {needsAck ? (
          <span className="rounded-full bg-status-warning px-2 py-0.5 type-caption text-status-warning-fg">{t("privacy.notice.unread")}</span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-status-feasible px-2 py-0.5 type-caption text-status-feasible-fg" data-testid="privacy-acked">
            <ShieldCheck className="size-3" aria-hidden />
            {t("privacy.notice.read")}
          </span>
        )}
      </div>
      {open ? <Markdown source={notice.body_md} className="max-h-[50vh] overflow-y-auto rounded-lg bg-fill-3 p-3 type-callout text-label-1" /> : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" className="pointer-coarse:min-h-11" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? t("privacy.notice.hide") : t("privacy.notice.show")}
        </Button>
        {needsAck ? (
          <Button size="sm" className="pointer-coarse:min-h-11" onClick={() => ack.mutate(notice.id, { onSuccess: () => toast.success(t("privacy.notice.acked")), onError: (e) => toast.error(errorText(wave1Error(e), locale)) })} {...busyProps(ack.isPending)} data-testid="privacy-ack">
            <BusyLabel busy={ack.isPending} label={t("busy.saving")}>
              {t("privacy.notice.ack")}
            </BusyLabel>
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

const CONSEQUENCE: Record<Purpose, MessageKey> = {
  sms: "privacy.consent.consequence.sms",
  photo: "privacy.consent.consequence.photo",
  calendar_sync: "privacy.consent.consequence.calendar_sync",
  ai_personal: "privacy.consent.consequence.ai_personal",
};

/** The ai_personal row: is the person kept out of AI requests now (the server's `ai_excluded`), and why. */
export function aiConsentText(c: Pick<Consent, "granted" | "withdrawn_at"> | undefined, aiDefault: "included" | "excluded", aiExcluded: boolean): { out: boolean; key: MessageKey } {
  if (aiExcluded) return { out: true, key: !c?.granted && c?.withdrawn_at ? "privacy.ai.excludedWithdrawn" : aiDefault === "excluded" ? "privacy.ai.excludedDefault" : "privacy.ai.excludedWithdrawn" };
  return { out: false, key: aiDefault === "excluded" ? "privacy.ai.includedConsent" : "privacy.ai.includedDefault" };
}

/** Withdrawals that delete something at once are confirmed first; `ai_personal` only changes what is sent from now on. */
const CONFIRM: Partial<Record<Purpose, { title: MessageKey; body: MessageKey; confirm: MessageKey }>> = {
  sms: { title: "privacy.consent.smsTitle", body: "privacy.consent.smsBody", confirm: "privacy.consent.smsConfirm" },
  photo: { title: "privacy.consent.photoTitle", body: "privacy.consent.photoBody", confirm: "privacy.consent.photoConfirm" },
  calendar_sync: { title: "privacy.consent.calendarTitle", body: "privacy.consent.calendarBody", confirm: "privacy.consent.calendarConfirm" },
};

function ConsentsCard({ consents, aiDefault, aiExcluded }: { consents: Consent[]; aiDefault: "included" | "excluded"; aiExcluded: boolean }) {
  const { t, locale } = useI18n();
  const m = useConsent();
  const when = useDateTime();
  // the dialog keeps its last consent while it closes, so the text does not blank out during the exit animation
  const [confirm, setConfirm] = useState<Consent | null>(null);
  const [open, setOpen] = useState(false);
  const ask = confirm ? CONFIRM[confirm.purpose as Purpose] : undefined;
  const run = (c: Consent, grant: boolean) =>
    m.mutate(
      { purpose: c.purpose as Purpose, grant },
      {
        onSuccess: (res) => {
          setOpen(false);
          if (grant || !res) return void toast.success(t("privacy.consent.granted"));
          // the server says what the withdrawal did (phones / photo deleted, feeds revoked, AI placeholders)
          const lines = effectSentences(res.effects, locale);
          toast.success(t("privacy.consent.withdrawn"), lines.length ? { description: lines.join(" "), duration: 8000 } : undefined);
        },
        onError: (e) => toast.error(errorText(wave1Error(e), locale)),
      },
    );
  return (
    <Card variant="glass" className="gap-1 px-4" data-testid="privacy-consents">
      <p className="type-headline text-label-1">{t("privacy.consent.title")}</p>
      <p className="type-callout text-label-2">{t("privacy.consent.lead")}</p>
      <ul className="mt-1 flex flex-col">
        {consents.map((c) => {
          const id = `consent-${c.purpose}`;
          const purpose = c.purpose as Purpose;
          const ai = purpose === "ai_personal" ? aiConsentText(c, aiDefault, aiExcluded) : null;
          return (
            <li key={c.purpose} className="flex items-start justify-between gap-4 py-3 not-last:edge-hairline-b" data-testid={`consent-${c.purpose}`}>
              <div className="min-w-0">
                <label htmlFor={id} className="type-callout font-medium text-label-1">
                  {locale === "tr" ? c.label_tr : c.label_en}
                </label>
                {ai ? (
                  <>
                    <p className={cn("mt-1 flex w-fit rounded-md px-2 py-0.5 type-caption font-medium", ai.out ? "bg-status-warning text-status-warning-fg" : "bg-fill-2 text-label-2")} data-testid="consent-ai-state" data-excluded={ai.out}>
                      {ai.out ? t("privacy.ai.stateOut") : t("privacy.ai.stateIn")}
                    </p>
                    <p className="type-footnote text-label-2" data-testid="consent-ai-text">{t(ai.key)}</p>
                  </>
                ) : (
                  <p className="type-footnote text-label-2">{CONSEQUENCE[purpose] ? t(CONSEQUENCE[purpose]) : null}</p>
                )}
                <p className="type-footnote text-label-3">{c.granted ? t("privacy.consent.since", { date: when(c.granted_at) }) : c.withdrawn_at ? t("privacy.consent.withdrawnOn", { date: when(c.withdrawn_at) }) : t("privacy.consent.never")}</p>
              </div>
              <Switch id={id} checked={c.granted} disabled={m.isPending} onCheckedChange={(on) => (on ? run(c, true) : CONFIRM[purpose] ? (setConfirm(c), setOpen(true)) : run(c, false))} data-testid={`consent-switch-${c.purpose}`} />
            </li>
          );
        })}
      </ul>
      <ConfirmDialog open={open} onOpenChange={setOpen} title={ask ? t(ask.title) : ""} description={ask ? t(ask.body) : ""} confirmLabel={ask ? t(ask.confirm) : ""} destructive busy={m.isPending} onConfirm={() => confirm && run(confirm, false)} />
    </Card>
  );
}

const KIND_HINT: Record<DsrKind, MessageKey> = {
  export: "privacy.request.hint.export",
  erase: "privacy.request.hint.erase",
  rectify: "privacy.request.hint.rectify",
  info: "privacy.request.hint.info",
};

export const STATUS_TONE: Record<string, string> = {
  OPEN: "bg-status-warning text-status-warning-fg",
  IN_PROGRESS: "bg-status-warning text-status-warning-fg",
  DONE: "bg-status-feasible text-status-feasible-fg",
  REFUSED: "bg-status-infeasible text-status-infeasible-fg",
};

function RequestsCard({ requests, dueDays }: { requests: Dsr[]; dueDays: number }) {
  const { t, locale } = useI18n();
  const create = useCreateDataRequest();
  const when = useDateTime();
  const kindId = useId();
  const noteId = useId();
  const [kind, setKind] = useState<DsrKind>("export");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [confirmErase, setConfirmErase] = useState(false);
  const noteNeeded = kind === "rectify";

  const send = () => {
    setError(null);
    if (noteNeeded && !note.trim()) return setError(t("privacy.request.noteRequired"));
    create.mutate(
      { kind, note: note.trim() || null },
      {
        onSuccess: (r) => {
          setNote("");
          setConfirmErase(false);
          toast.success(r.kind === "export" ? t("privacy.request.exportReady") : t("privacy.request.sent", { days: dueDays }));
        },
        onError: (e) => {
          const err = wave1Error(e);
          setConfirmErase(false);
          setError(err.code === "duplicate" ? t("privacy.request.duplicate") : errorText(err, locale));
        },
      },
    );
  };
  const download = async (id: number) => {
    setDownloading(id);
    try {
      await downloadExport(id);
    } catch (e) {
      const err = wave1Error(e);
      toast.error(err.status === 410 ? t("privacy.request.expired") : errorText(err, locale));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Card variant="glass" className="gap-3 px-4" data-testid="privacy-requests">
      <div>
        <p className="type-headline text-label-1">{t("privacy.request.title")}</p>
        <p className="type-callout text-label-2">{t("privacy.request.lead", { days: dueDays })}</p>
      </div>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (kind === "erase") setConfirmErase(true);
          else send();
        }}
      >
        <div className="grid max-w-[420px] gap-3">
          <Field label={t("privacy.request.kind")} htmlFor={kindId} hint={t(KIND_HINT[kind])}>
            <NativeSelect id={kindId} value={kind} onChange={(e) => setKind(e.target.value as DsrKind)} data-testid="privacy-request-kind">
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`privacy.request.kinds.${k}` as MessageKey)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label={noteNeeded ? t("privacy.request.noteRectify") : t("privacy.request.note")} htmlFor={noteId}>
            <Textarea id={noteId} rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} data-testid="privacy-request-note" />
          </Field>
        </div>
        {error ? <Alert tone="error" data-testid="privacy-request-error">{error}</Alert> : null}
        <div>
          <Button type="submit" {...busyProps(create.isPending)} data-testid="privacy-request-send">
            <BusyLabel busy={create.isPending} label={t("busy.sending")}>
              {kind === "export" ? t("privacy.request.exportNow") : t("privacy.request.send")}
            </BusyLabel>
          </Button>
        </div>
      </form>
      {requests.length ? (
        <ul className="flex flex-col gap-2" aria-label={t("privacy.request.mine")} data-testid="privacy-request-list">
          {requests.map((r) => {
            const tone = dueTone(r);
            return (
              <li key={r.id} className="flex flex-col gap-1 rounded-lg bg-fill-3 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between" data-testid={`privacy-request-${r.id}`}>
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 type-callout font-medium text-label-1">
                    {t(`privacy.request.kinds.${r.kind}` as MessageKey)}
                    <span className={cn("rounded-full px-2 type-caption", STATUS_TONE[r.status] ?? "bg-fill-2 text-label-2")}>{t(`privacy.status.${r.status}` as MessageKey)}</span>
                  </p>
                  <p className="type-footnote text-label-2">
                    {t("privacy.request.created", { date: when(r.created_at) })}
                    {tone !== "closed" && r.due_at ? <span className={cn(tone === "overdue" && "font-medium text-status-infeasible-fg")}> · {t("privacy.request.due", { date: when(r.due_at), days: r.days_left ?? 0 })}</span> : null}
                    {r.kind === "export" && r.download_expires_at ? <span> · {r.downloadable ? t("privacy.request.expiresOn", { date: when(r.download_expires_at, true) }) : t("privacy.request.expiredShort")}</span> : null}
                  </p>
                  {r.refusal_reason ? <p className="type-footnote text-label-1">{t("privacy.request.refusal", { reason: r.refusal_reason })}</p> : null}
                  {r.status === "DONE" && r.kind !== "export" ? <p className="type-footnote text-label-2">{t("privacy.request.done", { date: when(r.handled_at) })}</p> : null}
                </div>
                {r.downloadable ? (
                  <Button variant="outline" size="sm" className="self-start sm:self-auto pointer-coarse:min-h-11" onClick={() => void download(r.id)} {...busyProps(downloading === r.id)} data-testid={`privacy-download-${r.id}`}>
                    <BusyLabel busy={downloading === r.id} label={t("busy.loading")} icon={<Download aria-hidden />}>
                      {t("privacy.request.download")}
                    </BusyLabel>
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="type-footnote text-label-3">{t("privacy.request.none")}</p>
      )}
      <ConfirmDialog open={confirmErase} onOpenChange={setConfirmErase} title={t("privacy.request.eraseTitle")} description={t("privacy.request.eraseBody", { days: dueDays })} confirmLabel={t("privacy.request.eraseConfirm")} destructive busy={create.isPending} onConfirm={send} />
    </Card>
  );
}
