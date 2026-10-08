"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { ALL_NAV_ITEMS } from "./nav-config";
import { useCycleTheme } from "./theme-toggle";

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.getAttribute("role") === "textbox";
}

/** ⌘K palette · ⌘B sidebar · g+<key> navigation · t theme · l language · ? shortcuts */
export function useGlobalShortcuts() {
  const router = useRouter();
  const { locale, setLocale, languages } = useI18n();
  const cycleTheme = useCycleTheme();
  const pending = useRef<number | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
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
        const item = ALL_NAV_ITEMS.find((i) => i.key === e.key.toLowerCase());
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
    return () => window.removeEventListener("keydown", onKey);
  }, [router, locale, setLocale, languages, cycleTheme]);
}
