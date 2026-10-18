"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useSyncExternalStore, type ReactNode } from "react";
import { useAppearancePreferences } from "@/components/ui/appearance-preferences";
import { KeyboardClearance } from "@/components/ui/keyboard-clearance";
import { AlertTriangle } from "lucide-react";
import { useOrgPublic } from "@/lib/api/crbs";
import { NoAccess } from "@/components/admin/kit";
import { onUnauthorized } from "@/lib/api/client";
import { hasPermission, useMeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { useUiStore } from "@/stores/ui";
import { useAccentPreference } from "./appearance";
import { MobileDrawer } from "./mobile-drawer";
import { Sidebar } from "./sidebar";
import { TabBar } from "./tab-bar";
import { MobileTopBar, TopBar } from "./top-bar";
import { planningRequirement, queryDependentRoute } from "./nav-config";
import { useGlobalShortcuts } from "./use-global-shortcuts";
import { useWorkspaceStore, useWorkspaceUser } from "./workspace";
import { useProfileLanguage } from "@/components/bookings/use-booking-format";
import { HelperRoot } from "@/components/helper/helper-root";
import { PageFileTarget } from "@/components/helper/page-file-target";
import { clearHelperFileSession } from "@/components/helper/file-session";
import { PeriodGridGate } from "./period-grid-gate";
import { WelcomeSettle } from "./welcome-settle";
// F-CH-1: palette, shortcuts, welcome guide and privacy gate in their own chunks (lazy-shell.tsx)
import { LazyCommandPalette, LazyPrivacyNoticeGate, LazyShortcutsSheet, LazyWelcomeHomeCardSlot, LazyWelcomePageSlot, LazyWelcomeProvider } from "./lazy-shell";

function OfflineBanner() {
  const { t } = useI18n();
  const offline = useSyncExternalStore(
    (cb) => {
      window.addEventListener("online", cb);
      window.addEventListener("offline", cb);
      return () => {
        window.removeEventListener("online", cb);
        window.removeEventListener("offline", cb);
      };
    },
    () => !navigator.onLine,
    () => false,
  );
  if (!offline) return null;
  return (
    <div role="status" className="mx-4 mt-2 rounded-full bg-status-warning px-4 py-1.5 text-center type-callout text-status-warning-fg sm:mx-6 lg:mx-8">
      {t("common.offline")}
    </div>
  );
}

/**
 * CRBS `layout.php`: while maintenance mode is on, every page says so (staff cannot book; roles with
 * system.bypass_maintenance_mode still can). /bookings shows its own 503 screen or bypass notice instead.
 */
export function MaintenanceBanner() {
  const { t } = useI18n();
  const pathname = usePathname();
  const org = useOrgPublic();
  // org data can land while the shell hydrates: render nothing until hydrated (no #418 mismatch)
  const hydrated = useHydrated();
  if (!hydrated || !org.data?.maintenance_mode || pathname === "/bookings" || pathname.startsWith("/bookings/")) return null;
  return (
    <div role="status" data-testid="shell-maintenance" className="mx-4 mt-2 flex items-start gap-2 rounded-xl bg-status-warning px-3 py-2 type-callout text-status-warning-fg sm:mx-6 lg:mx-8">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0">
        <span className="font-semibold">{t("admingaps.shell.maintenanceTitle")}</span>
        {" "}
        {org.data.maintenance_message || t("crbs.maintenance.default")}
      </p>
    </div>
  );
}

function Shortcuts() {
  useGlobalShortcuts();
  return null;
}

/**
 * Whether the shell must send the user to /login/change-password: only a settled /me that says so (T-R2-03, R2-S-02:
 * the cached "true" while the query refetches after a change bounced the user back to the empty form).
 */
export function mustChangePassword(me: { data?: { force_password_reset?: boolean } | undefined; isFetching: boolean }): boolean {
  return !me.isFetching && (me.data?.force_password_reset ?? false);
}

/**
 * Per-user state: appearance preferences (motion, transparency, accent) and the workspace memory
 * (term, run, week). When the signed-in user changes, the session term switches to the one they used last;
 * every later term change is remembered for them.
 */
function UserSync() {
  const me = useMeFull();
  const userKey = me.data ? String(me.data.id) : null;
  useAppearancePreferences(userKey ?? undefined);
  useAccentPreference(userKey ?? undefined);
  const setUserKey = useWorkspaceUser((s) => s.setUserKey);
  const router = useRouter();
  const pathname = usePathname();
  const mustChange = mustChangePassword(me);
  useEffect(() => {
    // a 401 anywhere = the session is gone (expired, revoked by a password change, signed out elsewhere):
    // clear the cookie and go to the login page once, with a notice, instead of rendering empty lists
    let leaving = false;
    return onUnauthorized(() => {
      if (leaving) return;
      leaving = true;
      const next = `${window.location.pathname}${window.location.search}`;
      // KVKK (HB-23 review, condition 10): no file hand-over (token + name) survives into the next session
      void clearHelperFileSession()
        .catch(() => undefined)
        .then(() => fetch("/api/auth/logout", { method: "POST" }))
        .catch(() => undefined)
        .finally(() => {
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a full load drops every cached query of the dead session
          window.location.assign(`/login?next=${encodeURIComponent(next)}&reason=expired`);
        });
    });
  }, []);
  useEffect(() => {
    // a forced password change cannot be skipped by opening a page directly
    if (mustChange) router.replace(`/login/change-password?next=${encodeURIComponent(pathname)}`);
  }, [mustChange, pathname, router]);
  useEffect(() => {
    if (!userKey) return;
    setUserKey(userKey);
    const remembered = useWorkspaceStore.getState().users[userKey]?.termId;
    useUiStore.getState().setTermId(remembered ?? null);
    return useUiStore.subscribe((s, prev) => {
      if (s.termId !== null && s.termId !== prev.termId) useWorkspaceStore.getState().remember(userKey, (m) => ({ ...m, termId: s.termId ?? undefined }));
    });
  }, [userKey, setUserKey]);
  return null;
}

/**
 * Planning routes reached by URL, a bookmark or an old link: without the permission show the no-access page
 * (the page is not mounted, so it calls nothing); /dashboard goes to /bookings. Nothing renders until the user
 * is known after hydration (no #418 mismatch, no flash of planner chrome).
 */
function RouteGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // only a query-dependent route (/import?kind=room-master) reads the search params, inside its own Suspense, so every
  // other page keeps its server render
  if (queryDependentRoute(pathname))
    return (
      <Suspense fallback={null}>
        <QueryRouteGuard pathname={pathname}>{children}</QueryRouteGuard>
      </Suspense>
    );
  return <PathGuard pathname={pathname} need={planningRequirement(pathname)}>{children}</PathGuard>;
}

function QueryRouteGuard({ pathname, children }: { pathname: string; children: ReactNode }) {
  const search = useSearchParams();
  return <PathGuard pathname={pathname} need={planningRequirement(pathname, search)}>{children}</PathGuard>;
}

function PathGuard({ pathname, need, children }: { pathname: string; need: string | string[] | undefined; children: ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const me = useMeFull();
  const hydrated = useHydrated();
  const known = hydrated && !me.isLoading;
  const denied = !!need && known && !me.isError && !hasPermission(me.data?.permissions, need);
  const home = denied && pathname === "/dashboard";
  useEffect(() => {
    if (home) router.replace("/bookings");
  }, [home, router]);
  if (!need) return <>{children}</>;
  if (!known || home) return null;
  if (denied) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("crbs.admin.noAccessBody")} />;
  return <>{children}</>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  // the profile language applies on the first page of a session, whichever it is (was: bookings pages only)
  useProfileLanguage();
  const density = useUiStore((s) => s.density);
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  return (
    // data-app-shell: html takes scroll-padding for the sticky top bar and the tab bar (globals.css)
    <div className="flex min-h-dvh" data-app-shell="">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-tint focus:px-3 focus:py-1.5 focus:text-tint-foreground">
        {t("app.skip")}
      </a>
      <Suspense fallback={<div className="hidden w-[264px] shrink-0 lg:block" />}>
        <Sidebar />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopBar />
        <Suspense fallback={<div className="hidden h-12 lg:block" />}>
          <TopBar />
        </Suspense>
        <OfflineBanner />
        <MaintenanceBanner />
        <main id="main" tabIndex={-1} className="flex-1 outline-hidden pt-3 pr-[max(1rem,env(safe-area-inset-right))] pb-[calc(6rem+env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] sm:pr-[max(1.5rem,env(safe-area-inset-right))] sm:pl-[max(1.5rem,env(safe-area-inset-left))] lg:px-8 lg:pt-4 lg:pb-8">
          <div className="mx-auto w-full max-w-[1600px]">
            {/* F-MB-1: on /dashboard, /reserve and /admin the card and the page appear together (no push-down) */}
            <WelcomeSettle>
              {/* WG-06 / WG-07: the hint strip at the top of the page */}
              <LazyWelcomePageSlot />
              {/* RF-16: the university's period grid (GET /period-grid) before the first screen that shows times */}
              <PeriodGridGate>
                <RouteGuard>{children}</RouteGuard>
              </PeriodGridGate>
              {/* HX12B-F10: the "Başlarken" card after the page's own task (desktop only; phones use "Daha") */}
              <LazyWelcomeHomeCardSlot />
            </WelcomeSettle>
          </div>
        </main>
      </div>
      <Suspense fallback={null}>
        <TabBar />
        <MobileDrawer />
      </Suspense>
      {/* T-R2-01: page-level fields scroll clear of the sticky save / search bars and the tab bar when the keyboard opens */}
      <KeyboardClearance scope="document" />
      <LazyCommandPalette />
      {/* HX-03: the helper sheet ("Yardımcı"), ⌘J and "Göster" */}
      <HelperRoot />
      {/* HB-23c: an OS file dragged onto any signed-in desktop page → the helper's file router (quiet edge outline) */}
      <PageFileTarget />
      <LazyShortcutsSheet />
      <Shortcuts />
      <UserSync />
      {/* A4 KVKK: the current privacy notice until acknowledged (never over /admin/kvkk; admins may postpone) */}
      <LazyPrivacyNoticeGate />
      {/* WG-04: the welcome guide (sheet, tour, checklist list, hints); it waits for any other dialog */}
      <LazyWelcomeProvider />
    </div>
  );
}
