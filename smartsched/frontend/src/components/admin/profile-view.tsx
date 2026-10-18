"use client";
/**
 * /profile (CRBS `Profile`): own e-mail, names, display name, extension and language (per user, as in
 * CRBS), and the password change (current password required unless an administrator forced a change).
 * Identity frontend (2026-10-16): "Microsoft hesabı" (link / unlink, sign-in.md §13–§14), "Bağlı kanallar"
 * (Telegram, SMS / WhatsApp, browser push; docs/deploy/notification-channels.md) and the notification
 * preferences panel of the approval UI (components/notifications/preferences-panel.tsx).
 */
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input, useShake } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { crbs, crbsError, useCrbsMe, useCrbsMutation, useOrgPublic, useProfile, type Profile } from "@/lib/api/crbs";
import { LOCALE_INFO, displayLocale, isLocale, translate } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useIsCompact } from "@/components/bookings/use-is-phone";
import { roleLabel } from "@/lib/i18n/roles";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, PageTitle, SectionTitle, SelectField } from "./kit";
import { MyChannels } from "@/components/channels/my-channels";
import { MicrosoftAccountSection, ProfileSsoNotice } from "@/components/identity/profile-microsoft";
import { SecuritySection } from "@/components/profile/security/security-section";
import { NotificationPreferencesPanel } from "@/components/notifications/preferences-panel";
import { PrivacySection } from "@/components/privacy/privacy-section";
import { CalendarConnectionsSection } from "@/components/settings/calendar-connections";
import { CalendarExportSection } from "@/components/calendar-export/calendar-export-section";
import { MyAiUsage } from "@/components/admin/ai/my-ai-usage";
import { HelperMemorySection } from "@/components/helper/memory/memory-section";
import { MyStats } from "@/components/profile/my-stats";
import { MyLoad } from "@/components/profile/my-load";
import { ChartPatternsToggle } from "@/components/charts/chart-patterns-toggle";
import { mfaErrorCode, usePasswordMinLength } from "@/lib/api/auth-security";
import { refusalBody } from "@/lib/api/error-text";

/** language names in themselves (Turkish, English); a legacy stored code (`de`) reads as English */
const langLabel = (code: string | null | undefined) => {
  const shown = displayLocale(code);
  return shown ? LOCALE_INFO[shown].name : "";
};

export function ProfileView() {
  const { t } = useI18n();
  const q = useProfile();
  const me = useCrbsMe();
  // mobile-a fix 15: below lg (phones and tablets, where the tab bar shows) the save sits in the sticky bar
  const compact = useIsCompact();
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageTitle title={t("crbs.profile.title")} subtitle={q.data ? [q.data.username ?? q.data.email, q.data.role_name ? roleLabel(t, { code: q.data.role, name: q.data.role_name }) : null].filter(Boolean).join(" · ") : undefined} />
      <ProfileSsoNotice />
      {q.isLoading ? <ProfileFormSkeleton phone={compact} /> : q.data ? <ProfileForm key={q.data.id} data={q.data} phone={compact} /> : <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>}
      <MicrosoftAccountSection />
      {/* AUX-06/07 (docs/design/v3/auth.md §6): Giriş ve güvenlik — 2FA, passkeys, remembered devices, recent sign-ins */}
      <SecuritySection />
      <section aria-labelledby="pf-channels" id="channels" className="scroll-mt-20">
        <SectionTitle id="pf-channels">{t("channels.me.title")}</SectionTitle>
        <Card variant="glass" className="gap-3 px-4">
          <p className="type-callout text-label-2">{t("channels.me.lead")}</p>
          <MyChannels email={q.data?.email ?? me.data?.email ?? null} />
        </Card>
      </section>
      <CalendarExportSection />
      {/* Google Calendar / Microsoft 365 push: connect, choose the calendar, disconnect */}
      <CalendarConnectionsSection />
      {/* CH-11: my booking numbers, and an academician's weekly teaching load (tiles + BarList, no chart library) */}
      <MyStats showTitle />
      <MyLoad />
      {/* wave 3 W3-AI: my AI usage against my limit (hidden for people who never used AI and have no limit) */}
      <section id="ai-usage" className="scroll-mt-20" data-tour="profile-ai-usage">
        <MyAiUsage />
      </section>
      {/* HX-08: Profil › Yardımcı — the helper's notes and history, all deletable */}
      <HelperMemorySection />
      {/* the approval UI's panel: which event reaches you on which channel */}
      <section id="notifications" className="scroll-mt-20" data-tour="profile-notifications">
        <NotificationPreferencesPanel />
      </section>
      {/* CH-03: Grafiklerde desen (hatch patterns in charts, per user, default off) */}
      <ChartPatternsToggle userId={me.data?.id} />
      <PasswordForm forced={!!me.data?.force_password_reset} />
      {/* A4 KVKK: the privacy notice, consents and data requests (wave-2 UI) */}
      <PrivacySection />
      <p className="type-callout text-label-2">
        {t("crbs.profile.calendar")}{" "}
        <Link href="/my-bookings" className="font-medium text-tint-text underline-offset-4 hover:underline">
          {t("crbs.nav.myBookings")}
        </Link>
      </p>
      {/* MOBILE M-05: on a phone the details form's save button stays in reach above the tab bar while the whole page
          scrolls (the form itself is `#profile-form`); on wider screens it sits in the form */}
      {compact && q.data ? (
        <div className="sticky bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-10 -mx-4 flex px-4 py-2 glass-chrome" data-testid="profile-save-bar">
          <Button type="submit" form="profile-form" data-testid="profile-save">
            {t("crbs.common.save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * mobile-a fix 1 (CLS 0.45 phone / 0.73 tablet): while the profile loads, hold the details form's space with the same
 * six label + field rows (and the two hint lines), so the sections below do not jump when the form arrives.
 */
function ProfileFormSkeleton({ phone }: { phone: boolean }) {
  const { t } = useI18n();
  return (
    <section aria-labelledby="pf-details" aria-busy="true" data-testid="profile-skeleton">
      <SectionTitle id="pf-details">{t("crbs.profile.details")}</SectionTitle>
      <Card variant="glass" className="gap-3 px-4">
        <span className="sr-only" role="status">{t("crbs.common.loading")}</span>
        <div className="grid max-w-[360px] gap-3">
          {[false, false, true, false, false, true].map((hint, i) => (
            <div key={i} className="flex flex-col gap-1.5" data-slot="skeleton-field">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-(--control-h-md) w-full" />
              {hint ? <Skeleton className="h-4 w-48" /> : null}
            </div>
          ))}
        </div>
        {phone ? null : <Skeleton className="h-(--control-h-md) w-24" />}
      </Card>
    </section>
  );
}

function ProfileForm({ data, phone }: { data: Profile; phone: boolean }) {
  const { t, locale, setLocale } = useI18n();
  const org = useOrgPublic();
  const qc = useQueryClient();
  // P18-LANG (TR + EN only): a stored legacy code (`de`, from a CRBS import) is shown as English and kept: the
  // save sends `language` only when the user picks another one
  const storedLanguage = data.language ?? "";
  const legacyLanguage = storedLanguage !== "" && !isLocale(storedLanguage) ? storedLanguage : null;
  const initialLanguage = displayLocale(storedLanguage) ?? "";
  const [f, setF] = useState({ email: data.email ?? "", firstname: data.firstname ?? "", lastname: data.lastname ?? "", displayname: data.displayname ?? "", ext: data.ext ?? "", language: initialLanguage });
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: string) => setF((p) => ({ ...p, [k]: v }));
  const save = useCrbsMutation(
    () => crbs.auth.putProfile({ email: f.email.trim() || null, firstname: f.firstname.trim() || null, lastname: f.lastname.trim() || null, displayname: f.displayname.trim() || null, ext: f.ext.trim() || null, ...(f.language && f.language !== initialLanguage ? { language: f.language } : {}) }),
    [["crbs", "profile"], ["crbs", "me"], ["me"]],
  );
  const languages = [...new Set((org.data?.languages ?? ["tr", "en"]).map((l) => displayLocale(l)).filter((l) => l !== null))];
  return (
    <section aria-labelledby="pf-details">
      <SectionTitle id="pf-details">{t("crbs.profile.details")}</SectionTitle>
      <Card variant="glass" className="gap-3 px-4">
        <form
          id="profile-form"
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            save.mutate(undefined, {
              onSuccess: (p) => {
                const shown = displayLocale(p.language);
                if (shown) setLocale(shown);
                // round-1 R1-A-30: this closure's t() is the previous language's; a changed language is saved in its own
                toast.success(shown && shown !== locale ? translate(shown, "crbs.common.saved") : t("crbs.common.saved"));
                void qc.invalidateQueries({ queryKey: ["me"] });
              },
              onError: (err) => setError(bookingErrorMessage(crbsError(err), t)),
            });
          }}
        >
          {/* UI/UX review §3: one column of 360 px fields */}
          <div className="grid max-w-[360px] gap-3">
            <Field label={t("crbs.users.firstname")} htmlFor="pf-first">
              <Input id="pf-first" value={f.firstname} onChange={(e) => set("firstname", e.target.value)} />
            </Field>
            <Field label={t("crbs.users.lastname")} htmlFor="pf-last">
              <Input id="pf-last" value={f.lastname} onChange={(e) => set("lastname", e.target.value)} />
            </Field>
            <Field label={t("crbs.users.displayname")} htmlFor="pf-display" hint={t("crbs.profile.displayHint")}>
              <Input id="pf-display" value={f.displayname} onChange={(e) => set("displayname", e.target.value)} />
            </Field>
            <Field label={t("crbs.users.email")} htmlFor="pf-email">
              <Input id="pf-email" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} />
            </Field>
            <Field label={t("crbs.users.ext")} htmlFor="pf-ext">
              <Input id="pf-ext" value={f.ext} onChange={(e) => set("ext", e.target.value)} />
            </Field>
            <Field label={t("crbs.profile.language")} htmlFor="pf-lang" hint={legacyLanguage && f.language === initialLanguage ? t("crbs.profile.languageLegacy", { code: legacyLanguage }) : t("crbs.profile.languageHint")}>
              {/* R2-A-19 (owner decision 2026-10-15, decided 2026-10-17): Türkçe and English only; a stored institution
                  default (no language) reads as the institution's language until the user picks one */}
              <SelectField id="pf-lang" value={f.language || (displayLocale(org.data?.default_language) ?? "tr")} onChange={(e) => set("language", e.target.value)} data-testid="profile-language">
                {languages.map((l) => (
                  <option key={l} value={l} lang={l}>
                    {langLabel(l)}
                  </option>
                ))}
              </SelectField>
            </Field>
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          {phone ? null : (
            <div>
              <Button type="submit" disabled={save.isPending} data-testid="profile-save" aria-busy={save.isPending || undefined}>
                <BusyLabel busy={save.isPending} label={t("busy.saving")}>
                {t("crbs.common.save")}</BusyLabel>
              </Button>
            </div>
          )}
        </form>
      </Card>
    </section>
  );
}

function PasswordForm({ forced }: { forced: boolean }) {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { ref, shake } = useShake<HTMLDivElement>();
  // AUX-F (owner Q2, AU-B API.md §10): 12 characters, or 8 with 2FA, from GET /auth/mfa; a 422 password_too_short
  // moves the rule to the backend's min_length
  const serverMin = usePasswordMinLength();
  const [refusedMin, setRefusedMin] = useState<number | null>(null);
  const min = refusedMin ?? serverMin;
  const m = useCrbsMutation(() => crbs.auth.changePassword(forced ? current || null : current, next), [["crbs", "me"], ["me"]]);
  return (
    <section aria-labelledby="pf-pw">
      <SectionTitle id="pf-pw">{t("crbs.profile.password")}</SectionTitle>
      <Card variant="glass" className="gap-3 px-4">
        {forced ? <Alert tone="warning">{t("crbs.profile.forced")}</Alert> : null}
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (next.length < min) return (setError(t("auth.setPassword.short", { n: min })), shake());
            if (next !== again) return (setError(t("crbs.reset.mismatch")), shake());
            m.mutate(undefined, {
              onSuccess: (res) => {
                // B-AUTH-11 revoked the session and signing in again failed: say so and go to the login page
                if (res && typeof res === "object" && "signedOut" in res && res.signedOut) {
                  toast.message(t("wave1.session.password"));
                  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a full load drops every cached query of the dead session
                  window.location.assign(`/login?next=${encodeURIComponent("/profile")}&reason=password`);
                  return;
                }
                toast.success(t("crbs.profile.passwordChanged"));
                setCurrent("");
                setNext("");
                setAgain("");
              },
              onError: (err) => {
                if (mfaErrorCode(err) === "password_too_short") {
                  const need = refusalBody(err)?.min_length;
                  if (typeof need === "number") setRefusedMin(need);
                  setError(t("auth.setPassword.short", { n: typeof need === "number" ? need : min }));
                  return shake();
                }
                const ce = crbsError(err);
                setError(ce.status === 403 ? t("crbs.profile.wrongCurrent") : ce.status === 422 ? t("crbs.profile.samePassword") : bookingErrorMessage(ce, t));
                shake();
              },
            });
          }}
        >
          <div ref={ref} className="t-input grid max-w-[360px] gap-3">
            <Field label={t("crbs.profile.current")} htmlFor="pw-cur">
              <Input id="pw-cur" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            </Field>
            <Field label={t("crbs.users.newPassword")} htmlFor="pw-new" hint={t("auth.setPassword.hintChange", { n: min })}>
              <Input id="pw-new" type="password" autoComplete="new-password" minLength={min} {...{ passwordrules: `minlength: ${min};` }} value={next} onChange={(e) => setNext(e.target.value)} />
            </Field>
            <Field label={t("crbs.reset.again")} htmlFor="pw-again">
              <Input id="pw-again" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
            </Field>
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div>
            <Button type="submit" variant="outline" disabled={!next || m.isPending}>
              {t("crbs.profile.changePassword")}
            </Button>
          </div>
        </form>
      </Card>
    </section>
  );
}
