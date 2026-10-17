"use client";

import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HttpError } from "@/lib/api/client";
import { changePassword } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { AuthCard } from "./auth-card";

/**
 * Forced password change after login (`password_change_required`, POST /auth/change-password).
 * T-R2-03 (R2-S-02): after the 200 the cached /me is marked settled (force_password_reset false) and refetched BEFORE
 * the navigation, or the shell read the stale "true" and sent the user straight back here with empty fields.
 */
export function ChangePasswordForm() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = next.length > 0 && next.length < 8;
  const mismatch = again.length > 0 && again !== next;
  const submit = async () => {
    if (next.length < 8 || next !== again) return;
    setBusy(true);
    setError(null);
    try {
      await changePassword({ current_password: current || null, new_password: next });
      queryClient.setQueryData<{ force_password_reset?: boolean } | undefined>(["me", "full"], (me) => (me ? { ...me, force_password_reset: false } : me));
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      toast.success(t("glass.auth.changed"));
      const target = params.get("next");
      router.replace(target && target.startsWith("/") && !target.startsWith("//") ? target : "/dashboard");
      router.refresh();
    } catch (e) {
      setError(e instanceof HttpError && e.status === 400 ? t("glass.auth.changeRejected") : t("glass.auth.changeFailed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthCard title={t("glass.auth.changeTitle")} subtitle={t("glass.auth.changeHint")}>
      {error ? (
        <div role="alert" className="mb-4 rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg">
          {error}
        </div>
      ) : null}
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="cur">{t("glass.auth.current")}</Label>
          <Input id="cur" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          <p className="type-footnote text-label-3">{t("glass.auth.currentHint")}</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="new">{t("glass.auth.new")}</Label>
          <Input id="new" type="password" autoComplete="new-password" aria-invalid={tooShort} aria-describedby="new-hint" value={next} onChange={(e) => setNext(e.target.value)} />
          <p id="new-hint" className={tooShort ? "type-footnote text-status-infeasible-fg" : "type-footnote text-label-3"}>
            {t("glass.auth.newHint")}
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="again">{t("glass.auth.again")}</Label>
          <Input id="again" type="password" autoComplete="new-password" aria-invalid={mismatch} value={again} onChange={(e) => setAgain(e.target.value)} />
          {mismatch ? <p className="type-footnote text-status-infeasible-fg">{t("glass.auth.mismatch")}</p> : null}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={busy || next.length < 8 || next !== again}>
          {busy ? <Loader2 className="animate-spin" /> : null} {t("glass.auth.changeSubmit")}
        </Button>
      </form>
    </AuthCard>
  );
}
