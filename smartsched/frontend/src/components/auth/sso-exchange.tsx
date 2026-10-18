"use client";
/**
 * /login/sso (sign-in.md §14): post the one-time ticket (`POST /auth/sso/exchange`; the Next proxy keeps the token
 * in the httpOnly cookie), then go to `/welcome[?invited=1|?bound=1]` when the backend says this sign-in created or
 * bound the account, else to `next` or the role's home. A used or expired ticket (401) lands on the generic
 * `failed` error of /login — the same text as any other refusal.
 * AU-16: `idp_mfa_missing` (the policy wants 2FA for the role, the provider asserted none, enforcement off) shows the
 * server's step-up sentence once, as a lasting warning toast that survives the navigation.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { applySessionLanguage } from "@/components/bookings/use-booking-format";
import { BusyGlyph } from "@/components/ui/busy-label";
import { exchangeTicket } from "@/lib/api/identity";
import { MeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { rememberMethod } from "./local-sign-in";
import { homeFor, safeNext, WELCOME_KEY, welcomePath, type WelcomeFlag } from "./signin-model";
import { SignInShell } from "./signin-shell";

export function SsoExchange({ logoUrl, kvkkUrl }: { logoUrl: string | null; kvkkUrl: string | null }) {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const started = useRef(false);

  useEffect(() => {
    // the ticket is single use: never post it twice (StrictMode re-runs effects; refs survive that)
    if (started.current) return;
    started.current = true;
    const ticket = params.get("ticket") ?? "";
    const urlNext = safeNext(params.get("next"));
    const fail = () => router.replace(`/login?error=failed${urlNext ? `&next=${encodeURIComponent(urlNext)}` : ""}`);
    if (ticket.length < 16) return fail();
    void (async () => {
      try {
        const out = await exchangeTicket(ticket);
        rememberMethod("microsoft");
        const user = MeFull.safeParse(out.user);
        const me = user.success ? user.data : null;
        const next = safeNext(out.next) ?? urlNext;
        if (out.idp_mfa_missing) {
          const text = (locale === "tr" ? out.idp_mfa_message_tr : out.idp_mfa_message_en) || t("auth.idp.mfaMissing");
          toast.warning(t("auth.idp.mfaMissingTitle"), { description: text, duration: 12_000, id: "idp-mfa-missing" });
        }
        if (out.welcome) {
          const flag: WelcomeFlag = { kind: out.welcome, inviter: out.inviter_name ?? null, next };
          sessionStorage.setItem(WELCOME_KEY, JSON.stringify(flag));
          router.replace(welcomePath(out.welcome));
          return;
        }
        if (me) await applySessionLanguage(me.id, locale, setLocale);
        const name = me?.full_name?.split(" ")[0];
        toast.success(name ? t("glass.auth.welcome", { name }) : t("signin.title"));
        router.replace(next ?? homeFor(me?.permissions));
        router.refresh();
      } catch {
        fail();
      }
    })();
  }, [params, router, locale, setLocale, t]);

  return (
    <SignInShell logoUrl={logoUrl} kvkkUrl={kvkkUrl} testId="signin-exchange">
      <h1 id="signin-title" className="type-large-title text-label-1">
        {t("signin.exchange.title")}
      </h1>
      <p role="status" className="mt-3 flex items-center gap-2 type-callout text-label-2">
        <BusyGlyph className="size-4" />
        {t("signin.exchange.busy")}
      </p>
    </SignInShell>
  );
}
