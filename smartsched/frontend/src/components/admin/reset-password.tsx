"use client";
/**
 * /reset-password: request a one-time code (never reveals whether the account exists; without SMTP the
 * administrators are notified) and set a new password with the code (`?token=` pre-fills it).
 * T-R2-06 (R2-A-06, R2-S-12): no LDAP sentence; the page names the 24-hour code lifetime. AUX12-F07 (fix-h): the new
 * password goes through SetPasswordForm (12 characters, show/hide, one field) and the request field carries the SSO line.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { crbs, useCrbsMutation } from "@/lib/api/crbs";
import { SetPasswordForm } from "@/components/auth/set-password-form";
import { CREDENTIAL_FORM } from "@/components/auth/credential-form";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { Alert, Field } from "./kit";
import { PublicCard } from "./public-card";

export function ResetPassword() {
  const params = useSearchParams();
  const [mode, setMode] = useState<"request" | "confirm">(params.get("token") ? "confirm" : "request");
  return mode === "request" ? <RequestForm onHaveCode={() => setMode("confirm")} /> : <ConfirmForm initialToken={params.get("token") ?? ""} onBack={() => setMode("request")} />;
}

function RequestForm({ onHaveCode }: { onHaveCode: () => void }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const m = useCrbsMutation(() => crbs.auth.requestReset(email.trim()));
  const hydrated = useHydrated(); // HB18-F02: no native submit before hydration
  return (
    <PublicCard title={t("crbs.reset.title")} lead={t("crbs.reset.lead")}>
      {sent ? (
        <Alert tone="success" testId="reset-requested">
          {t("crbs.reset.requested")}
        </Alert>
      ) : (
        <form
          {...CREDENTIAL_FORM}
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate(undefined, { onSuccess: () => setSent(true), onError: () => setSent(true) });
          }}
        >
          <Field label={t("crbs.reset.identifier")} htmlFor="rs-email" hint={t("auth.setPassword.ssoLine")}>
            <Input id="rs-email" autoComplete="username" autoCapitalize="none" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" size="lg" disabled={!hydrated || !email.trim() || m.isPending} aria-busy={m.isPending || undefined}>
            <BusyLabel busy={m.isPending} label={t("busy.working")}>
            {t("crbs.reset.send")}</BusyLabel>
          </Button>
        </form>
      )}
      <div className="mt-4 flex flex-wrap justify-between gap-2 type-callout">
        <Button variant="link" className="px-0" onClick={onHaveCode}>
          {t("crbs.reset.haveCode")}
        </Button>
        <Link href="/login" className="inline-flex items-center text-tint-text underline-offset-4 hover:underline pointer-coarse:min-h-11">
          {t("crbs.reset.backToLogin")}
        </Link>
      </div>
    </PublicCard>
  );
}

/**
 * AUX12-F07 (fix-h-2026-10-18): the code, then the one set-password form of the sign-in flow (auth.md §4.5,
 * `SetPasswordForm`): one field with show/hide, "En az 12 karakter" as the backend requires, the live counter.
 */
function ConfirmForm({ initialToken, onBack }: { initialToken: string; onBack: () => void }) {
  const { t } = useI18n();
  const [token, setToken] = useState(initialToken);
  return (
    <PublicCard title={t("crbs.reset.newTitle")} lead={t("crbs.reset.newLead")}>
      <div className="flex flex-col gap-4">
        <Field label={t("crbs.reset.code")} htmlFor="rs-token">
          <Input id="rs-token" className="font-mono" autoComplete="one-time-code" required value={token} onChange={(e) => setToken(e.target.value)} />
        </Field>
        <SetPasswordForm mode="reset" token={token.trim()} title={false} />
        <Button type="button" variant="link" className="self-start px-0 pointer-coarse:min-h-11" onClick={onBack}>
          {t("crbs.reset.needCode")}
        </Button>
      </div>
    </PublicCard>
  );
}
