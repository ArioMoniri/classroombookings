"use client";
/**
 * /profile (CRBS `Profile`): own e-mail, names, display name, extension and language (per user, as in
 * CRBS), and the password change (current password required unless an administrator forced a change).
 */
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, useShake } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMe, useCrbsMutation, useOrgPublic, useProfile, type Profile } from "@/lib/api/crbs";
import { isLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, Loading, PageTitle, SectionTitle, SelectField } from "./kit";

const LANG_LABEL: Record<string, string> = { tr: "Türkçe", en: "English" };

export function ProfileView() {
  const { t } = useI18n();
  const q = useProfile();
  const me = useCrbsMe();
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageTitle title={t("crbs.profile.title")} subtitle={q.data ? [q.data.username ?? q.data.email, q.data.role_name].filter(Boolean).join(" · ") : undefined} />
      {q.isLoading ? <Loading /> : q.data ? <ProfileForm key={q.data.id} data={q.data} /> : <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>}
      <PasswordForm forced={!!me.data?.force_password_reset} />
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
  const [f, setF] = useState({ email: data.email ?? "", firstname: data.firstname ?? "", lastname: data.lastname ?? "", displayname: data.displayname ?? "", ext: data.ext ?? "", language: data.language ?? "" });
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: string) => setF((p) => ({ ...p, [k]: v }));
  const save = useCrbsMutation(
    () => crbs.auth.putProfile({ email: f.email.trim() || null, firstname: f.firstname.trim() || null, lastname: f.lastname.trim() || null, displayname: f.displayname.trim() || null, ext: f.ext.trim() || null, ...(f.language ? { language: f.language } : {}) }),
    [["crbs", "profile"], ["crbs", "me"], ["me"]],
  );
  const languages = org.data?.languages ?? ["tr", "en"];
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
                if (p.language && isLocale(p.language)) setLocale(p.language);
                void qc.invalidateQueries({ queryKey: ["me"] });
              },
              onError: (err) => setError(bookingErrorMessage(crbsError(err), t)),
            });
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
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
            <Field label={t("crbs.profile.language")} htmlFor="pf-lang" hint={t("crbs.profile.languageHint")}>
              <SelectField id="pf-lang" value={f.language} onChange={(e) => set("language", e.target.value)} data-testid="profile-language">
                <option value="">{t("crbs.profile.orgDefault", { lang: LANG_LABEL[org.data?.default_language ?? "tr"] ?? org.data?.default_language ?? "" })}</option>
                {languages.map((l) => (
                  <option key={l} value={l}>
                    {LANG_LABEL[l] ?? l}
                  </option>
                ))}
              </SelectField>
            </Field>
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div>
            <Button type="submit" disabled={save.isPending} data-testid="profile-save">
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t("crbs.common.save")}
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
              onSuccess: () => {
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
          <div ref={ref} className="t-input grid gap-3 sm:grid-cols-3">
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
