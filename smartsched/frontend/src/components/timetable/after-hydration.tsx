"use client";

import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";

/**
 * Renders `children` only after hydration; the server and the hydration pass both render the same quiet
 * "Loading…" line.
 *
 * Why (React #418 on /timetable and /classes in the production build): these pages read their data from the
 * TanStack Query cache, whose `useSyncExternalStore` hands React the live client snapshot even while hydrating.
 * Their Suspense boundaries hydrate in a later, low-priority pass (the /classes boundary is even streamed out
 * of band), so `/auth/me`, `/terms` or `/runs`, started by the shell's effects, can land first; the restarted
 * pass then renders markup the server never had. The server has no data for these pages anyway (it renders a
 * loading state), so nothing visible is lost, and the page's own hydration work, which made the window wide,
 * becomes trivial.
 */
export function AfterHydration({ children, testId }: { children: ReactNode; testId?: string }) {
  const hydrated = useHydrated();
  const { t } = useI18n();
  if (hydrated) return <>{children}</>;
  return (
    <p className="flex items-center gap-2 px-6 py-6 text-[13px] text-label-2" role="status" data-testid={testId}>
      <span className="size-3 animate-spin rounded-full border-2 border-label-4 border-t-label-2 motion-reduce:animate-none" aria-hidden />
      {t("common.loading")}
    </p>
  );
}
