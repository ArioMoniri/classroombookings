"use client";
/**
 * One way to leave the sign-in sheet (docs/design/v3/auth.md §4.3, §5, §5.6): after the password, a passkey, the
 * second step or the enrolment, the route handler answers `signed_in` / `mfa` / `setup`, and this hook goes on:
 * - `mfa` → `/login/verify` (the challenge stays in the httpOnly cookie; only `next` is in the URL);
 * - `setup` (grace over) or `signed_in` with `setup_due` (grace running) → `/login/setup-2fa`;
 * - `signed_in` → the forced password change, or the welcome toast and `next` / `homeFor()`;
 *   a recovery code adds "Bir kurtarma kodu kullandınız. {n} kod kaldı." (+ "Yeni kodlar oluştur" at ≤ 3).
 */
import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { toast } from "sonner";
import { applySessionLanguage } from "@/components/bookings/use-booking-format";
import type { SignInStepOut } from "@/lib/api/auth-security";
import { MeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { LOW_CODES } from "./mfa-model";
import { homeFor, LAST_METHOD_COOKIE } from "./signin-model";

export type SignInMethod = "local" | "microsoft" | "passkey";

export function rememberSignInMethod(method: SignInMethod) {
  document.cookie = `${LAST_METHOD_COOKIE}=${method}; path=/; max-age=31536000; samesite=lax`;
}

const withNext = (path: string, next: string | null) => (next ? `${path}?next=${encodeURIComponent(next)}` : path);

export function useFinishSignIn(next: string | null) {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  return useCallback(
    async (out: SignInStepOut, method: SignInMethod = "local"): Promise<void> => {
      if (out.status === "mfa") {
        router.push(withNext("/login/verify", next));
        return;
      }
      if (out.status === "setup") {
        router.push(withNext("/login/setup-2fa", next));
        return;
      }
      if (out.status !== "signed_in") return;
      rememberSignInMethod(method);
      const parsed = MeFull.safeParse(out.user);
      const user = parsed.success ? parsed.data : null;
      const target = next ?? homeFor(user?.permissions);
      if (out.password_change_required || user?.force_password_reset) {
        router.replace(`/login/change-password?next=${encodeURIComponent(target)}`);
        return;
      }
      if (out.setup_due) {
        router.replace(withNext("/login/setup-2fa", target));
        return;
      }
      if (user) await applySessionLanguage(user.id, locale, setLocale);
      if (typeof out.recovery_codes_remaining === "number") {
        const n = out.recovery_codes_remaining;
        toast.warning(t("auth.mfa.recoveryUsed", { n }), {
          duration: 8000,
          action: n <= LOW_CODES ? { label: t("auth.mfa.newCodes"), onClick: () => router.push("/profile#security") } : undefined,
        });
      } else {
        const name = user?.full_name?.split(" ")[0];
        toast.success(name ? t("glass.auth.welcome", { name }) : t("signin.title"), { duration: 3000 });
      }
      router.replace(target);
      router.refresh();
    },
    [locale, next, router, setLocale, t],
  );
}
