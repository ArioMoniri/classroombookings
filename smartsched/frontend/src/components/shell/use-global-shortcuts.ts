"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { hasPermission, usePermissions } from "@/lib/api/shell-extra";
import { visibleNavGroups } from "./nav-config";
import { useCycleTheme } from "./theme-toggle";

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.getAttribute("role") === "textbox";
}

/** Set on <html> once the keydown listener is attached: Playwright waits for it instead of a fixed delay. */
export const SHORTCUTS_ARMED_ATTR = "data-shortcuts";

/**
 * ⌘K palette · ⌘B sidebar · g+<key> navigation · t theme · l language · ? shortcuts.
 * The listener is attached once on mount and never re-attached (the handler reads the latest router / locale /
 * permission list through a ref), and html[data-shortcuts="armed"] says so: the e2e gate saw Shift+? land before the
 * listener existed when the effect re-ran on every permission or locale change (loop-r1-laneA T-R1-06 flake).
 */
export function useGlobalShortcuts() {
  const router = useRouter();
  const { locale, setLocale, languages } = useI18n();
  const cycleTheme = useCycleTheme();
  const pending = useRef<number | null>(null);
  // g+<key> only for pages this user may open (a teacher's "g d" must not open the planner dashboard);
  // the booking entries (g b, g m) come from the same list
  const { perms } = usePermissions();
  const items = useMemo(() => visibleNavGroups((p) => hasPermission(perms, p)).flatMap((g) => g.items), [perms]);
  const latest = useRef({ router, locale, setLocale, languages, cycleTheme, items });
  latest.current = { router, locale, setLocale, languages, cycleTheme, items };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { router, locale, setLocale, languages, cycleTheme, items } = latest.current;
      const store = useUiStore.getState();
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        store.setPaletteOpen(!store.paletteOpen);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        store.toggleSidebar();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || isEditable(e.target)) return;
      if (pending.current !== null) {
        window.clearTimeout(pending.current);
        pending.current = null;
        const item = items.find((i) => i.key === e.key.toLowerCase());
        if (item) {
          e.preventDefault();
          router.push(item.href);
        }
        return;
      }
      switch (e.key) {
        case "g":
          pending.current = window.setTimeout(() => (pending.current = null), 800);
          break;
        case "t":
          cycleTheme();
          break;
        case "l":
          setLocale(languages[(languages.indexOf(locale) + 1) % languages.length]!);
          router.refresh();
          break;
        case "?":
          store.setShortcutsOpen(true);
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    document.documentElement.setAttribute(SHORTCUTS_ARMED_ATTR, "armed");
    return () => {
      window.removeEventListener("keydown", onKey);
      document.documentElement.removeAttribute(SHORTCUTS_ARMED_ATTR);
    };
  }, []);
}
