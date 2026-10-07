"use client";

import { Suspense, useEffect, useSyncExternalStore, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { CommandPalette } from "./command-palette";
import { MobileDrawer } from "./mobile-drawer";
import { ShortcutsSheet } from "./shortcuts-sheet";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { useGlobalShortcuts } from "./use-global-shortcuts";

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
  return <div role="status" className="bg-status-warning px-4 py-1.5 text-center text-sm text-status-warning-fg">{t("common.offline")}</div>;
}

function Shortcuts() {
  useGlobalShortcuts();
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
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-1.5 focus:text-primary-foreground">
        {t("app.skip")}
      </a>
      <Suspense fallback={<div className="hidden w-[240px] shrink-0 border-r bg-sidebar lg:block" />}>
        <Sidebar />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <Suspense fallback={<div className="h-12 border-b" />}>
          <TopBar />
        </Suspense>
        <OfflineBanner />
        <main id="main" className="flex-1 px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>
      <Suspense fallback={null}>
        <MobileDrawer />
      </Suspense>
      <CommandPalette />
      <ShortcutsSheet />
      <Shortcuts />
    </div>
  );
}
