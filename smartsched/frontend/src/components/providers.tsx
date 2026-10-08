"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AppearanceMotionConfig } from "@/components/ui/appearance-preferences";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { HttpError, onApiError } from "@/lib/api/client";
import { I18nProvider, useI18n } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n";

/** Planner-facing error toasts: the backend's English detail is shown only in English (usability m1, M3). */
function ApiErrorBridge() {
  const router = useRouter();
  const { t, locale } = useI18n();
  useEffect(
    () =>
      onApiError((err: HttpError) => {
        if (err.status === 401) {
          router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
          return;
        }
        const title =
          err.status === 0 ? t("glass.errors.offline") : err.status === 403 ? t("glass.errors.forbidden") : err.status === 404 ? t("glass.errors.notFound") : err.status === 409 ? t("glass.errors.conflict") : err.status >= 500 ? t("glass.errors.server") : t("glass.errors.rejected");
        const detail = locale === "en" && err.status > 0 && err.status < 500 ? err.message : undefined;
        const id = err.errorId ? t("glass.errors.errorId", { id: err.errorId }) : undefined;
        toast.error(title, { description: [detail, id].filter(Boolean).join(" · ") || undefined, duration: err.status >= 500 ? Infinity : 8000 });
      }),
    [router, t, locale],
  );
  return null;
}

export function Providers({ locale, children }: { locale: Locale; children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, retry: (count, error) => !(error instanceof HttpError && error.status < 500) && count < 2, refetchOnWindowFocus: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        <I18nProvider initialLocale={locale}>
          {/* motion/react follows the OS and the in-app Reduce motion switch (motion.md §2, pattern §0) */}
          <AppearanceMotionConfig>
            <TooltipProvider delay={300}>
              {children}
              <Toaster position="bottom-right" closeButton visibleToasts={3} />
              <ApiErrorBridge />
            </TooltipProvider>
          </AppearanceMotionConfig>
        </I18nProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
