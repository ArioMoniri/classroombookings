"use client";
/**
 * A local-password invitation on /login?invite=<token> (wave 3b W3-IDP): the invited person sets a password, then signs
 * in with the form below. Shown only when the invite's provider is ``local`` (read client side from
 * ``GET /auth/sso/invites/{token}``; the identity-provider invites keep the provider button flow).
 */
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/provider";
import { idp } from "./providers-api";

export function useInviteProvider(token: string | null) {
  return useQuery({
    queryKey: ["identity", "invite-provider", token],
    queryFn: () => idp.publicInvite(token ?? ""),
    enabled: !!token,
    retry: false,
    staleTime: 60_000,
  });
}

export function LocalInviteAccept({ token }: { token: string }) {
  const { t } = useI18n();
  const ids = { pw: useId(), again: useId(), err: useId() };
  const [pw, setPw] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  if (done !== null) {
    return (
      <Alert tone="success" data-testid="local-invite-done">
        {t("identity.localInvite.done", { email: done })}
      </Alert>
    );
  }
  return (
    <form
      className="flex flex-col gap-3"
      data-testid="local-invite-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (pw.length < 8) return setError(t("identity.localInvite.short"));
        if (pw !== again) return setError(t("identity.localInvite.mismatch"));
        setBusy(true);
        try {
          const out = await idp.acceptLocal(token, pw);
          setDone(out.email ?? "");
        } catch {
          setError(t("identity.localInvite.invalid"));
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="type-callout text-label-2">{t("identity.localInvite.lead")}</p>
      <div className="grid gap-1.5">
        <Label htmlFor={ids.pw}>{t("identity.localInvite.password")}</Label>
        <Input
          id={ids.pw}
          type="password"
          autoComplete="new-password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          aria-describedby={error ? ids.err : undefined}
          className="text-base sm:text-sm"
          data-testid="local-invite-password"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={ids.again}>{t("identity.localInvite.again")}</Label>
        <Input id={ids.again} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} className="text-base sm:text-sm" data-testid="local-invite-again" />
      </div>
      {error ? (
        <div id={ids.err}>
          <Alert tone="error" data-testid="local-invite-error">
            {error}
          </Alert>
        </div>
      ) : null}
      <BusyButton type="submit" busy={busy} busyLabel={t("busy.saving")} className="min-h-11" data-testid="local-invite-submit">
        {t("identity.localInvite.submit")}
      </BusyButton>
    </form>
  );
}
