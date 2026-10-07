"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarRange, Eye, EyeOff, Loader2 } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/endpoints";
import { HttpError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/provider";

const schema = z.object({ email: z.string().email(), password: z.string().min(1) });
type FormValues = z.infer<typeof schema>;

const MOCK = process.env.NEXT_PUBLIC_API_MOCK === "1";

export function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const reduce = useReducedMotion();
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: MOCK ? "fatih.demir@example.edu.tr" : "", password: "" } });

  useEffect(() => {
    if (error) alertRef.current?.focus();
  }, [error]);

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const { user } = await api.auth.login(values.email, values.password);
      const name = user.full_name?.split(" ")[0];
      toast.success(name ? `Hoş geldiniz, ${name}` : t("auth.title"));
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? next : "/dashboard");
      router.refresh();
    } catch (e) {
      setError(e instanceof HttpError && e.status === 0 ? e.message : t("auth.failed"));
      form.resetField("password");
    }
  });

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="w-full max-w-[400px] rounded-xl border bg-card p-6 shadow-elev-1 sm:p-8"
    >
      <div className="mb-6 flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <CalendarRange className="size-5" aria-hidden />
        </span>
        <div>
          <p className="text-md font-semibold leading-tight">{t("app.name")}</p>
          <p className="text-xs text-muted-foreground">{t("auth.subtitle")}</p>
        </div>
      </div>
      <h1 className="mb-4 text-2xl font-semibold tracking-tight">{t("auth.title")}</h1>
      {error ? (
        <div ref={alertRef} tabIndex={-1} role="alert" className="mb-4 rounded-md border border-status-infeasible-border bg-status-infeasible px-3 py-2 text-sm text-status-infeasible-fg outline-none">
          {error}
        </div>
      ) : null}
      <form onSubmit={onSubmit} className="space-y-4" noValidate aria-describedby={error ? "login-error" : undefined}>
        <div className="space-y-1.5">
          <Label htmlFor="email">{t("auth.email")}</Label>
          <Input id="email" type="email" inputMode="email" autoComplete="username" aria-invalid={!!form.formState.errors.email} {...form.register("email")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">{t("auth.password")}</Label>
          <div className="relative">
            <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" className="pr-9" aria-invalid={!!form.formState.errors.password} {...form.register("password")} />
            <button
              type="button"
              aria-pressed={show}
              aria-controls="password"
              aria-label={show ? "Hide password" : "Show password"}
              onClick={() => setShow((s) => !s)}
              className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        <Button type="submit" className="h-9 w-full" disabled={form.formState.isSubmitting} data-testid="login-submit">
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="animate-spin" /> {t("auth.signingIn")}
            </>
          ) : (
            t("auth.submit")
          )}
        </Button>
      </form>
      {MOCK ? <p className="mt-4 text-xs text-muted-foreground">{t("auth.demoHint")}</p> : null}
      <div className="mt-6 flex items-center justify-between border-t pt-4 text-xs text-muted-foreground">
        <span>{t("app.version")}</span>
        <div className="flex items-center gap-1">
          <LocaleToggle />
          <ThemeToggle />
        </div>
      </div>
    </motion.div>
  );
}
