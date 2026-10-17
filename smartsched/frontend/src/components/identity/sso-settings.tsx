"use client";
/**
 * Settings › Microsoft ile giriş (`planning.admin`; backend GET/PUT /auth/sso/admin/entra + /mappings, IT checklist
 * docs/deploy/sso-entra.md). Administrators may see "Entra ID" here (sign-in.md §2.1); users never do.
 *
 * - The client secret is write-only: the screen shows only "Ayarlandı" (`client_secret_set`), never a value or a
 *   fragment; "Değiştir" reveals an empty field. Values that come from SSM (`from_environment`) are labelled.
 * - Switching sign-in on is guarded by the backend's 422 (incomplete client, no public URL); the message is shown.
 * - "Microsoft only for non-administrators" is guarded by the 409 break-glass rule (an active administrator with
 *   a local password must exist); the message says what to do.
 * - Role mapping: app role values / group object ids → SmartSched roles (applied at every sign-in while on).
 */
import { Copy, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Field, FieldRow, Loading, SelectField } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusDot } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useRoles } from "@/lib/api/crbs";
import { apiProblem, identity, identityKeys, useIdentityMutation, useSsoConfig, useSsoMappings, type SsoConfig, type SsoConfigIn } from "@/lib/api/identity";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { roleLabel } from "@/lib/i18n/roles";
import { usePermissions } from "@/lib/permissions";
import { IdentityProvidersPanel } from "./identity-providers-panel";

const KEYS = [identityKeys.config, identityKeys.providers, identityKeys.mappings];

/**
 * Settings › Kimlik sağlayıcıları (wave 3b W3-IDP): every provider with its guided setup and the invitations
 * (`IdentityProvidersPanel`, also embedded by W3-HUB in /admin/integrations), then the Microsoft provider's account
 * switches that only exist there ("Microsoft only for non-administrators", break-glass rule).
 */
export function SsoSettings() {
  return (
    <div className="flex flex-col gap-8">
      <IdentityProvidersPanel />
      <MicrosoftSettings />
    </div>
  );
}

function MicrosoftSettings() {
  const { t, locale } = useI18n();
  const q = useSsoConfig();
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{problemText(q.error, locale) ?? apiProblem(q.error, locale).text ?? t("sso.admin.loadError")}</Alert>;
  return <SsoForm key={q.data.updated_at ?? "new"} cfg={q.data} />;
}

function useSave() {
  const { t, locale } = useI18n();
  const m = useIdentityMutation((body: SsoConfigIn) => identity.putConfig(body), KEYS);
  const [error, setError] = useState<string | null>(null);
  const save = (body: SsoConfigIn, ok = t("sso.admin.saved")) => {
    setError(null);
    m.mutate(body, {
      onSuccess: () => toast.success(ok),
      onError: (e) => {
        const p = apiProblem(e, locale);
        // T-R1-31: a validator's refusal (tenant 'common', a bad domain) reads in Turkish, without "Value error"
        setError(p.code === "break_glass" ? t("sso.admin.breakGlass409") : (problemText(e, locale) ?? p.text ?? t("sso.admin.saveFailed")));
      },
    });
  };
  return { save, error, pending: m.isPending, setError };
}

function SsoForm({ cfg }: { cfg: SsoConfig }) {
  const { t } = useI18n();
  const { save, error, pending } = useSave();
  const env = new Set(cfg.from_environment);
  const [tenant, setTenant] = useState(cfg.tenant_id ?? "");
  const [client, setClient] = useState(cfg.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [replacing, setReplacing] = useState(!cfg.client_secret_set);
  const [domain, setDomain] = useState(cfg.domain_hint ?? "");
  const [days, setDays] = useState(String(cfg.invite_days));
  const dirty: SsoConfigIn = {
    ...(tenant.trim() !== (cfg.tenant_id ?? "") ? { tenant_id: tenant.trim() } : {}),
    ...(client.trim() !== (cfg.client_id ?? "") ? { client_id: client.trim() } : {}),
    ...(secret.trim() ? { client_secret: secret.trim() } : {}),
    ...(domain.trim() !== (cfg.domain_hint ?? "") ? { domain_hint: domain.trim() } : {}),
    ...(Number(days) !== cfg.invite_days && Number(days) >= 1 ? { invite_days: Number(days) } : {}),
  };
  const hasChanges = Object.keys(dirty).length > 0;
  return (
    <div className="flex flex-col gap-5" data-testid="sso-settings">
      <Card>
        <CardHeader>
          <CardTitle>{t("sso.admin.title")}</CardTitle>
          <CardDescription>{t("sso.admin.lead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col">
          <FieldRow label={t("sso.admin.enabled")} hint={cfg.configured ? t("sso.admin.enabledHint") : t("sso.admin.notConfigured")} htmlFor="sso-enabled">
            <StatusDot tone={cfg.enabled ? "feasible" : "neutral"}>{cfg.enabled ? t("sso.admin.on") : t("sso.admin.off")}</StatusDot>
            <Switch id="sso-enabled" checked={cfg.enabled} disabled={pending} onCheckedChange={(v) => save({ enabled: v })} data-testid="sso-enabled" />
          </FieldRow>
          {error ? <Alert tone="error" data-testid="sso-error">{error}</Alert> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("sso.admin.app")}</CardTitle>
          <CardDescription>{t("sso.admin.appLead")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!hasChanges) return;
              save(dirty);
              setSecret("");
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={<>{t("sso.admin.tenant")} {env.has("tenant_id") ? <EnvBadge /> : null}</>} htmlFor="sso-tenant" hint={t("sso.admin.guidHint")}>
                <Input id="sso-tenant" value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="off" spellCheck={false} className="font-mono" data-testid="sso-tenant" />
              </Field>
              <Field label={<>{t("sso.admin.client")} {env.has("client_id") ? <EnvBadge /> : null}</>} htmlFor="sso-client" hint={t("sso.admin.guidHint")}>
                <Input id="sso-client" value={client} onChange={(e) => setClient(e.target.value)} autoComplete="off" spellCheck={false} className="font-mono" data-testid="sso-client" />
              </Field>
            </div>
            <Field label={<>{t("sso.admin.secret")} {env.has("client_secret") ? <EnvBadge /> : null}</>} htmlFor="sso-secret" hint={t("sso.admin.secretHint")}>
              {cfg.client_secret_set && !replacing ? (
                <span className="flex flex-wrap items-center gap-2">
                  <StatusDot tone="feasible">
                    <span data-testid="sso-secret-set">{t("sso.admin.secretSet")}</span>
                  </StatusDot>
                  <Button type="button" size="sm" variant="outline" onClick={() => setReplacing(true)} data-testid="sso-secret-replace">
                    {t("sso.admin.replace")}
                  </Button>
                </span>
              ) : (
                <Input id="sso-secret" type="password" autoComplete="new-password" spellCheck={false} value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={cfg.client_secret_set ? t("sso.admin.secretKeep") : ""} data-testid="sso-secret" />
              )}
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("sso.admin.domain")} htmlFor="sso-domain" hint={t("sso.admin.domainHint")}>
                <Input id="sso-domain" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="uni.edu.tr" autoComplete="off" spellCheck={false} data-testid="sso-domain" />
              </Field>
              <Field label={t("sso.admin.inviteDays")} htmlFor="sso-days" hint={t("sso.admin.inviteDaysHint")}>
                <Input id="sso-days" type="number" inputMode="numeric" min={1} max={365} value={days} onChange={(e) => setDays(e.target.value)} className="max-w-28" />
              </Field>
            </div>
            <Field label={t("sso.admin.redirect")} htmlFor="sso-redirect" hint={cfg.redirect_uri ? t("sso.admin.redirectHint") : t("sso.admin.redirectMissing")}>
              <span className="flex items-center gap-2">
                <Input id="sso-redirect" readOnly value={cfg.redirect_uri ?? ""} className="font-mono" onFocus={(e) => e.currentTarget.select()} data-testid="sso-redirect" />
                {cfg.redirect_uri ? (
                  <IconButton label={t("sso.admin.copy")} variant="outline" onClick={() => void navigator.clipboard?.writeText(cfg.redirect_uri ?? "").then(() => toast.success(t("sso.admin.copied")))}>
                    <Copy />
                  </IconButton>
                ) : null}
              </span>
            </Field>
            <div>
              <BusyButton type="submit" busy={pending} busyLabel={t("busy.saving")} disabled={!hasChanges} data-testid="sso-save">
                {t("crbs.common.save")}
              </BusyButton>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("sso.admin.accounts")}</CardTitle>
          <CardDescription>{t("sso.admin.accountsLead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col">
          <FieldRow label={t("sso.admin.selfSignup")} hint={t("sso.admin.selfSignupHint", { role: cfg.default_role ? roleLabel(t, cfg.default_role) : "—" })} htmlFor="sso-self" className="hairline-b">
            <Switch id="sso-self" checked={cfg.self_signup} disabled={pending} onCheckedChange={(v) => save({ self_signup: v })} data-testid="sso-self-signup" />
          </FieldRow>
          <DefaultRole cfg={cfg} onSave={(id) => save({ default_role_id: id })} />
          <FieldRow label={t("sso.admin.oidcOnly")} hint={t("sso.admin.oidcOnlyHint", { n: cfg.break_glass_admins })} htmlFor="sso-oidc-only" className="hairline-t">
            <Switch id="sso-oidc-only" checked={cfg.oidc_only_non_admins} disabled={pending} onCheckedChange={(v) => save({ oidc_only_non_admins: v })} data-testid="sso-oidc-only" />
          </FieldRow>
          {cfg.oidc_only_non_admins ? <p className="pb-2 type-footnote text-label-2">{t("sso.admin.breakGlassLink")}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("sso.admin.mapping")}</CardTitle>
          <CardDescription>{t("sso.admin.mappingLead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <FieldRow label={t("sso.admin.mappingOn")} hint={t("sso.admin.mappingOnHint")} htmlFor="sso-map" className="hairline-b">
            <Switch id="sso-map" checked={cfg.role_mapping_enabled} disabled={pending} onCheckedChange={(v) => save({ role_mapping_enabled: v })} data-testid="sso-mapping-enabled" />
          </FieldRow>
          <FieldRow label={t("sso.admin.adminMapping")} hint={t("sso.admin.adminMappingHint")} htmlFor="sso-admin-map" className="hairline-b">
            <Switch id="sso-admin-map" checked={cfg.allow_admin_mapping} disabled={pending} onCheckedChange={(v) => save({ allow_admin_mapping: v })} />
          </FieldRow>
          <Mappings />
        </CardContent>
      </Card>
    </div>
  );
}

function EnvBadge() {
  const { t } = useI18n();
  return (
    <Badge variant="secondary" className="ml-1 align-middle">
      {t("sso.admin.fromEnv")}
    </Badge>
  );
}

/** permissions the server refuses on the self sign-up role (`sso._too_privileged_for_default`, 422 default_role_privileged) */
const NOT_FOR_NEW_ACCOUNTS: ReadonlySet<string> = new Set(["planning.admin", "planning.edit", "setup.users", "setup.roles"]);

/** Whether a role may be the role of every new self-signed-up account (round-1 R1-M-25, T-R1-35). */
export function defaultRoleEligible(role: { code?: string | null; permissions: readonly string[] }): boolean {
  return role.code !== "ADMIN" && !role.permissions.some((p) => NOT_FOR_NEW_ACCOUNTS.has(p));
}

function DefaultRole({ cfg, onSave }: { cfg: SsoConfig; onSave: (id: number) => void }) {
  const { t } = useI18n();
  const { can } = usePermissions();
  const roles = useRoles(can("setup.roles"));
  if (!roles.data) {
    return (
      <FieldRow label={t("sso.admin.defaultRole")} hint={t("sso.admin.defaultRoleHint")}>
        <span className="type-callout text-label-1">{cfg.default_role ? roleLabel(t, cfg.default_role) : "—"}</span>
      </FieldRow>
    );
  }
  return (
    <FieldRow label={t("sso.admin.defaultRole")} hint={t("sso.admin.defaultRoleHint")} htmlFor="sso-default-role">
      <SelectField id="sso-default-role" className="w-56" value={String(cfg.default_role?.id ?? "")} onChange={(e) => e.target.value && onSave(Number(e.target.value))} data-testid="sso-default-role">
        {!cfg.default_role ? <option value="">—</option> : null}
        {/* only roles the server accepts for new accounts (the current one stays visible if an older setup chose it) */}
        {roles.data
          .filter((r) => defaultRoleEligible(r) || r.id === cfg.default_role?.id)
          .map((r) => (
            <option key={r.id} value={r.id}>
              {roleLabel(t, r)}
            </option>
          ))}
      </SelectField>
    </FieldRow>
  );
}

function Mappings() {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const q = useSsoMappings();
  const roles = useRoles(can("setup.roles"));
  const [claim, setClaim] = useState<"role" | "group">("role");
  const [value, setValue] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useIdentityMutation((b: { claim: "role" | "group"; value: string; role_id: number }) => identity.addMapping(b), [identityKeys.mappings]);
  const del = useIdentityMutation((id: number) => identity.deleteMapping(id), [identityKeys.mappings]);
  return (
    <div className="flex flex-col gap-3 pt-2" data-testid="sso-mappings">
      {(q.data ?? []).length ? (
        <ul className="flex flex-col">
          {(q.data ?? []).map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-3 py-2 hairline-b">
              <Badge variant="secondary">{m.claim === "role" ? t("sso.admin.claimRole") : t("sso.admin.claimGroup")}</Badge>
              <span className="min-w-0 flex-1 truncate font-mono type-footnote text-label-1">{m.value}</span>
              <span className="type-callout text-label-1">→ {roleLabel(t, m.role)}</span>
              <IconButton label={t("sso.admin.mappingDelete")} size="sm" onClick={() => del.mutate(m.id, { onError: (e) => toast.error(problemText(e, locale) ?? apiProblem(e, locale).text ?? t("sso.admin.saveFailed")) })}>
                <Trash2 />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="type-footnote text-label-3">{t("sso.admin.mappingNone")}</p>
      )}
      <form
        className="grid gap-2 sm:grid-cols-[auto_1fr_auto_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!value.trim() || !role) return setError(t("sso.admin.mappingIncomplete"));
          add.mutate(
            { claim, value: value.trim(), role_id: Number(role) },
            {
              onSuccess: () => {
                setValue("");
                toast.success(t("sso.admin.saved"));
              },
              onError: (err) => setError(problemText(err, locale) ?? apiProblem(err, locale).text ?? t("sso.admin.saveFailed")),
            },
          );
        }}
      >
        <Field label={t("sso.admin.claim")} htmlFor="map-claim">
          <SelectField id="map-claim" value={claim} onChange={(e) => setClaim(e.target.value === "group" ? "group" : "role")}>
            <option value="role">{t("sso.admin.claimRole")}</option>
            <option value="group">{t("sso.admin.claimGroup")}</option>
          </SelectField>
        </Field>
        <Field label={claim === "role" ? t("sso.admin.valueRole") : t("sso.admin.valueGroup")} htmlFor="map-value">
          <Input id="map-value" value={value} onChange={(e) => setValue(e.target.value)} placeholder={claim === "role" ? "SmartSched.Planner" : ""} className="font-mono" autoComplete="off" spellCheck={false} data-testid="map-value" />
        </Field>
        <Field label={t("sso.admin.mapTo")} htmlFor="map-role">
          <SelectField id="map-role" value={role} onChange={(e) => setRole(e.target.value)} data-testid="map-role">
            <option value="">—</option>
            {(roles.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {roleLabel(t, r)}
              </option>
            ))}
          </SelectField>
        </Field>
        <BusyButton type="submit" variant="outline" busy={add.isPending} busyLabel={t("busy.saving")} data-testid="map-add">
          <Plus aria-hidden />
          {t("sso.admin.mappingAdd")}
        </BusyButton>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}
