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
import { I18nProvider } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n";

function ApiErrorBridge() {
  const router = useRouter();
  useEffect(
    () =>
      onApiError((err: HttpError) => {
        if (err.status === 401) {
          router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
          return;
        }
        toast.error(err.message, { description: err.errorId ? `Error id ${err.errorId}` : undefined, duration: err.status >= 500 ? Infinity : 8000 });
      }),
    [router],
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
