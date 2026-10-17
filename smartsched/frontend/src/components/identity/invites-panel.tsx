"use client";
/**
 * Invitations per provider (wave 3b W3-IDP): invite one person by e-mail with the sign-in method to use (an identity
 * provider or a local password), the themed invite e-mail (W3-MAIL), the link shown once to copy, resend / renew /
 * revoke (revoking disables the unused placeholder account, T-R1-35), and bulk invite from a CSV (Excel's ";" and
 * Turkish headers accepted; refused rows listed with the line and the reason in TR/EN).
 */
import { useState } from "react";
import { toast } from "sonner";
import { CopyField } from "@/components/admin/integrations/copy-field";
import { Field, SelectField } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRoles } from "@/lib/api/crbs";
import { apiProblem } from "@/lib/api/identity";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { roleLabel } from "@/lib/i18n/roles";
import { usePermissions } from "@/lib/permissions";
import { idp, useIdpMutation, useProviderInvites, type BulkOut, type Provider, type ProviderInvite } from "./providers-api";
import { cleanPasted } from "./providers-model";

export function InvitesPanel({ providers }: { providers: Provider[] }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const roles = useRoles(can("setup.roles"));
  const invites = useProviderInvites();
  const options = [
    ...providers.map((p) => ({
      value: p.name,
      label: locale === "en" ? p.label_en : p.label,
    })),
    { value: "local", label: t("identity.invites.local") },
  ];
  const [provider, setProvider] = useState(options[0]?.value ?? "local");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [send, setSend] = useState(true);
  const [created, setCreated] = useState<ProviderInvite | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [csv, setCsv] = useState("");
  const [bulk, setBulk] = useState<BulkOut | null>(null);
  const lang = locale === "en" ? "en" : "tr";
  const fail = (e: unknown) => problemText(e, locale) ?? apiProblem(e, locale).text ?? t("identity.saveFailed");
  const invite = useIdpMutation(() =>
    idp.invite({
      email: cleanPasted(email).value,
      full_name: cleanPasted(name).value || null,
      role_id: role ? Number(role) : null,
      provider,
      send_email: send,
      locale: lang,
    }),
  );
  const bulkM = useIdpMutation(() =>
    idp.bulk({
      csv,
      provider,
      role_id: role ? Number(role) : null,
      send_email: send,
      locale: lang,
    }),
  );
  const resend = useIdpMutation((id: number) => idp.resend(id, lang));
  const renew = useIdpMutation((id: number) => idp.renew(id));
  const revoke = useIdpMutation((id: number) => idp.revoke(id));
  return (
    <Card data-testid="idp-invites">
      <CardHeader>
        <CardTitle>{t("identity.invites.title")}</CardTitle>
        <CardDescription>{t("identity.invites.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            setCreated(null);
            if (!cleanPasted(email).value.includes("@")) return setError(t("identity.invites.badEmail"));
            invite.mutate(undefined, {
              onSuccess: (out) => {
                setCreated(out);
                setEmail("");
                setName("");
                toast.success(
                  out.email_status === "SENT"
                    ? t("identity.invites.sent", {
                        email: out.email,
                      })
                    : t("identity.invites.created", {
                        email: out.email,
                      }),
                );
              },
              onError: (err) => setError(fail(err)),
            });
          }}
        >
          <Field label={t("identity.invites.email")} htmlFor="inv-email">
            <Input
              id="inv-email"
              type="email"
              inputMode="email"
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ad.soyad@uni.edu.tr"
              className="text-base sm:text-sm"
              data-testid="inv-email"
            />
          </Field>
          <Field label={t("identity.invites.name")} htmlFor="inv-name">
            <Input id="inv-name" value={name} onChange={(e) => setName(e.target.value)} className="text-base sm:text-sm" data-testid="inv-name" />
          </Field>
          <Field label={t("identity.invites.provider")} htmlFor="inv-provider">
            <SelectField id="inv-provider" value={provider} onChange={(e) => setProvider(e.target.value)} data-testid="inv-provider">
              {options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("identity.invites.role")} htmlFor="inv-role">
            <SelectField id="inv-role" value={role} onChange={(e) => setRole(e.target.value)} data-testid="inv-role">
              <option value="">{t("identity.invites.defaultRole")}</option>
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {roleLabel(t, r)}
                </option>
              ))}
            </SelectField>
          </Field>
          <label className="flex min-h-11 items-center gap-2 type-callout sm:col-span-2">
            <Checkbox checked={send} onCheckedChange={(v) => setSend(v === true)} data-testid="inv-send" />
            {t("identity.invites.send")}
          </label>
          <div className="sm:col-span-2">
            <BusyButton type="submit" busy={invite.isPending} busyLabel={t("busy.saving")} className="min-h-11" data-testid="inv-submit">
              {t("identity.invites.submit")}
            </BusyButton>
          </div>
        </form>
        {error ? (
          <Alert tone="error" data-testid="inv-error">
            {error}
          </Alert>
        ) : null}
        {created?.link ? (
          <div className="flex flex-col gap-2" data-testid="inv-created">
            {created.email_status && created.email_status !== "SENT" ? <Alert tone="warning">{t("identity.invites.notSent")}</Alert> : null}
            <CopyField label={t("identity.invites.link")} value={created.link} testId="inv-link" />
            <p className="type-footnote text-label-2">{t("identity.invites.linkOnce")}</p>
          </div>
        ) : null}

        <details className="rounded-xl p-3 shadow-(--edge-control)" data-testid="inv-bulk">
          <summary className="min-h-11 cursor-pointer content-center type-callout font-semibold text-label-1">{t("identity.invites.bulk")}</summary>
          <div className="mt-2 flex flex-col gap-3">
            <p className="type-footnote text-label-2">{t("identity.invites.bulkLead")}</p>
            <input
              type="file"
              accept=".csv,text/csv,text/plain"
              aria-label={t("identity.invites.bulkFile")}
              className="type-callout"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) setCsv(await f.text());
              }}
            />
            <Textarea
              rows={5}
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              placeholder={"E-posta;Ad Soyad;Rol\nayse.yilmaz@uni.edu.tr;Ayşe Yılmaz;Öğretmen"}
              className="font-mono text-base sm:text-sm"
              aria-label={t("identity.invites.bulkText")}
              data-testid="inv-bulk-text"
            />
            <div>
              <BusyButton
                busy={bulkM.isPending}
                busyLabel={t("busy.saving")}
                disabled={!csv.trim()}
                className="min-h-11"
                onClick={() =>
                  bulkM.mutate(undefined, {
                    onSuccess: setBulk,
                    onError: (err) => toast.error(fail(err)),
                  })
                }
                data-testid="inv-bulk-submit"
              >
                {t("identity.invites.bulkSubmit")}
              </BusyButton>
            </div>
            {bulk ? (
              <div className="flex flex-col gap-2" data-testid="inv-bulk-result" aria-live="polite">
                <p className="type-callout text-label-1">
                  {t("identity.invites.bulkDone", {
                    ok: bulk.created.length,
                    bad: bulk.errors.length,
                  })}
                </p>
                {bulk.errors.length ? (
                  <ul className="flex flex-col gap-1 type-footnote">
                    {bulk.errors.map((e) => (
                      <li key={`${e.line}-${e.code}`} className="text-status-infeasible-fg">
                        {t("identity.invites.line", {
                          n: e.line,
                        })}
                        : {e.email ? `${e.email} · ` : ""}
                        {locale === "en" ? e.en : e.tr}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        </details>

        <div className="flex flex-col" data-testid="inv-list">
          {(invites.data ?? []).length === 0 ? <p className="type-footnote text-label-3">{t("identity.invites.none")}</p> : null}
          {(invites.data ?? []).map((i) => (
            <div key={i.id} className="flex flex-wrap items-center gap-2 py-2 hairline-b" data-testid={`inv-row-${i.id}`}>
              <div className="min-w-0 flex-1">
                <p className="truncate type-callout text-label-1">{i.email}</p>
                <p className="type-footnote text-label-2">
                  {i.provider_label ?? i.provider} · {t(i.status === "invite_expired" ? "identity.invites.expired" : "identity.invites.open")} ·{" "}
                  {t("identity.invites.until", {
                    when: new Date(i.expires_at).toLocaleDateString(locale === "tr" ? "tr-TR" : "en-GB", { timeZone: "Europe/Istanbul" }),
                  })}
                </p>
              </div>
              {i.status === "invited" ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="min-h-11 sm:min-h-9"
                  disabled={resend.isPending}
                  onClick={() =>
                    resend.mutate(i.id, {
                      onSuccess: (r) => toast[r.sent ? "success" : "warning"](t(r.sent ? "identity.invites.resent" : "identity.invites.notSent")),
                      onError: (e) => toast.error(fail(e)),
                    })
                  }
                >
                  {t("identity.invites.resend")}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                className="min-h-11 sm:min-h-9"
                disabled={renew.isPending}
                onClick={() =>
                  renew.mutate(i.id, {
                    onSuccess: (r) => setCreated(r),
                    onError: (e) => toast.error(fail(e)),
                  })
                }
              >
                {t("identity.invites.renew")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="min-h-11 sm:min-h-9"
                disabled={revoke.isPending}
                onClick={() =>
                  revoke.mutate(i.id, {
                    onSuccess: () => toast.success(t("identity.invites.revoked")),
                    onError: (e) => toast.error(fail(e)),
                  })
                }
                data-testid={`inv-revoke-${i.id}`}
              >
                {t("identity.invites.revoke")}
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
