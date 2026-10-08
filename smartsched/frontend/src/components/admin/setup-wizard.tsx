"use client";
/**
 * /setup — the first-run wizard (CRBS `install`): the server requirements (`Install::check_requirements`,
 * `GET /org/setup/requirements`), then organisation name, time zone and the first administrator
 * (`Install::info`). Only shown while `GET /org/setup-status` says setup is needed; afterwards it points to
 * sign-in. Any requirement in error blocks the wizard, as in CRBS; `POST /org/setup` answers 409 then, and
 * the wizard returns to the checklist with the blocking checks marked. Back keeps what was typed.
 */
import { Check, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation, useSetupRequirements, useSetupStatus } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, Loading, SelectField } from "./kit";
import { PublicCard } from "./public-card";
import { RequirementsList } from "./requirements-list";
import { blockedKeysFromError, summariseRequirements } from "./requirements-model";

const TIMEZONES = ["Europe/Istanbul", "Europe/London", "Europe/Berlin", "UTC", "Asia/Baku", "Asia/Dubai", "America/New_York"];

export function SetupWizard() {
  const { t } = useI18n();
  const status = useSetupStatus();
  const setupRequired = !!status.data?.setup_required;
  const reqs = useSetupRequirements(setupRequired);
  const req = summariseRequirements(reqs.data);
  const [blocked, setBlocked] = useState<string[]>([]);
  // steps: 0 requirements, 1 institution, 2 administrator, 3 done
  const [step, setStep] = useState(0);
  const [org, setOrg] = useState({ name: "", tz: "Europe/Istanbul" });
  const [admin, setAdmin] = useState({ email: "", username: "", display: "", password: "", again: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const { ref, shake } = useShake<HTMLDivElement>();
  const m = useCrbsMutation(() =>
    crbs.org.setup({ org_name: org.name.trim(), timezone: org.tz, admin_email: admin.email.trim(), admin_username: admin.username.trim() || null, admin_password: admin.password, admin_displayname: admin.display.trim() || null }),
  );
  const steps = [t("crbs.setup.stepCheck"), t("crbs.setup.stepOrg"), t("crbs.setup.stepAdmin"), t("crbs.setup.stepDone")];

  if (status.isLoading) return <PublicCard title={t("crbs.setup.title")}><Loading /></PublicCard>;
  if (status.data && !status.data.setup_required && !done) {
    return (
      <PublicCard title={t("crbs.setup.title")} lead={t("crbs.setup.already")}>
        <Button nativeButton={false} render={<Link href="/login" />}>
          {t("crbs.setup.toLogin")}
        </Button>
      </PublicCard>
    );
  }

  const fail = (msg: string) => {
    setError(msg);
    shake();
  };
  return (
    <PublicCard title={t("crbs.setup.title")} lead={t("crbs.setup.lead")} wide>
      <ol className="mb-5 flex gap-2" aria-label={t("crbs.setup.progress")}>
        {steps.map((s, i) => (
          <li key={s} aria-current={i === step ? "step" : undefined} className={cn("flex items-center gap-1.5 type-footnote", i === step ? "font-semibold text-label-1" : "text-label-3")}>
            <span className={cn("flex size-5 items-center justify-center rounded-full type-caption", i < step || done ? "bg-tint text-tint-foreground" : i === step ? "bg-tint-soft text-tint-text" : "bg-fill-2")}>{i < step || done ? <Check className="size-3" aria-hidden /> : i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <div ref={ref} className="t-input flex flex-col gap-3">
        {step === 0 ? (
          <>
            <p className="type-callout text-label-2">{t("crbs.setup.req.lead")}</p>
            <RequirementsList query={reqs} highlight={blocked} compact />
          </>
        ) : step === 1 ? (
          <>
            <Field label={t("crbs.org.name")} htmlFor="su-org" hint={t("crbs.setup.orgHint")}>
              <Input id="su-org" autoFocus value={org.name} onChange={(e) => setOrg((o) => ({ ...o, name: e.target.value }))} />
            </Field>
            <Field label={t("crbs.org.timezone")} htmlFor="su-tz">
              <SelectField id="su-tz" value={org.tz} onChange={(e) => setOrg((o) => ({ ...o, tz: e.target.value }))}>
                {TIMEZONES.map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
              </SelectField>
            </Field>
          </>
        ) : step === 2 && !done ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("crbs.users.email")} htmlFor="su-email">
              <Input id="su-email" type="email" autoComplete="email" value={admin.email} onChange={(e) => setAdmin((a) => ({ ...a, email: e.target.value }))} />
            </Field>
            <Field label={t("crbs.users.username")} htmlFor="su-user" hint={t("crbs.setup.optional")}>
              <Input id="su-user" autoComplete="username" value={admin.username} onChange={(e) => setAdmin((a) => ({ ...a, username: e.target.value }))} />
            </Field>
            <Field label={t("crbs.users.displayname")} htmlFor="su-display" className="sm:col-span-2">
              <Input id="su-display" value={admin.display} onChange={(e) => setAdmin((a) => ({ ...a, display: e.target.value }))} />
            </Field>
            <Field label={t("crbs.users.password")} htmlFor="su-pw" hint={t("crbs.users.passwordHint")}>
              <Input id="su-pw" type="password" autoComplete="new-password" value={admin.password} onChange={(e) => setAdmin((a) => ({ ...a, password: e.target.value }))} />
            </Field>
            <Field label={t("crbs.reset.again")} htmlFor="su-pw2">
              <Input id="su-pw2" type="password" autoComplete="new-password" value={admin.again} onChange={(e) => setAdmin((a) => ({ ...a, again: e.target.value }))} />
            </Field>
          </div>
        ) : (
          <Alert tone="success" title={t("crbs.setup.doneTitle")}>
            {t("crbs.setup.doneBody", { email: admin.email })}
          </Alert>
        )}
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
      <div className="mt-5 flex justify-between gap-2">
        {(step === 1 || step === 2) && !done ? (
          <Button variant="ghost" onClick={() => setStep(step - 1)}>
            {t("crbs.common.back")}
          </Button>
        ) : (
          <span />
        )}
        {step === 0 ? (
          <Button disabled={!req.ok || reqs.isFetching} onClick={() => (setError(null), setBlocked([]), setStep(1))} data-testid="setup-requirements-next">
            {t("crbs.setup.next")}
          </Button>
        ) : step === 1 ? (
          <Button onClick={() => (org.name.trim() ? (setError(null), setStep(2)) : fail(t("crbs.setup.needOrg")))}>{t("crbs.setup.next")}</Button>
        ) : done ? (
          <Button nativeButton={false} render={<Link href="/login?next=/admin" />}>
            {t("crbs.setup.toLogin")}
          </Button>
        ) : (
          <Button
            disabled={m.isPending}
            onClick={() => {
              if (!admin.email.includes("@")) return fail(t("crbs.setup.needEmail"));
              if (admin.password.length < 8) return fail(t("crbs.reset.tooShort"));
              if (admin.password !== admin.again) return fail(t("crbs.reset.mismatch"));
              setError(null);
              m.mutate(undefined, {
                onSuccess: () => (setDone(true), setStep(3)),
                onError: (e) => {
                  const err = crbsError(e);
                  const keys = err.status === 409 ? blockedKeysFromError(err.message) : [];
                  if (keys.length) {
                    // a requirement broke after the first check (CRBS refuses too): back to the checklist
                    setBlocked(keys);
                    setError(null);
                    setStep(0);
                    void reqs.refetch();
                    return;
                  }
                  if (err.status === 409) void status.refetch();
                  fail(bookingErrorMessage(err, t));
                },
              });
            }}
          >
            {m.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.setup.finish")}
          </Button>
        )}
      </div>
    </PublicCard>
  );
}
