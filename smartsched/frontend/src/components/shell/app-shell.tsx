"use client";

import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useSyncExternalStore, type ReactNode } from "react";
import { useAppearancePreferences } from "@/components/ui/appearance-preferences";
import { AlertTriangle } from "lucide-react";
import { useOrgPublic } from "@/lib/api/crbs";
import { useMeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { useAccentPreference } from "./appearance";
import { CommandPalette } from "./command-palette";
import { MobileDrawer } from "./mobile-drawer";
import { ShortcutsSheet } from "./shortcuts-sheet";
import { Sidebar } from "./sidebar";
import { TabBar } from "./tab-bar";
import { MobileTopBar, TopBar } from "./top-bar";
import { useGlobalShortcuts } from "./use-global-shortcuts";
import { useWorkspaceStore, useWorkspaceUser } from "./workspace";

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
    <div role="status" className="mx-4 mt-2 rounded-full bg-status-warning px-4 py-1.5 text-center text-[13px] text-status-warning-fg sm:mx-6 lg:mx-8">
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
  if (!org.data?.maintenance_mode || pathname === "/bookings" || pathname.startsWith("/bookings/")) return null;
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
  const mustChange = me.data?.force_password_reset ?? false;
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

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const density = useUiStore((s) => s.density);
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  return (
    <div className="flex min-h-dvh">
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
        <main id="main" className="flex-1 px-4 pt-3 pb-[calc(6rem+env(safe-area-inset-bottom))] sm:px-6 lg:px-8 lg:pt-4 lg:pb-8">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>
      <Suspense fallback={null}>
        <TabBar />
        <MobileDrawer />
      </Suspense>
      <CommandPalette />
      <ShortcutsSheet />
      <Shortcuts />
      <UserSync />
    </div>
  );
}
