"use client";
/**
 * Ayarlar › Genel › Güvenlik iletişimi (security follow-up wave3-sec2; docs/SECURITY.md "security.txt").
 * The institution's RFC 9116 contact: `GET` / `PUT /admin/security-contact` (administrators, audited
 * `security.contact`). The backend serves /.well-known/security.txt from it; while the e-mail is unset the card warns
 * "Güvenlik iletişim adresi ayarlanmadı". A refusal (422 `field`, `message_tr` / `message_en`) is shown under the named
 * field, which takes the focus.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Field } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { request } from "@/lib/api/client";
import { refusalBody } from "@/lib/api/error-text";
import { useMeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";

const Contact = z.object({
  contact_email: z.string().nullish(),
  contact_url: z.string().nullish(),
  policy_url: z.string().nullish(),
  preferred_languages: z.string().nullish(),
  configured: z.boolean(),
  warning: z.object({ message_tr: z.string(), message_en: z.string() }).nullish(),
  last_change: z.object({ actor: z.string().nullish(), at: z.string().nullish() }).nullish(),
});
type Contact = z.infer<typeof Contact>;
const FIELDS = ["contact_email", "contact_url", "policy_url", "preferred_languages"] as const;
type FieldName = (typeof FIELDS)[number];
const KEY = ["admin", "security-contact"];

export function SecurityContactCard() {
  const me = useMeFull();
  if (me.data?.role !== "ADMIN") return null;
  return <SecurityContactForm />;
}

function SecurityContactForm() {
  const { t, locale } = useI18n();
  const ids = useId();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: () => request("/admin/security-contact", { schema: Contact, silent: true }) });
  // the typed values; null = show what the server holds (no effect copying server data into state)
  const [edits, setEdits] = useState<Record<FieldName, string> | null>(null);
  const form: Record<FieldName, string> = edits ?? { contact_email: q.data?.contact_email ?? "", contact_url: q.data?.contact_url ?? "", policy_url: q.data?.policy_url ?? "", preferred_languages: q.data?.preferred_languages ?? "tr, en" };
  const setForm = (next: (f: Record<FieldName, string>) => Record<FieldName, string>) => setEdits(next(form));
  const [error, setError] = useState<{ field: FieldName | null; text: string } | null>(null);
  const refs = useRef<Partial<Record<FieldName, HTMLInputElement | null>>>({});
  useEffect(() => {
    if (error?.field) refs.current[error.field]?.focus();
  }, [error]);

  const save = useMutation({
    mutationFn: (body: Record<FieldName, string>) => request("/admin/security-contact", { method: "PUT", body, schema: Contact, silent: true }),
    onSuccess: (data: Contact) => {
      setError(null);
      qc.setQueryData(KEY, data);
      setEdits(null);
      toast.success(t("settings.securityContact.saved"));
    },
    onError: (e: unknown) => {
      const d = refusalBody(e);
      const field = typeof d?.field === "string" && (FIELDS as readonly string[]).includes(d.field) ? (d.field as FieldName) : null;
      const said = d ? (locale === "tr" ? d.message_tr : d.message_en) : null;
      setError({ field, text: typeof said === "string" && said ? said : t("settings.securityContact.failed") });
    },
  });

  const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { timeZone: "Europe/Istanbul", dateStyle: "medium", timeStyle: "short" }) : "");
  const last = q.data?.last_change;
  const labels: Record<FieldName, { label: string; hint: string; type: string; inputMode?: "email" | "url" | "text" }> = {
    contact_email: { label: t("settings.securityContact.email"), hint: t("settings.securityContact.emailHint"), type: "email", inputMode: "email" },
    contact_url: { label: t("settings.securityContact.url"), hint: t("settings.securityContact.urlHint"), type: "url", inputMode: "url" },
    policy_url: { label: t("settings.securityContact.policy"), hint: t("settings.securityContact.urlHint"), type: "url", inputMode: "url" },
    preferred_languages: { label: t("settings.securityContact.languages"), hint: t("settings.securityContact.languagesHint"), type: "text" },
  };

  return (
    <Card data-testid="settings-security-contact">
      <CardHeader>
        <CardTitle>{t("settings.securityContact.title")}</CardTitle>
        <CardDescription>{t("settings.securityContact.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.data && !q.data.configured ? (
          <Alert tone="warning" title={locale === "tr" ? (q.data.warning?.message_tr ?? t("settings.securityContact.unset")) : (q.data.warning?.message_en ?? t("settings.securityContact.unset"))} data-testid="security-contact-unset">
            {t("settings.securityContact.unsetLead")}
          </Alert>
        ) : null}
        <form
          className="grid gap-3 md:grid-cols-2"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ ...form });
          }}
        >
          {FIELDS.map((name) => (
            <Field key={name} label={labels[name].label} htmlFor={`${ids}-${name}`} hint={labels[name].hint} error={error?.field === name ? error.text : null}>
              <Input
                id={`${ids}-${name}`}
                ref={(el) => {
                  refs.current[name] = el;
                }}
                type={labels[name].type}
                inputMode={labels[name].inputMode}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={error?.field === name || undefined}
                value={form[name]}
                onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
                data-testid={`security-contact-${name}`}
              />
            </Field>
          ))}
          <div className="flex flex-wrap items-center gap-3 md:col-span-2">
            <Button type="submit" disabled={save.isPending} className="pointer-coarse:min-h-11" data-testid="security-contact-save">
              {t("settings.securityContact.save")}
            </Button>
            <p className="type-footnote text-label-3" data-testid="security-contact-last">
              {last?.at ? t("settings.securityContact.lastChange", { name: last.actor ?? "—", time: when(last.at) }) : t("settings.securityContact.never")}
            </p>
          </div>
          {error && !error.field ? (
            <p className="type-footnote text-status-infeasible-fg md:col-span-2" role="alert">
              {error.text}
            </p>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
