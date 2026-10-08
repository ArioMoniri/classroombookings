"use client";
/**
 * /admin/email: SMTP server, "send a test" and the notification outbox. Without SMTP every notification
 * stays in the outbox as UNSENT (nothing pretends to send); an administrator can retry after configuring.
 */
import { Loader2, RotateCw, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation, useOutbox, useSmtpSettings, type SmtpSettings } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, FieldRow, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";

export function EmailSettingsView() {
  const { t } = useI18n();
  const q = useSmtpSettings();
  return (
    <div className="flex flex-col gap-6">
      <PageTitle title={t("crbs.admin.email.title")} subtitle={t("crbs.email.lead")} />
      {q.isLoading ? <Loading /> : q.data ? <SmtpForm key={JSON.stringify(q.data)} data={q.data} /> : <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>}
      <OutboxList />
    </div>
  );
}

function SmtpForm({ data }: { data: SmtpSettings }) {
  const { t } = useI18n();
  const [d, setD] = useState<Partial<Omit<SmtpSettings, "configured">>>({});
  const masked = data.password as unknown as { set?: boolean; masked?: string } | string | null | undefined;
  const v = { ...data, ...d };
  const set = <K extends keyof typeof d>(k: K, val: (typeof d)[K]) => setD((p) => ({ ...p, [k]: val }));
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const toastError = useErrorToast();
  const save = useCrbsMutation(() => crbs.org.putSmtp(d), [["crbs", "smtp"], ["crbs", "setup-status"]]);
  const test = useCrbsMutation(() => crbs.org.testSmtp(to), [["crbs", "outbox"]]);
  const pwSet = typeof masked === "object" && masked ? masked.set : !!masked;
  return (
    <>
      <Card variant="glass" className="gap-0 px-4 py-1">
        <p className="py-2 type-callout text-label-2">{data.configured ? t("crbs.email.configured") : t("crbs.email.notConfigured")}</p>
        <FieldRow label={t("crbs.email.host")} htmlFor="smtp-host" className="hairline-t">
          <Input id="smtp-host" className="w-64" value={v.host ?? ""} onChange={(e) => set("host", e.target.value)} placeholder="smtp.uni.edu.tr" />
          <Input aria-label={t("crbs.ldap.port")} type="number" className="w-20" value={v.port ?? ""} onChange={(e) => set("port", e.target.value ? Number(e.target.value) : null)} />
        </FieldRow>
        <FieldRow label={t("crbs.email.security")} htmlFor="smtp-sec" className="hairline-t">
          <SelectField id="smtp-sec" className="w-40" value={v.security ?? "starttls"} onChange={(e) => set("security", e.target.value as "starttls" | "ssl" | "none")}>
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL/TLS</option>
            <option value="none">{t("crbs.common.none")}</option>
          </SelectField>
        </FieldRow>
        <FieldRow label={t("crbs.users.username")} htmlFor="smtp-user" className="hairline-t">
          <Input id="smtp-user" className="w-64" autoComplete="off" value={v.username ?? ""} onChange={(e) => set("username", e.target.value)} />
        </FieldRow>
        <FieldRow label={t("crbs.users.password")} hint={pwSet ? t("crbs.email.passwordKept") : undefined} htmlFor="smtp-pw" className="hairline-t">
          <Input id="smtp-pw" type="password" className="w-64" autoComplete="new-password" placeholder={pwSet ? "••••••••" : ""} value={typeof d.password === "string" ? d.password : ""} onChange={(e) => set("password", e.target.value)} />
        </FieldRow>
        <FieldRow label={t("crbs.email.from")} htmlFor="smtp-from" className="hairline-t">
          <Input id="smtp-from" type="email" className="w-64" value={v.from_address ?? ""} onChange={(e) => set("from_address", e.target.value)} />
          <Input aria-label={t("crbs.email.fromName")} className="w-40" value={v.from_name ?? ""} onChange={(e) => set("from_name", e.target.value)} />
        </FieldRow>
      </Card>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            test.mutate(undefined, {
              onSuccess: (r) => (r.status === "SENT" ? toast.success(t("crbs.email.testSent", { to })) : toast.warning(t("crbs.email.testUnsent", { status: r.status, error: r.error ?? "" }))),
              onError: toastError,
            });
          }}
        >
          <Field label={t("crbs.email.testTo")} htmlFor="smtp-to">
            <Input id="smtp-to" type="email" className="w-64" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <Button type="submit" variant="outline" disabled={!to || test.isPending}>
            {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
            {t("crbs.email.sendTest")}
          </Button>
        </form>
        <Button disabled={!Object.keys(d).length || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), setD({})), onError: (e) => setError(bookingErrorMessage(crbsError(e), t)) })}>
          {t("crbs.common.save")}
        </Button>
      </div>
    </>
  );
}

function OutboxList() {
  const { t, locale } = useI18n();
  const [status, setStatus] = useState("");
  const q = useOutbox(status || undefined);
  const toastError = useErrorToast();
  const retry = useCrbsMutation((id: number) => crbs.bookingAdmin.retryOutbox(id), [["crbs", "outbox"]]);
  const dt = (iso: string | null | undefined) => (iso ? new Date(/Z|\+/.test(iso) ? iso : `${iso}Z`).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "short", timeStyle: "short" }) : "");
  return (
    <section aria-labelledby="outbox" className="flex flex-col gap-3">
      <SectionTitle
        id="outbox"
        actions={
          <SelectField aria-label={t("crbs.users.status")} className="w-40" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("crbs.email.all")}</option>
            <option value="UNSENT">{t("crbs.email.unsent")}</option>
            <option value="FAILED">{t("crbs.email.failed")}</option>
            <option value="SENT">{t("crbs.email.sent")}</option>
          </SelectField>
        }
      >
        {t("crbs.email.outbox")}
      </SectionTitle>
      <Card variant="glass" className="py-0">
        {q.isLoading ? <Loading className="px-4" /> : null}
        {q.data && q.data.length === 0 ? <p className="px-4 py-4 type-callout text-label-2">{t("crbs.email.empty")}</p> : null}
        <ul>
          {(q.data ?? []).map((m) => (
            <li key={m.id} className="flex items-start gap-3 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
              <span className="min-w-0 flex-1">
                <span className="block truncate type-headline text-label-1">{m.subject}</span>
                <span className="block truncate type-footnote text-label-2">
                  {m.to_email ?? t("crbs.email.toAdmins")} · {dt(m.created_at)}
                  {m.attempts ? ` · ${t("crbs.email.attempts", { n: m.attempts })}` : ""}
                </span>
                {m.error ? <span className="block truncate type-footnote text-status-infeasible-fg">{m.error}</span> : null}
              </span>
              <Badge variant="secondary" tone={m.status === "SENT" ? "feasible" : m.status === "FAILED" ? "infeasible" : "warning"}>
                {m.status === "SENT" ? t("crbs.email.sent") : m.status === "FAILED" ? t("crbs.email.failed") : t("crbs.email.unsent")}
              </Badge>
              {m.status !== "SENT" && m.kind !== "password_reset" && m.to_email ? (
                <Button variant="ghost" size="icon-sm" aria-label={t("crbs.email.retry")} disabled={retry.isPending} onClick={() => retry.mutate(m.id, { onError: toastError })}>
                  <RotateCw />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}
