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
import { crbs, crbsError, useCrbsMe, useCrbsMutation, useOrgPublic, useProfile, type Profile } from "@/lib/api/crbs";
import { LOCALE_INFO, displayLocale, isLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { MyChannels } from "@/components/channels/my-channels";
import { MicrosoftAccountSection, ProfileSsoNotice } from "@/components/identity/profile-microsoft";
import { NotificationPreferencesPanel } from "@/components/notifications/preferences-panel";
import { PrivacySection } from "@/components/privacy/privacy-section";

/** language names in themselves (Turkish, English); a legacy stored code (`de`) reads as English */
const langLabel = (code: string | null | undefined) => {
  const shown = displayLocale(code);
  return shown ? LOCALE_INFO[shown].name : "";
};

export function ProfileView() {
  const { t } = useI18n();
  const q = useProfile();
  const me = useCrbsMe();
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageTitle title={t("crbs.profile.title")} subtitle={q.data ? [q.data.username ?? q.data.email, q.data.role_name].filter(Boolean).join(" · ") : undefined} />
      <ProfileSsoNotice />
      {q.isLoading ? <Loading /> : q.data ? <ProfileForm key={q.data.id} data={q.data} /> : <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>}
      <MicrosoftAccountSection />
      <section aria-labelledby="pf-channels" id="channels" className="scroll-mt-20">
        <SectionTitle id="pf-channels">{t("channels.me.title")}</SectionTitle>
        <Card variant="glass" className="gap-3 px-4">
          <p className="type-callout text-label-2">{t("channels.me.lead")}</p>
          <MyChannels email={q.data?.email ?? me.data?.email ?? null} />
        </Card>
      </section>
      {/* the approval UI's panel: which event reaches you on which channel */}
      <section id="notifications" className="scroll-mt-20">
        <NotificationPreferencesPanel />
      </section>
      <PasswordForm forced={!!me.data?.force_password_reset} />
      {/* A4 KVKK: the privacy notice, consents and data requests (wave-2 UI) */}
      <PrivacySection />
      <p className="type-callout text-label-2">
        {t("crbs.profile.calendar")}{" "}
        <Link href="/my-bookings" className="font-medium text-tint-text underline-offset-4 hover:underline">
          {t("crbs.nav.myBookings")}
        </Link>
      </p>
    </div>
  );
}

function ProfileForm({ data }: { data: Profile }) {
  const { t, setLocale } = useI18n();
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
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            save.mutate(undefined, {
              onSuccess: (p) => {
                toast.success(t("crbs.common.saved"));
                const shown = displayLocale(p.language);
                if (shown) setLocale(shown);
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
              <SelectField id="pf-lang" value={f.language} onChange={(e) => set("language", e.target.value)} data-testid="profile-language">
                <option value="">{t("crbs.profile.orgDefault", { lang: langLabel(org.data?.default_language ?? "tr") })}</option>
                {languages.map((l) => (
                  <option key={l} value={l} lang={l}>
                    {langLabel(l)}
                  </option>
                ))}
              </SelectField>
            </Field>
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div>
            <Button type="submit" disabled={save.isPending} data-testid="profile-save" aria-busy={save.isPending || undefined}>
              <BusyLabel busy={save.isPending} label={t("busy.saving")}>
              {t("crbs.common.save")}</BusyLabel>
            </Button>
          </div>
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
            if (next.length < 8) return (setError(t("crbs.reset.tooShort")), shake());
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
            <Field label={t("crbs.users.newPassword")} htmlFor="pw-new">
              <Input id="pw-new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
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
