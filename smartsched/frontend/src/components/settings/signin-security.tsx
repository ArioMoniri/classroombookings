"use client";
/**
 * Ayarlar › Giriş güvenliği (`/settings?tab=signin-security`, docs/design/v3/auth.md §9; AUX-11, AU-B API.md §8
 * `GET/PUT /admin/auth/mfa-policy`, permission `setup.authentication`). One card, one save:
 * - İki aşamalı doğrulama: Kapalı · İsteğe bağlı · Zorunlu (segmented, glass-morph thumb) + the help;
 * - Zorunlu only: the role chips (default Yönetici, wrap, 44 px on touch) with "Tüm roller", the grace 7 / 14 / 30
 *   days and the live sentence (with the counts once AU-B adds them to the policy answer, ask);
 * - Geçiş anahtarları (switch) with the nested "Parolasız girişe de izin ver";
 * - Gelişmiş › "Bu cihazı hatırla": Kapalı · 7 gün · 30 gün;
 * - the SSO note, and the self-scope banner with "Şimdi kur" when the rule covers the admin who has no 2FA.
 * Saving Zorunlu (from another value) and Kapalı (from another value) confirm first; "İsteğe bağlı kalsın" keeps
 * optional. On phones the save is a capsule above the tab bar (MOBILE M-05), as on the solver tab.
 */
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { MFA_ROLES, useMfaPolicy, useMfaStatus, useSaveMfaPolicy, type MfaPolicy, type MfaPolicyValue } from "@/lib/api/auth-security";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { shortDate } from "@/components/profile/security/format";
import "@/components/auth/auth.css";

export const GRACE_CHOICES = [7, 14, 30] as const;
export const REMEMBER_CHOICES = [0, 7, 30] as const;

/** The fields this tab writes (a subset of the policy answer). */
export type PolicyForm = Pick<MfaPolicy, "mfa_policy" | "mfa_roles" | "mfa_grace_days" | "passkeys_enabled" | "passkey_first_factor" | "trusted_device_days">;

export function toForm(p: MfaPolicy): PolicyForm {
  return { mfa_policy: p.mfa_policy, mfa_roles: p.mfa_roles.length ? p.mfa_roles : ["ADMIN"], mfa_grace_days: p.mfa_grace_days, passkeys_enabled: p.passkeys_enabled, passkey_first_factor: p.passkey_first_factor, trusted_device_days: p.trusted_device_days };
}

/** Only the changed fields are sent; passwordless is off whenever passkeys are off. */
export function policyDiff(saved: PolicyForm, form: PolicyForm): Partial<PolicyForm> {
  const out: Partial<PolicyForm> = {};
  const f = { ...form, passkey_first_factor: form.passkeys_enabled && form.passkey_first_factor };
  (Object.keys(f) as (keyof PolicyForm)[]).forEach((k) => {
    const a = saved[k];
    const b = f[k];
    if (JSON.stringify(Array.isArray(a) ? [...a].sort() : a) !== JSON.stringify(Array.isArray(b) ? [...b].sort() : b)) (out as Record<string, unknown>)[k] = b;
  });
  return out;
}

/** The confirmation a save needs (§9): turning on Zorunlu, or turning 2FA off. */
export function confirmFor(saved: PolicyForm, form: PolicyForm): "required" | "off" | null {
  if (form.mfa_policy === "required_for_roles" && saved.mfa_policy !== "required_for_roles") return "required";
  if (form.mfa_policy === "off" && saved.mfa_policy !== "off") return "off";
  return null;
}

export function graceEnd(days: number, now: number = Date.now()): string {
  return new Date(now + days * 86_400_000).toISOString();
}

export function SigninSecuritySettings() {
  const q = useMfaPolicy();
  const { t } = useI18n();
  if (q.isLoading)
    return (
      <Card variant="glass">
        <CardContent className="flex flex-col gap-3 py-5">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  if (!q.data) return <Alert tone="error">{t("auth.policy.loadFailed")}</Alert>;
  return <PolicyEditor key={q.dataUpdatedAt} saved={toForm(q.data)} counts={{ required_people: q.data.required_people, enrolled_people: q.data.enrolled_people }} />;
}

function PolicyEditor({ saved, counts }: { saved: PolicyForm; counts: { required_people?: number; enrolled_people?: number } }) {
  const { t, locale } = useI18n();
  const save = useSaveMfaPolicy();
  const me = useMfaStatus().data;
  const [form, setForm] = useState<PolicyForm>(saved);
  const [advanced, setAdvanced] = useState(saved.trusted_device_days !== 30);
  const [ask, setAsk] = useState<"required" | "off" | null>(null);
  const [rolesError, setRolesError] = useState(false);
  const ids = { mfa: useId(), help: useId(), roles: useId(), grace: useId(), pk: useId(), pkHelp: useId(), pwless: useId(), remember: useId(), adv: useId() };
  const diff = useMemo(() => policyDiff(saved, form), [saved, form]);
  const dirty = Object.keys(diff).length > 0;
  const required = form.mfa_policy === "required_for_roles";
  const set = <K extends keyof PolicyForm>(k: K, v: PolicyForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const doSave = async (f: PolicyForm = form) => {
    setAsk(null);
    try {
      await save.mutateAsync(policyDiff(saved, f));
      toast.success(t("auth.policy.saved"));
    } catch {
      toast.error(t("auth.policy.saveFailed"));
    }
  };

  const onSave = () => {
    if (required && form.mfa_roles.length === 0) return setRolesError(true);
    const c = confirmFor(saved, form);
    if (c) return setAsk(c);
    void doSave();
  };

  const toggleRole = (role: string, on: boolean) => {
    setRolesError(false);
    set("mfa_roles", on ? [...new Set([...form.mfa_roles, role])] : form.mfa_roles.filter((r) => r !== role));
  };
  const allRoles = MFA_ROLES.every((r) => form.mfa_roles.includes(r));

  // §9 banner: the saved rule covers this admin and they have no second factor yet
  const meUncovered = me && me.required && !me.totp.enabled && me.passkeys.length === 0 && me.account_type !== "sso";
  const graceOptions = (GRACE_CHOICES as readonly number[]).includes(form.mfa_grace_days) ? GRACE_CHOICES : [...GRACE_CHOICES, form.mfa_grace_days].sort((a, b) => a - b);
  // AU-18 counts describe the SAVED policy: shown while the form still has its Zorunlu and roles
  const sameScope = saved.mfa_policy === "required_for_roles" && JSON.stringify([...saved.mfa_roles].sort()) === JSON.stringify([...form.mfa_roles].sort());
  const sentence =
    sameScope && typeof counts.required_people === "number" && typeof counts.enrolled_people === "number"
      ? t("auth.policy.liveSentence", { n: counts.required_people, m: counts.enrolled_people, date: shortDate(graceEnd(form.mfa_grace_days), locale) })
      : t("auth.policy.graceSentence", { date: shortDate(graceEnd(form.mfa_grace_days), locale) });

  return (
    <Card variant="glass" data-testid="signin-security">
      <CardHeader>
        <CardTitle>{t("auth.policy.title")}</CardTitle>
        <CardDescription>{t("auth.policy.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {meUncovered ? (
          <Alert tone="warning" data-testid="policy-self-banner">
            <span className="flex flex-wrap items-center justify-between gap-3">
              <span>{me.grace_until ? t("auth.policy.selfBanner", { date: shortDate(me.grace_until, locale) }) : t("auth.policy.selfBannerNow")}</span>
              <Link href="/profile#security" className={cn(buttonVariants({ variant: "secondary", shape: "rect", size: "md" }))} data-testid="policy-setup-now">
                {t("auth.policy.setupNow")}
              </Link>
            </span>
          </Alert>
        ) : null}

        <fieldset className="flex flex-col gap-2">
          <legend id={ids.mfa} className="mb-2 type-headline text-label-1">
            {t("auth.policy.mfa")}
          </legend>
          <SegmentedControl<MfaPolicyValue>
            semantics="radiogroup"
            fill
            size="lg"
            aria-labelledby={ids.mfa}
            aria-describedby={ids.help}
            value={form.mfa_policy}
            onValueChange={(v) => set("mfa_policy", v)}
            options={[
              { value: "off", label: t("auth.policy.off"), testId: "policy-off" },
              { value: "optional", label: t("auth.policy.optional"), testId: "policy-optional" },
              { value: "required_for_roles", label: t("auth.policy.required"), testId: "policy-required" },
            ]}
            data-testid="policy-mfa"
          />
          <p id={ids.help} className="type-footnote text-label-2">
            {t("auth.policy.help")}
          </p>
        </fieldset>

        {required ? (
          <div className="auth-panel-in flex flex-col gap-5" data-testid="policy-required-panel">
            <fieldset className="flex flex-col gap-2">
              <legend id={ids.roles} className="mb-1 type-callout font-semibold text-label-1">
                {t("auth.policy.roles")}
              </legend>
              <div className="flex flex-wrap gap-2 pointer-coarse:gap-1" role="group" aria-labelledby={ids.roles} data-testid="policy-roles">
                {MFA_ROLES.map((r) => (
                  <Chip key={r} selected={form.mfa_roles.includes(r)} onSelectedChange={(on) => toggleRole(r, on)} className="pointer-coarse:min-h-11" data-testid={`policy-role-${r}`}>
                    {t(`auth.policy.role${r}` as MessageKey)}
                  </Chip>
                ))}
                <Chip selected={allRoles} onSelectedChange={(on) => (setRolesError(false), set("mfa_roles", on ? [...MFA_ROLES] : ["ADMIN"]))} className="pointer-coarse:min-h-11" data-testid="policy-role-all">
                  {t("auth.policy.allRoles")}
                </Chip>
              </div>
              <p className="type-footnote text-label-2">{t("auth.policy.rolesHint")}</p>
              {rolesError ? (
                <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="policy-roles-error">
                  {t("auth.policy.rolesNone")}
                </p>
              ) : null}
            </fieldset>
            <fieldset className="flex flex-col gap-2">
              <legend id={ids.grace} className="mb-1 type-callout font-semibold text-label-1">
                {t("auth.policy.grace")}
              </legend>
              <SegmentedControl<string>
                semantics="radiogroup"
                fill
                aria-labelledby={ids.grace}
                value={String(form.mfa_grace_days)}
                onValueChange={(v) => set("mfa_grace_days", Number(v))}
                options={graceOptions.map((d) => ({ value: String(d), label: t("auth.policy.graceDays", { n: d }), testId: `policy-grace-${d}` }))}
                data-testid="policy-grace"
              />
              <p className="type-callout text-label-1" aria-live="polite" data-testid="policy-sentence">
                {sentence}
              </p>
            </fieldset>
          </div>
        ) : null}

        <div className="flex flex-col gap-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <label htmlFor={ids.pk} className="type-headline text-label-1">
                {t("auth.policy.passkeys")}
              </label>
              <p id={ids.pkHelp} className="type-footnote text-label-2">
                {t("auth.policy.passkeysHelp")}
              </p>
            </div>
            <Switch id={ids.pk} checked={form.passkeys_enabled} onCheckedChange={(v) => set("passkeys_enabled", Boolean(v))} aria-describedby={ids.pkHelp} data-testid="policy-passkeys" />
          </div>
          {form.passkeys_enabled ? (
            <label htmlFor={ids.pwless} className="ml-1 flex min-h-11 cursor-pointer items-center gap-3 border-l-2 border-(--hairline) pl-4 type-callout text-label-1">
              <Checkbox id={ids.pwless} checked={form.passkey_first_factor} onCheckedChange={(v) => set("passkey_first_factor", Boolean(v))} data-testid="policy-passwordless" />
              {t("auth.policy.passwordless")}
            </label>
          ) : null}
        </div>

        <div className="flex flex-col gap-3">
          <Button type="button" variant="ghost" shape="rect" className="w-fit" aria-expanded={advanced} aria-controls={ids.adv} onClick={() => setAdvanced((v) => !v)} data-testid="policy-advanced">
            {t("auth.policy.advanced")}
            <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast) motion-reduce:transition-none", advanced && "rotate-180")} />
          </Button>
          {advanced ? (
            <fieldset id={ids.adv} className="auth-panel-in flex flex-col gap-2">
              <legend id={ids.remember} className="mb-1 type-callout font-semibold text-label-1">
                {t("auth.policy.remember")}
              </legend>
              <SegmentedControl<string>
                semantics="radiogroup"
                aria-labelledby={ids.remember}
                value={String(form.trusted_device_days)}
                onValueChange={(v) => set("trusted_device_days", Number(v))}
                options={REMEMBER_CHOICES.map((d) => ({ value: String(d), label: d === 0 ? t("auth.policy.rememberOff") : t("auth.policy.rememberDays", { n: d }), testId: `policy-remember-${d}` }))}
                data-testid="policy-remember"
              />
              <p className="type-footnote text-label-2">{t("auth.policy.rememberHelp")}</p>
            </fieldset>
          ) : null}
        </div>

        <p className="type-footnote text-label-2" data-testid="policy-sso-note">
          {t("auth.policy.ssoNote")}
        </p>

        {/* phones (MOBILE M-05): the save is a capsule above the tab bar; the card keeps room for it */}
        <div className="flex items-center justify-end gap-3 max-sm:pointer-events-none max-sm:fixed max-sm:inset-x-0 max-sm:bottom-[calc(5.25rem+env(safe-area-inset-bottom))] max-sm:z-30 max-sm:px-4" data-testid="policy-save-row">
          {dirty ? (
            <span className="type-footnote text-label-2 max-sm:sr-only" aria-live="polite">
              {t("auth.policy.unsaved")}
            </span>
          ) : null}
          <div className="max-sm:pointer-events-auto max-sm:rounded-full max-sm:bg-(--mat-thick-solid) max-sm:p-1 max-sm:shadow-elev-3 max-sm:edge-hairline">
            <BusyButton type="button" shape="rect" className="pointer-coarse:h-11 max-sm:rounded-full max-sm:px-6" busy={save.isPending} busyLabel={t("busy.saving")} disabled={!dirty} onClick={onSave} data-testid="policy-save">
              {t("auth.policy.save")}
            </BusyButton>
          </div>
        </div>
        <div aria-hidden className="h-14 sm:hidden" />
      </CardContent>

      <Dialog open={ask !== null} onOpenChange={(o) => (!o ? setAsk(null) : undefined)}>
        <DialogContent role="alertdialog" data-testid="policy-confirm">
          <DialogHeader>
            <DialogTitle>{ask === "off" ? t("auth.policy.confirmOffTitle") : t("auth.policy.confirmRequiredTitle")}</DialogTitle>
            <DialogDescription>{ask === "off" ? t("auth.policy.confirmOff") : t("auth.policy.confirmRequired")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            {ask === "off" ? (
              <Button
                type="button"
                variant="secondary"
                shape="rect"
                onClick={() => {
                  set("mfa_policy", "optional");
                  setAsk(null);
                }}
                data-testid="policy-keep-optional"
              >
                {t("auth.policy.keepOptional")}
              </Button>
            ) : (
              <Button type="button" variant="secondary" shape="rect" onClick={() => setAsk(null)}>
                {t("auth.admin.cancel")}
              </Button>
            )}
            <BusyButton type="button" variant={ask === "off" ? "destructive" : "default"} shape="rect" busy={save.isPending} busyLabel={t("busy.saving")} onClick={() => void doSave()} data-testid="policy-confirm-save">
              {t("auth.policy.save")}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
