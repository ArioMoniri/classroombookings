"use client";
/**
 * /admin/email: the guided SMTP setup (components/admin/email/smtp-wizard), the themed e-mail templates
 * (components/admin/email/email-templates) and the notification outbox. Without SMTP every notification stays in the
 * outbox as UNSENT (nothing pretends to send); an administrator can retry after configuring (wave 3b W3-MAIL).
 */
import { RotateCw } from "lucide-react";
import { useId, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { crbs, useCrbsMutation, useOutbox } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { EmailTemplates } from "./email/email-templates";
import { SmtpWizard } from "./email/smtp-wizard";
import { Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";

export function EmailSettingsView() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-6">
      <PageTitle title={t("crbs.admin.email.title")} subtitle={t("crbs.email.lead")} />
      <EmailSettingsPanel />
    </div>
  );
}

type PanelTab = "setup" | "templates" | "outbox";

/** The whole e-mail area (W3-MAIL): guided SMTP setup, themed templates, the outbox. Exported for the integrations
 *  hub's E-posta sheet (W3-HUB, /admin/integrations); `initialTab` opens a section directly. */
export function EmailSettingsPanel({ initialTab = "setup" }: { initialTab?: PanelTab }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<PanelTab>(initialTab);
  const base = useId();
  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="email-settings-panel">
      <SegmentedControl
        aria-label={t("email.panel.tabs")}
        value={tab}
        onValueChange={(v) => setTab(v)}
        fill
        options={[
          { value: "setup", label: t("email.panel.setup"), controls: `${base}-setup` },
          { value: "templates", label: t("email.panel.templates"), controls: `${base}-templates` },
          { value: "outbox", label: t("email.panel.outbox"), controls: `${base}-outbox` },
        ]}
      />
      <div id={`${base}-${tab}`} role="tabpanel" className="min-w-0">
        {tab === "setup" ? <SmtpWizard /> : tab === "templates" ? <EmailTemplates /> : <OutboxList />}
      </div>
    </div>
  );
}

function OutboxList() {
  const { t } = useI18n();
  const [status, setStatus] = useState("");
  const q = useOutbox(status || undefined);
  const toastError = useErrorToast();
  const retry = useCrbsMutation((id: number) => crbs.bookingAdmin.retryOutbox(id), [["crbs", "outbox"]]);
  const fmt = useBookingFormat();
  const dt = fmt.dateTime;
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
      <Card className="py-0">
        {q.isLoading ? <Loading className="px-4" /> : null}
        {q.data && q.data.length === 0 ? <p className="px-4 py-4 type-callout text-label-2">{t("crbs.email.empty")}</p> : null}
        <ul>
          {(q.data ?? []).map((m) => (
            <li key={m.id} className="flex items-start gap-3 px-4 py-2.5 not-last:edge-hairline-b">
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
                <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-11" aria-label={t("crbs.email.retry")} disabled={retry.isPending} onClick={() => retry.mutate(m.id, { onError: toastError })}>
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
