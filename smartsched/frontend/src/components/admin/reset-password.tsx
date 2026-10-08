"use client";
/**
 * /reset-password: request a one-time code (never reveals whether the account exists; without SMTP the
 * administrators are notified) and set a new password with the code (`?token=` pre-fills it).
 */
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
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
  return (
    <PublicCard title={t("crbs.reset.title")} lead={t("crbs.reset.lead")}>
      {sent ? (
        <Alert tone="success" testId="reset-requested">
          {t("crbs.reset.requested")}
        </Alert>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate(undefined, { onSuccess: () => setSent(true), onError: () => setSent(true) });
          }}
        >
          <Field label={t("crbs.reset.identifier")} htmlFor="rs-email">
            <Input id="rs-email" autoComplete="username" autoCapitalize="none" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" size="lg" disabled={!email.trim() || m.isPending}>
            {m.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.reset.send")}
          </Button>
        </form>
      )}
      <div className="mt-4 flex flex-wrap justify-between gap-2 type-callout">
        <Button variant="link" className="px-0" onClick={onHaveCode}>
          {t("crbs.reset.haveCode")}
        </Button>
        <Link href="/login" className="text-tint-text underline-offset-4 hover:underline">
          {t("crbs.reset.backToLogin")}
        </Link>
      </div>
    </PublicCard>
  );
}

function ConfirmForm({ initialToken, onBack }: { initialToken: string; onBack: () => void }) {
  const { t } = useI18n();
  const [token, setToken] = useState(initialToken);
  const [pw, setPw] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const { ref, shake } = useShake<HTMLDivElement>();
  const m = useCrbsMutation(() => crbs.auth.confirmReset(token.trim(), pw));
  const fail = (msg: string) => (setError(msg), shake());
  return (
    <PublicCard title={t("crbs.reset.newTitle")} lead={t("crbs.reset.newLead")}>
      {done ? (
        <div className="flex flex-col gap-3">
          <Alert tone="success" testId="reset-done">
            {t("crbs.reset.done")}
          </Alert>
          <Button nativeButton={false} render={<Link href="/login" />}>
            {t("crbs.reset.backToLogin")}
          </Button>
        </div>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (pw.length < 8) return fail(t("crbs.reset.tooShort"));
            if (pw !== again) return fail(t("crbs.reset.mismatch"));
            m.mutate(undefined, { onSuccess: () => setDone(true), onError: (err) => fail(crbsError(err).status === 400 ? t("crbs.reset.badCode") : crbsError(err).message) });
          }}
        >
          <div ref={ref} className="t-input flex flex-col gap-3">
            <Field label={t("crbs.reset.code")} htmlFor="rs-token">
              <Input id="rs-token" className="font-mono" autoComplete="one-time-code" required value={token} onChange={(e) => setToken(e.target.value)} />
            </Field>
            <Field label={t("crbs.users.newPassword")} htmlFor="rs-pw" hint={t("crbs.users.passwordHint")}>
              <Input id="rs-pw" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </Field>
            <Field label={t("crbs.reset.again")} htmlFor="rs-pw2">
              <Input id="rs-pw2" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
            </Field>
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Button type="submit" size="lg" disabled={!token.trim() || !pw || m.isPending}>
            {m.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.reset.setPassword")}
          </Button>
          <Button type="button" variant="link" className="self-start px-0" onClick={onBack}>
            {t("crbs.reset.needCode")}
          </Button>
        </form>
      )}
    </PublicCard>
  );
}
