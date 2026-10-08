"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HttpError } from "@/lib/api/client";
import { loginWithIdentifier } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { AuthCard } from "./auth-card";

/* CRBS parity: an e-mail or a username */
const schema = z.object({ identifier: z.string().trim().min(2), password: z.string().min(1) });
type FormValues = z.infer<typeof schema>;

export function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { identifier: "", password: "" } });

  useEffect(() => {
    if (error) alertRef.current?.focus();
  }, [error]);

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const { user, mustChangePassword } = await loginWithIdentifier(values.identifier, values.password);
      const next = params.get("next");
      const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
      if (mustChangePassword) {
        router.replace(`/login/change-password?next=${encodeURIComponent(target)}`);
        return;
      }
      const name = user?.full_name?.split(" ")[0];
      toast.success(name ? t("glass.auth.welcome", { name }) : t("auth.title"));
      // a teacher has no planning dashboard: land on the timetable (permissions come from /auth/me)
      const planner = !user || user.permissions.includes("planning.view");
      router.replace(target === "/dashboard" && !planner ? "/timetable" : target);
      router.refresh();
    } catch (e) {
      setError(e instanceof HttpError && e.status === 0 ? t("glass.auth.offline") : t("glass.auth.failed"));
      form.resetField("password");
      shake();
    }
  });

  return (
    <AuthCard title={t("auth.title")}>
      {error ? (
        <div ref={alertRef} id="login-error" tabIndex={-1} role="alert" className="mb-4 rounded-xl bg-status-infeasible px-3 py-2 text-[13px] text-status-infeasible-fg outline-none">
          {error}
        </div>
      ) : null}
      <form onSubmit={onSubmit} className="space-y-4" noValidate aria-describedby={error ? "login-error" : undefined}>
        <div ref={shakeRef} className="t-input space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="identifier">{t("glass.auth.identifier")}</Label>
            <Input id="identifier" autoComplete="username" autoCapitalize="none" spellCheck={false} aria-invalid={!!form.formState.errors.identifier} placeholder={t("glass.auth.identifierHint")} {...form.register("identifier")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">{t("auth.password")}</Label>
            <div className="relative">
              <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" className="pr-10" aria-invalid={!!form.formState.errors.password} {...form.register("password")} />
              <button
                type="button"
                aria-pressed={show}
                aria-controls="password"
                aria-label={show ? t("glass.auth.hidePassword") : t("glass.auth.showPassword")}
                onClick={() => setShow((s) => !s)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-label-3 outline-none hover:text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus)"
              >
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting} data-testid="login-submit">
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="animate-spin" /> {t("auth.signingIn")}
            </>
          ) : (
            t("auth.submit")
          )}
        </Button>
      </form>
    </AuthCard>
  );
}
