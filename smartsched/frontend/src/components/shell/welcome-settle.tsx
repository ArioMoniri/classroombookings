"use client";
/**
 * F-MB-1 (fix-b-2026-10-18): on the audiences' home pages (`/dashboard`, `/reserve`, `/admin`) the guide's "Başlarken"
 * card sits ABOVE the page (WelcomePageSlot). GET /welcome is asked only after /auth/me, so the card used to land
 * above an already rendered page and push all of it down (CLS 0.48 on /dashboard, 0.43 on /admin at 390, the shifted
 * nodes `dashboard-hero` and the admin column). On those routes the slot and the page now appear together, once
 * GET /welcome has answered (or failed), at most SETTLE_CAP_MS later. Every other route renders as before.
 */
import { skipToken, useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { SettleGate } from "@/components/common/settle-gate";
import { Skeleton } from "@/components/ui/skeleton";
import { useMeFull } from "@/lib/api/shell-extra";
import { welcomeKeys, type WelcomeState } from "@/lib/api/welcome";
import { useHydrated } from "@/lib/use-hydrated";

/** The routes where the checklist card can open above the page (welcome/content.ts CHECKLIST_HOMES). */
export const WELCOME_HOLD_ROUTES = ["/dashboard", "/reserve", "/admin"] as const;

export function welcomeHold(s: { pathname: string; hydrated: boolean; meLoading: boolean; meKnown: boolean; welcomePending: boolean; slotLoaded: boolean }): boolean {
  if (!(WELCOME_HOLD_ROUTES as readonly string[]).includes(s.pathname)) return false;
  // the server render and the hydration pass hold too, so both produce the same markup
  if (!s.hydrated || s.meLoading) return true;
  // no user (signed out, /me failed): the welcome guide never asks, nothing to wait for
  if (!s.meKnown) return false;
  // the page slot is its own chunk (lazy-shell.tsx, F-CH-1): wait for it as well as for the answer
  return s.welcomePending || !s.slotLoaded;
}

/** Fetches the page slot's chunk (the one LazyWelcomePageSlot renders) and says when it is in. */
function useSlotChunk(wanted: boolean): boolean {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!wanted || loaded) return;
    let live = true;
    import("@/components/welcome/page-slot")
      .then(() => live && setLoaded(true))
      // a failed chunk: the slot shows nothing, the page must not wait for it
      .catch(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, [wanted, loaded]);
  return loaded;
}

export function WelcomeSettle({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const hydrated = useHydrated();
  const me = useMeFull();
  // read-only observer of the provider's GET /welcome (welcome-provider.tsx fetches it)
  const welcome = useQuery<WelcomeState>({ queryKey: welcomeKeys.state, queryFn: skipToken });
  const onHoldRoute = (WELCOME_HOLD_ROUTES as readonly string[]).includes(pathname);
  const slotLoaded = useSlotChunk(onHoldRoute && hydrated);
  const hold = welcomeHold({ pathname, hydrated, meLoading: me.isLoading, meKnown: !!me.data, welcomePending: welcome.status === "pending", slotLoaded });
  return (
    <SettleGate
      ready={!hold}
      testId="page-settling"
      placeholderClassName="min-h-[70dvh] space-y-4"
      placeholder={
        <>
          <Skeleton className="h-10 w-64 max-w-full rounded-xl" />
          <Skeleton className="h-48 rounded-2xl" />
        </>
      }
    >
      {children}
    </SettleGate>
  );
}
