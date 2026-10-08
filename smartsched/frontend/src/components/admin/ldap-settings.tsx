"use client";
/** /admin/authentication (CRBS `settings/Authentication`): LDAP sign-in with a "test" that binds without saving. */
import { Loader2, PlugZap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { crbs, crbsError, useCrbsMutation, useDepartments, useLdapSettings, useRoles, type LdapSettings, type LdapTestOut } from "@/lib/api/crbs";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, FieldRow, Loading, PageTitle, SectionTitle, SelectField } from "./kit";

export function LdapSettingsView() {
  const { t } = useI18n();
  const q = useLdapSettings();
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>;
  return <LdapForm key={JSON.stringify(q.data)} data={q.data} />;
}

const TEXT_FIELDS: { k: keyof LdapSettings; label: MessageKey; hint?: MessageKey; mono?: boolean }[] = [
  { k: "server", label: "crbs.ldap.server", hint: "crbs.ldap.serverHint" },
  { k: "bind_dn_format", label: "crbs.ldap.bindDn", hint: "crbs.ldap.bindDnHint", mono: true },
  { k: "base_dn", label: "crbs.ldap.baseDn", mono: true },
  { k: "search_filter", label: "crbs.ldap.filter", hint: "crbs.ldap.filterHint", mono: true },
  { k: "attr_firstname", label: "crbs.ldap.attrFirst", mono: true },
  { k: "attr_lastname", label: "crbs.ldap.attrLast", mono: true },
  { k: "attr_displayname", label: "crbs.ldap.attrDisplay", hint: "crbs.ldap.attrHint", mono: true },
  { k: "attr_email", label: "crbs.ldap.attrEmail", mono: true },
];

function LdapForm({ data }: { data: LdapSettings }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const roles = useRoles(can("setup.roles"));
  const departments = useDepartments();
  const [d, setD] = useState<Partial<LdapSettings>>({});
  const v = { ...data, ...d };
  const set = <K extends keyof LdapSettings>(k: K, val: LdapSettings[K]) => setD((p) => ({ ...p, [k]: val }));
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [result, setResult] = useState<LdapTestOut | null>(null);
  const save = useCrbsMutation(() => crbs.org.putLdap(d), [["crbs", "ldap"], ["crbs", "org-public"]]);
  const test = useCrbsMutation(() => crbs.org.testLdap({ username: user, password: pass, settings: d }));
  return (
    <div className="flex flex-col gap-6">
      <PageTitle title={t("crbs.admin.ldap.title")} subtitle={t("crbs.ldap.lead")} />
      <Card variant="glass" className="gap-0 px-4 py-1">
        <FieldRow label={t("crbs.ldap.enabled")} hint={t("crbs.ldap.enabledHint")} htmlFor="ldap-on">
          <Switch id="ldap-on" checked={v.enabled} onCheckedChange={(x) => set("enabled", x)} />
        </FieldRow>
        <FieldRow label={t("crbs.ldap.create")} hint={t("crbs.ldap.createHint")} htmlFor="ldap-create" className="hairline-t">
          <Switch id="ldap-create" checked={v.create_users} onCheckedChange={(x) => set("create_users", x)} />
        </FieldRow>
        <FieldRow label={t("crbs.ldap.port")} htmlFor="ldap-port" className="hairline-t">
          <Input id="ldap-port" type="number" className="w-24" value={v.port ?? ""} onChange={(e) => set("port", e.target.value ? Number(e.target.value) : null)} />
          <SelectField aria-label={t("crbs.ldap.version")} className="w-28" value={String(v.version ?? 3)} onChange={(e) => set("version", Number(e.target.value))}>
            <option value="3">LDAPv3</option>
            <option value="2">LDAPv2</option>
          </SelectField>
        </FieldRow>
        <FieldRow label={t("crbs.ldap.tls")} htmlFor="ldap-tls" className="hairline-t">
          <Switch id="ldap-tls" checked={v.use_tls} onCheckedChange={(x) => set("use_tls", x)} />
        </FieldRow>
        <FieldRow label={t("crbs.ldap.ignoreCert")} hint={t("crbs.ldap.ignoreCertHint")} htmlFor="ldap-ign" className="hairline-t">
          <Switch id="ldap-ign" checked={v.ignore_cert} onCheckedChange={(x) => set("ignore_cert", x)} />
        </FieldRow>
        {TEXT_FIELDS.map((f) => (
          <FieldRow key={f.k} label={t(f.label)} hint={f.hint ? t(f.hint) : undefined} htmlFor={`ldap-${f.k}`} className="hairline-t">
            <Input id={`ldap-${f.k}`} className={f.mono ? "w-80 font-mono" : "w-80"} value={String(v[f.k] ?? "")} onChange={(e) => set(f.k, e.target.value as never)} />
          </FieldRow>
        ))}
        <FieldRow label={t("crbs.ldap.defaultRole")} hint={t("crbs.ldap.defaultRoleHint")} htmlFor="ldap-role" className="hairline-t">
          <SelectField id="ldap-role" className="w-56" value={v.default_role_id ?? ""} onChange={(e) => set("default_role_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">{t("crbs.users.noRole")}</option>
            {(roles.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </SelectField>
        </FieldRow>
        <FieldRow label={t("crbs.ldap.defaultDept")} htmlFor="ldap-dept" className="hairline-t">
          <SelectField id="ldap-dept" className="w-56" value={v.default_department_id ?? ""} onChange={(e) => set("default_department_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">{t("crbs.book.departmentNone")}</option>
            {(departments.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </SelectField>
        </FieldRow>
      </Card>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex justify-end">
        <Button disabled={!Object.keys(d).length || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), setD({})), onError: (e) => setError(bookingErrorMessage(crbsError(e), t)) })}>
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("crbs.common.save")}
        </Button>
      </div>
      <section aria-labelledby="ldap-test" className="flex flex-col gap-3">
        <SectionTitle id="ldap-test">{t("crbs.ldap.test")}</SectionTitle>
        <p className="type-callout text-label-2">{t("crbs.ldap.testHint")}</p>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setResult(null);
            test.mutate(undefined, { onSuccess: setResult, onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
          }}
        >
          <Field label={t("crbs.users.username")} htmlFor="ldap-tu">
            <Input id="ldap-tu" autoComplete="off" value={user} onChange={(e) => setUser(e.target.value)} />
          </Field>
          <Field label={t("crbs.users.password")} htmlFor="ldap-tp">
            <Input id="ldap-tp" type="password" autoComplete="off" value={pass} onChange={(e) => setPass(e.target.value)} />
          </Field>
          <Button type="submit" variant="outline" disabled={!user || !pass || test.isPending}>
            {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <PlugZap aria-hidden />}
            {t("crbs.ldap.runTest")}
          </Button>
        </form>
        {result ? (
          <Alert tone={result.ok ? "success" : "error"} title={result.ok ? t("crbs.ldap.ok") : result.connection_error ? t("crbs.ldap.unreachable") : t("crbs.ldap.failed")}>
            {result.errors.length ? <p>{result.errors.join(", ")}</p> : null}
            {result.mapped && Object.keys(result.mapped).length ? (
              <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 type-footnote">
                {Object.entries(result.mapped).map(([k, val]) => (
                  <div key={k} className="contents">
                    <dt className="font-medium">{k}</dt>
                    <dd>{String(val ?? "")}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </Alert>
        ) : null}
      </section>
    </div>
  );
}
