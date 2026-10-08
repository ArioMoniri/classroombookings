"use client";

import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useHydrated } from "@/lib/use-hydrated";

/**
 * Renders the same placeholder on the server and in the hydration pass, then the live view.
 * Query data that resolves before a Suspense boundary hydrates otherwise changes the first client render
 * and React throws #418 (text mismatch) — seen on /runs and /settings in the production build.
 */
export function HydrationGate({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) {
  const hydrated = useHydrated();
  if (!hydrated)
    return (
      fallback ?? (
        <div aria-hidden className="space-y-4">
          <Skeleton className="h-10 w-64 rounded-xl" />
          <Skeleton className="h-48 rounded-2xl" />
        </div>
      )
    );
  return <>{children}</>;
}
